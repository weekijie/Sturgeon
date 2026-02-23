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
  - `vllm-cache` for vLLM runtime/cache artifacts
  - `chroma-db` for RAG cache/index

## Current Production Config

From `modal_backend/app.py`:

- `gpu="L4"`
- `timeout=600`
- `scaledown_window=300`
- `max_containers=MODAL_MAX_CONTAINERS` (default `1`)
- `@modal.concurrent(max_inputs=MODAL_MAX_INPUTS, target_inputs=MODAL_TARGET_INPUTS)`
- `enable_memory_snapshot=True` (default)
- `experimental_options={"enable_gpu_snapshot": True}` when `ENABLE_GPU_SNAPSHOT=1`
- vLLM flags include:
  - `--max-model-len 4096`
  - `--gpu-memory-utilization 0.70`
  - `--enforce-eager`

Why this matters:

- Input concurrency keeps lightweight routes responsive while long inference runs.
- `--enforce-eager` gives more predictable startup behavior for this workload.
- 5-minute scaledown window trims idle spend while keeping warm sessions practical.
- CPU memory snapshots are enabled by default; GPU snapshots are opt-in.

Current recommendation:

- Keep `ENABLE_GPU_SNAPSHOT=0` in production unless explicitly testing GPU snapshot alpha behavior.

## Exposed Backend Endpoints

- `GET /health`
- `GET /vllm-metrics` (debug queue/throughput signals)
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

Optional backend env vars:

- `ENABLE_MEMORY_SNAPSHOT` (`1`/`0`, default `1`)
- `ENABLE_GPU_SNAPSHOT` (`1`/`0`, default `0`, alpha)
- `RAG_CACHE_TTL_SECONDS` (default `900`)
- `RAG_CACHE_MAX_ENTRIES` (default `256`)
- `MODAL_MAX_CONTAINERS` (default `1`)
- `MODAL_MAX_INPUTS` (default `8`)
- `MODAL_TARGET_INPUTS` (default `4`)

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
4. Run `logchecklist.md` against Modal + Vercel logs.

## Latest Patch (Sessions 27-33)

Applied from `NEXT_PATCH_PLAN.md` plus follow-up production hardening:

- RAG retrieval query now clamps to `<=480` chars before `retrieve()` (security max remains `500` in retriever).
- Token budgets rebalanced to reduce concise retries:
  - `/differential`: first pass `1152`, concise retry `896`
  - `/summary`: first pass `1664`, concise retry `1280`
- `/health` now includes lightweight counters:
  - `differential_concise_retry_count`
  - `summary_concise_retry_count`
  - `rag_query_blocked_count`
  - `extract_labs_fast_path_count`
  - `extract_labs_llm_fallback_count`
- `/extract-labs-file` now uses deterministic parsing before LLM fallback:
  - `table-fast` for demo-style table PDFs
  - `table-full` and `flat-full` for broader real-world PDF layouts
- Debate citation normalization expanded for unknown-source guidelines (PMC/PubMed + major guideline organizations).
- Frontend warmup + analyze flow now degrades gracefully:
  - warmup pings: immediate -> ~2 min -> one fallback
  - analyze uses partial success handling so image results are kept even if labs fail

## Cold Start Strategy

Current behavior:

- Frontend warmup sends an immediate health ping, then backoff polling.
- Warmup sequence in UI logic: immediate -> ~2 minutes -> one fallback check.
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
- Deterministic lab extraction path before generative fallback for PDF lab reports.
- Debate prompt compaction (round/history/image/RAG trims) to stay under context limit.
- Debate hard failures return HTTP 500 (enables frontend Retry UX).

## Smoke Test Baseline (Session 33)

Latest production smoke check (`/extract-labs-file`) against deployed endpoint:

- `frontend/public/test-data/melanoma-labs.pdf` -> `10` labs, `0` abnormal
- `frontend/public/test-data/pneumonia-labs.pdf` -> `8` labs, `6` abnormal
- `frontend/public/test-data/sepsis-labs.pdf` -> `8` labs, `8` abnormal
- `sterling-accuris-pathology-sample-report-unlocked.pdf` -> `16` labs, `7` abnormal
- `Lab Report Example.pdf` -> `14` labs, `0` abnormal
- `/health` counter deltas after run:
  - `extract_labs_fast_path_count`: `+5`
  - `extract_labs_llm_fallback_count`: `0`

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
  - `scaledown_window=300`
  - single-container cap during cold start
  - CPU snapshot default + optional GPU snapshot for cold-start reduction

## Source of Truth

- Runtime behavior: `modal_backend/app.py`
- Orchestrator behavior: `modal_backend/gemini_orchestrator_modal.py`
- Session history and fixes: `CHANGELOG.md`
- Next patch queue: `NEXT_PATCH_PLAN.md`
