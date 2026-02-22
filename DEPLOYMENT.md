# Sturgeon Deployment Guide

This is the current deployment reference for the Modal backend and Vercel frontend.

## Architecture

- Frontend: Next.js (Vercel)
- Backend: `modal_backend/app.py` (Modal ASGI app)
- Inference in one Modal container:
  - vLLM OpenAI-compatible server on `:6501` (MedGemma 1.5 4B-it)
  - MedSigLIP server on `:6502`
  - FastAPI routes exposed through `@modal.asgi_app()`
- Persistent volumes:
  - `medgemma-cache` for model weights
  - `chroma-db` for RAG cache/index

## Current Production Config

From `modal_backend/app.py`:

- `gpu="L4"`
- `timeout=600`
- `scaledown_window=600`
- `max_containers=1`
- vLLM flags include:
  - `--max-model-len 4096`
  - `--gpu-memory-utilization 0.70`
  - `--enforce-eager`

Why this matters:

- `max_containers=1` prevents cold-start autoscaling fan-out.
- `--enforce-eager` gives more predictable startup behavior for this workload.
- 10-minute scaledown window helps avoid repeated cold starts during demos.

## Exposed Backend Endpoints

- `GET /health`
- `GET /rag-status`
- `POST /extract-labs`
- `POST /extract-labs-file`
- `POST /differential`
- `POST /debate-turn`
- `POST /summary`
- `POST /analyze-image`
- `POST /rag-evaluate` (dev/eval path)

## Prerequisites

- Modal account and CLI (`modal setup` complete)
- Vercel account/project
- HuggingFace access approved for `google/medgemma-1.5-4b-it`
- Gemini API key

## Secrets and Environment

Modal secrets expected by backend:

- `huggingface-token` with `HF_TOKEN`
- `gemini-api-key` with `GEMINI_API_KEY`

Vercel environment variable expected by frontend:

- `BACKEND_URL=https://<your-modal-endpoint>.modal.run`

## Deploy Steps

Backend (Modal):

```bash
modal deploy modal_backend/app.py
```

Frontend (Vercel):

```bash
vercel --prod
```

After deploy:

1. Verify backend health endpoint responds.
2. Verify frontend can call backend via `BACKEND_URL`.
3. Run one full flow: upload -> differential -> debate -> summary.

## Cold Start Strategy

Current behavior:

- Frontend warmup sends an immediate health ping, then backoff polling.
- Backoff sequence in UI logic: ~20s -> 30s -> 45s.
- Health API proxy disables caching (`cache: "no-store"`).

Relevant frontend files:

- `frontend/lib/useWarmup.ts`
- `frontend/components/WarmupToast.tsx`
- `frontend/app/api/health/route.ts`

## Reliability Safeguards (Important)

Implemented in `modal_backend/app.py` and `modal_backend/gemini_orchestrator_modal.py`:

- Centralized vLLM response handling for non-200 errors.
- Adaptive retry on `max_tokens` overflow (reduce generation budget).
- Compaction + retry on `input_tokens` overflow (reduce prompt size).
- Debate prompt compaction (round/history/image/RAG trims) to stay under context limit.
- Debate hard failures return HTTP 500 (enables frontend Retry UX).

## Citation Integrity Rules

Current policy:

- Only citations with valid absolute `http(s)` URLs are linked.
- Missing/invalid URLs are normalized from known source mappings when possible.
- Unresolvable citations are dropped.
- If no valid links remain, guideline link section is suppressed in debate UI.

Relevant files:

- `modal_backend/app.py`
- `frontend/app/debate/page.tsx`

## Known Failure Modes and Fixes

1. vLLM `max_tokens` overflow

- Symptom: non-200 validation error with context budget exceeded.
- Fix: automatic retry with reduced `max_tokens`.

2. vLLM `input_tokens` overflow

- Symptom: prompt too large even after lowering generation budget.
- Fix: compact context (history, rounds, image context, RAG chunks) and retry.

3. Debate fallback appears "successful" but should be retriable

- Symptom: backend returns 200 with synthetic error text.
- Fix: propagate hard failures as HTTP 500 so frontend Retry button appears.

4. Citation links open current page instead of guideline source

- Symptom: empty/invalid href behaves like same-page navigation.
- Fix: backend URL filtering + frontend URL gating.

## Troubleshooting

Useful commands:

```bash
modal app logs sturgeon-medgemma
modal app list
```

Health check:

```bash
curl https://<your-modal-endpoint>.modal.run/health
```

If cold starts feel excessive:

- Confirm `max_containers=1` is still present.
- Confirm warmup polling is not aggressive/overlapping.
- Confirm container was not scaled down due to inactivity.

## Cost Notes

- This setup is optimized for demo/competition usage, not always-on latency.
- Main cost controls currently in use:
  - serverless scale-to-zero
  - `scaledown_window=600`
  - single-container cap during cold start

## Source of Truth

- Runtime behavior: `modal_backend/app.py`
- Orchestrator behavior: `modal_backend/gemini_orchestrator_modal.py`
- Session history and fixes: `CHANGELOG.md`
