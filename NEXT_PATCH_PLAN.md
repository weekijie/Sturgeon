# Next Patch Plan (Session 27)

This file captures the exact follow-up patch to continue from the Feb 23 deployment audit.

## Goal

- Reduce retry churn in `/differential` and `/summary`
- Stop RAG query-length blocks (`max 500 chars`)
- Add lightweight counters so checklist verification is faster next time

## Proposed Changes

### 1) RAG Query-Length Clamp (high priority)

File: `modal_backend/app.py`

- In `_retrieve_rag_context(...)`, clamp composed `rag_query` before retrieval.
- Target max length: `<= 480` chars (keeps margin under retriever limit of 500).
- Keep `rag_retriever.py` security guard as-is (do not loosen).

Expected outcome:
- Remove `SECURITY [BLOCKED] ... Query exceeds maximum length of 500 characters` for normal debate turns.
- Improve `has_guidelines=true` rate in long debate prompts.

### 2) Reduce Retry Churn (balanced token tuning)

File: `modal_backend/app.py`

Differential path:
- First pass: `max_tokens` from `1024` to `1152`
- Concise retry: `768` to `896`

Summary path:
- First pass: `1536` to `1664`
- Concise retry: `1152` to `1280`

Expected outcome:
- Fewer concise retries while staying within current latency envelope.

### 3) Add Health Counters (observability)

File: `modal_backend/app.py`

- Track and expose in `/health`:
  - `differential_concise_retry_count`
  - `summary_concise_retry_count`
  - `rag_query_blocked_count`

Expected outcome:
- Faster `logchecklist.md` validation without deep log grep every run.

## Validation Checklist (after deploy)

1. No increase in 5xx/504 on Vercel API routes.
2. `modallog.txt` shows fewer concise retry warnings.
3. No `Query exceeds maximum length of 500 characters` in standard 3-case run.
4. SLOs remain within targets in `logchecklist.md`.
5. Differential still returns 3-4 diagnoses in demo flows.

## Current Runtime Recommendation

- Keep CPU snapshot default:
  - `ENABLE_MEMORY_SNAPSHOT=1`
  - `ENABLE_GPU_SNAPSHOT=0`

Use GPU snapshot only for explicit experimental testing.
