# Sturgeon - Changelog

All notable changes to this project will be documented in this file.

## [2026-02-23] Session 33 - Post-Deploy Smoke Recheck (Demo + Local PDFs)

### Verification (Modal Production)

- Re-ran `/extract-labs-file` smoke tests against deployed backend endpoint from `.env.local`:
  - `frontend/public/test-data/melanoma-labs.pdf` -> `10` labs, `0` abnormal
  - `frontend/public/test-data/pneumonia-labs.pdf` -> `8` labs, `6` abnormal
  - `frontend/public/test-data/sepsis-labs.pdf` -> `8` labs, `8` abnormal
  - `sterling-accuris-pathology-sample-report-unlocked.pdf` -> `16` labs, `7` abnormal
  - `Lab Report Example.pdf` -> `14` labs, `0` abnormal
- Confirmed new `/health` extraction counters are active post-deploy:
  - `extract_labs_fast_path_count` delta: `+5`
  - `extract_labs_llm_fallback_count` delta: `0`

### Problems Encountered (Required Session Notes)

1. **Problem**: Initial `/health` probe returned redirect status (`303`) before the final post-run check.
   - **Why**: Endpoint canonicalization/redirect behavior on the first request path normalization.
   - **Resolution**: Continued smoke flow and used the post-run `/health` response (`200`) as source of truth for counters.
   - **Lesson**: For deployment checklisting, rely on final resolved `/health` payload and counter deltas rather than first probe status alone.

## [2026-02-23] Session 32 - Demo-First Lab Parser Hardening + Robust Local PDF Fallback

### Backend (modal_backend)

#### Changed
- **`/extract-labs-file` now uses a deterministic multi-parser selection before LLM fallback** (`modal_backend/app.py`):
  - Added stricter deterministic extraction pipeline that scores and selects the best candidate from:
    - `table-fast` (compact table text, demo-speed path)
    - `table-full` (full extracted table/text context)
    - `flat-full` (space-delimited line parser for reports where table extraction is weak)
  - Increased deterministic quality guards to reduce false positives from metadata rows (for example `Number`, `Age`, patient header blocks).
  - Added explicit test-name, unit, reference-range, and status-hint confidence heuristics before accepting parsed rows.
- **Improved PDF text strategy without sacrificing demo speed** (`modal_backend/app.py`):
  - Endpoint now keeps both:
    - lean text (`raw_text`) for fast deterministic parse
    - full context text (`raw_text_full`) for robust fallback behavior
  - LLM fallback now uses expanded compact text (`max_chars=9000`, `max_lines=320`) to recover more values from long real-world PDFs when deterministic paths are insufficient.
- **Health observability counters extended** (`modal_backend/app.py`):
  - Added:
    - `extract_labs_fast_path_count`
    - `extract_labs_llm_fallback_count`
  - Exposed both under `/health -> counters`.

### Verification
- `.venv/Scripts/python -m py_compile modal_backend/app.py`
- `.venv/Scripts/python -c "...extract parser functions from modal_backend/app.py and run against: frontend/public/test-data/*.pdf, sterling-accuris-pathology-sample-report-unlocked.pdf, Lab Report Example.pdf..."`
  - Demo PDFs: deterministic `table-fast` path selected with expected lab counts and abnormal flags.
  - Local PDFs: deterministic extraction now returns broad lab sets (`flat-full` for Sterling, `table-fast` for MedScan sample) instead of prior metadata false positives.

### Problems Encountered (Required Session Notes)

1. **Problem**: Deterministic parser still accepted metadata-like table rows in some PDFs.
   - **Why**: Initial table parser trusted column count and numeric parsing too heavily, so rows like administrative headers could pass.
   - **Resolution**: Added stricter lab-name filtering, signal scoring (unit/reference/status/analyte hints), and raised acceptance thresholds.
   - **Lesson**: Fast-path deterministic extraction must include semantic row validation, not just structural validation.

2. **Problem**: Compact prompt fallback missed valid labs in longer local reports.
   - **Why**: Previous fallback used aggressively compacted text intended for speed-focused demo flows.
   - **Resolution**: Added dual raw-text tracks (`raw_text` + `raw_text_full`) and expanded fallback compaction budget for LLM parsing.
   - **Workaround**: Keep deterministic parser first for demo latency, then use fuller fallback context only when needed.

3. **Problem**: Remote `/health` did not expose new extraction counters during smoke tests.
   - **Why**: Smoke endpoint was running a previously deployed backend revision that did not yet include Session 32 fields.
   - **Resolution**: Verified functionality against local source-level parser harness and noted deployment dependency for live counter validation.
   - **Workaround**: Re-run smoke checklist after deploying updated `modal_backend/app.py` to confirm `extract_labs_fast_path_count` and `extract_labs_llm_fallback_count` deltas.

## [2026-02-23] Session 31 - Deterministic Table Parser for Demo PDF Lab Extraction

### Backend (modal_backend)

#### Fixed
- **`/extract-labs-file` malformed JSON fallback on simple table PDFs** (`modal_backend/app.py`):
  - Added deterministic table parser for `|`-delimited lab report lines.
  - New fast-path parses `test | result | reference | interpretation` directly into `lab_values` with normalized statuses (`high|low|normal`).
  - Fast-path short-circuits LLM extraction when >=2 labs are parsed, avoiding markdown-formatted pseudo-JSON failures.
  - Preserves existing MedGemma extraction path as fallback for non-tabular reports.

### Verification
- `.venv/Scripts/python -m py_compile modal_backend/app.py`

### Problems Encountered (Required Session Notes)

1. **Problem**: Generated demo PDFs contained clean text rows, but extraction returned only partial labs (often one row).
   - **Why**: MedGemma occasionally returned markdown bullet lists with inline JSON fragments instead of a single valid JSON object; repair logic recovered partial data.
   - **Resolution**: Added deterministic parser for simple table-formatted reports before the LLM call.
   - **Lesson**: For predictable structured inputs, deterministic extraction should run before generative parsing.

2. **Problem**: Lab extraction latency remained high despite compact prompts.
   - **Why**: Requests still paid full generation latency when deterministic parsing was sufficient.
   - **Resolution**: Fast-path now bypasses LLM for table-shaped reports, reducing both latency and parse fragility.
   - **Workaround**: Keep LLM fallback for unstructured or OCR-like reports.

## [2026-02-23] Session 30 - Warmup Poll Simplification + Partial Success Analyze Flow

### Frontend

#### Fixed
- **Analyze flow now preserves partial success** (`frontend/app/page.tsx`):
  - Switched analyze step from `Promise.all(...)` to `Promise.allSettled(...)` for image + lab requests.
  - If one request fails (for example `/extract-labs` timeout during cold start), successful results from the other request are still applied.
  - Added guarded continuation logic so differential generation proceeds when at least one usable evidence source is available.
- **Extract-labs route timeout alignment** (`frontend/app/api/extract-labs/route.ts`):
  - Increased timeout from `120000ms` to `295000ms` to match long-running backend cold/queue windows.
  - Added `runtime="nodejs"` and `maxDuration=300` for parity with other long AI routes.
- **Warmup health polling behavior simplified** (`frontend/lib/useWarmup.ts`, `frontend/components/WarmupToast.tsx`):
  - Poll sequence now: immediate ping, then ~2 minute check, then one fallback check.
  - Reduced warmup attempts from 5 to 3 to limit repeated health-check noise and credit overhead.
  - Updated toast copy to reflect new polling schedule.

### Verification
- `npm --prefix frontend run lint -- app/page.tsx app/api/extract-labs/route.ts lib/useWarmup.ts components/WarmupToast.tsx`

### Problems Encountered (Required Session Notes)

1. **Problem**: When `/extract-labs` timed out during cold start, image analysis success was effectively discarded in UX.
   - **Why**: `Promise.all(...)` rejects on first failure, so downstream handling never applied completed sibling results.
   - **Resolution**: Switched to `Promise.allSettled(...)` and processed fulfilled results independently.
   - **Lesson**: Parallel multimodal pipelines should degrade gracefully under partial failure, not fail closed.

2. **Problem**: Frequent `/health` checks created noisy 503 runs during predictable cold-start windows.
   - **Why**: Prior backoff schedule (20s/30s/45s with 5 attempts) probed too aggressively before inference stack was realistically ready.
   - **Resolution**: Moved to immediate + 2-minute + one fallback polling schedule.
   - **Workaround**: Treat initial Analyze as the real warmup trigger; keep health checks sparse.

## [2026-02-23] Session 29 - Demo PDF Labs + Extract-Labs-File Speed Pass

### Frontend

#### Added
- **Demo lab report PDFs** (`frontend/public/test-data/`):
  - `melanoma-labs.pdf`
  - `pneumonia-labs.pdf`
  - `sepsis-labs.pdf`
- **PDF generation utility** (`generate_demo_lab_pdfs.py`):
  - Deterministic text-PDF generator for regenerating demo lab files from source strings.

#### Changed
- **Demo case model and loaders** (`frontend/lib/demo-cases.ts`):
  - Added optional `labFile` to `DemoCase`.
  - Wired all three demo cases to PDF lab files in `frontend/public/test-data/`.
  - Added `loadDemoLabFile()` helper to load demo PDFs as `File` objects.
- **Upload page demo-case behavior** (`frontend/app/page.tsx`):
  - `loadDemoCase()` now prefers loading demo PDF lab files into `labFile` state.
  - Falls back to embedded `labValues` only when demo PDF load fails.
  - Removed stale note claiming labs are embedded in patient history.

### Backend (modal_backend)

#### Changed
- **`/extract-labs-file` speed-focused compaction pass** (`modal_backend/app.py`):
  - Added `_compact_lab_report_text()` to dedupe/normalize lines and keep high-signal lab content.
  - Reduced PDF text duplication by skipping `page.extract_text()` when table extraction is present on that page.
  - Added extraction-stage observability logs:
    - `extract-labs-file text prepared` (parse duration + raw/compact char counts)
    - `extract-labs-file model completed` (LLM duration)
  - Reduced output budget for file extraction:
    - first pass `max_tokens`: `2048 -> 1024`
    - retry `max_tokens`: `2048 -> 768`
  - Added concise extraction instruction to keep JSON compact while preserving explicit lab values only.

### Verification
- `.venv/Scripts/python -m py_compile modal_backend/app.py generate_demo_lab_pdfs.py`
- `npm --prefix frontend run lint -- app/page.tsx lib/demo-cases.ts` (passes; one existing `no-img-element` warning in upload page)
- `.venv/Scripts/python -c "...pdfplumber..."` sanity check confirms all 3 generated PDFs are text-extractable.

### Problems Encountered (Required Session Notes)

1. **Problem**: Demo cases did not exercise real PDF extraction path.
   - **Why**: Demo preload injected `labValues` directly into state instead of loading a lab `File`.
   - **Resolution**: Added `labFile` support and switched demo load path to file-first behavior.
   - **Lesson**: Demo fixtures should execute the same path judges will evaluate, not a shortcut path.

2. **Problem**: PDF lab extraction latency was disproportionately high versus image analysis.
   - **Why**: File extraction used large output budget and verbose/duplicated PDF text payload (tables + full page text).
   - **Resolution**: Added text compaction/dedupe, reduced token caps, and added stage timing logs for parse vs model time.
   - **Workaround**: For critical live demos, preload warm container and avoid concurrent heavy endpoints on first turn.

## [2026-02-23] Session 28 - CAP Citation Mapping Fix (Modal Orchestrator)

### Backend (modal_backend)

#### Fixed
- **Pneumonia guideline citation drop in debate turns** (`modal_backend/gemini_orchestrator_modal.py`, `modal_backend/app.py`):
  - Expanded fallback citation source mapping so extracted citations can resolve URLs for `PMC/PubMed`, `IDSA`, `ATS`, `BTS`, `SCCM`, `ESICM`, `SSC`, `NCCN`, `ASCO`, `ESMO`, `AAD`, `ACR`, `ADA`, `AHA`, `ACC`, `CHEST`, and `NICE` when alias matching misses.
  - Added explicit fallback handling for `PRIMARY CARE CLINICS` and `PUBMED CENTRAL` citation text variants to map to `PMC` URL.
  - Added warning logs when raw citations are extracted but all are dropped by URL normalization:
    - `All orchestrator citations dropped after URL normalization`
    - `All fallback citations dropped after URL normalization`

### Compliance
- No new external tools, datasets, or paid dependencies added.
- Changes remain within existing approved stack and licensing constraints in `CLAUDE.md`.

### Verification
- Syntax checks passed with virtualenv Python:
  - `.venv/Scripts/python -m py_compile modal_backend/gemini_orchestrator_modal.py`
  - `.venv/Scripts/python -m py_compile modal_backend/app.py`

### Problems Encountered (Required Session Notes)

1. **Problem**: RAG retrieval succeeded for CAP/sepsis turns, but guideline links intermittently disappeared in UI.
   - **Why**: Citation extraction returned text like `PMC Guidelines ...`, but fallback source inference did not map `PMC`/`PubMed` to a valid URL in unknown-source cases.
   - **Resolution**: Added broader fallback source mapping for major medical organizations and PubMed/PMC variants.
   - **Lesson**: Retrieval quality and citation-link quality are separate stages; both need explicit observability and robust mapping.

2. **Problem**: Citation failures were hard to distinguish from retrieval failures during fast log review.
   - **Why**: Existing logs showed retrieval success but did not show citation-drop events after URL filtering.
   - **Resolution**: Added targeted warnings when extracted citations are fully dropped by normalization.
   - **Workaround**: Continue checking `rag_audit` alongside `has_guidelines` and new normalization warnings during demo-case validation.

## [2026-02-23] Session 27 - NEXT_PATCH_PLAN Implementation (RAG Clamp + Retry Counters)

### Backend (modal_backend)

#### Changed
- **RAG query-length clamp** (`modal_backend/app.py`):
  - Added `_clamp_rag_query()` and enforced `rag_query_max_chars=480` before retriever calls in `_retrieve_rag_context(...)`.
  - Preserved clinical-context suffix where possible while trimming long challenge text first.
  - Kept `rag_retriever.py` length/security validation unchanged.
- **Retry churn tuning** (`modal_backend/app.py`):
  - `/differential` first pass `max_tokens`: `1024 -> 1152`
  - `/differential` concise retry `max_tokens`: `768 -> 896`
  - `/summary` first pass `max_tokens`: `1536 -> 1664`
  - `/summary` concise retry `max_tokens`: `1152 -> 1280`
- **Health counters for quick audit checks** (`modal_backend/app.py`):
  - Added runtime counters:
    - `differential_concise_retry_count`
    - `summary_concise_retry_count`
    - `rag_query_blocked_count`
  - Exposed all three under `/health -> counters`.

### Verification
- Syntax check passed with virtualenv Python:
  - `.venv/Scripts/python -m py_compile modal_backend/app.py`

### Problems Encountered (Required Session Notes)

1. **Problem**: Naive truncation risked dropping the diagnosis context appended to RAG queries.
   - **Why**: Original query composition appends `Clinical context` at the end, so simple end-trim can remove high-value differential hints.
   - **Resolution**: Applied a two-step clamp that trims challenge text first, then re-clamps final query to `<=480` chars.
   - **Lesson**: Clamp strategy should preserve semantically dense suffixes, not just character count.

2. **Problem**: Retry/block telemetry required lightweight visibility without introducing heavy logging dependencies.
   - **Why**: Post-deploy checklist validation currently relies on deep log scans.
   - **Resolution**: Added in-memory counters and exposed them directly in `/health` for fast checks.
   - **Workaround**: Counters are per-container runtime metrics (reset on cold start), so pair with log samples for long-window audits.

## [2026-02-23] Session 26 — Post-Deploy Logchecklist Audit (CPU Snapshot Run)

### Verification Scope
- Audited production behavior using `logchecklist.md` against:
  - `modallog.txt`
  - `sturgeon-log-export-2026-02-22T16-25-15.json`
  - Modal invocation timing table from production run

### Results
- **CPU snapshot mode stable**:
  - `enable_memory_snapshot=true`, `enable_gpu_snapshot=false`
  - No GPU snapshot NCCL broken-pipe failure pattern observed in this run.
- **Queue/concurrency behavior improved**:
  - vLLM telemetry repeatedly showed `Running: 2 reqs, Waiting: 0 reqs`.
  - Warm-path health checks remained responsive (~100-300ms execution).
- **Latency SLOs improved**:
  - `/analyze-image`: ~16s-33s in sampled runs (well under target)
  - `/differential`: ~43s-72s in sampled runs (under target)
  - `/summary`: ~42s-53s in sampled runs (under target)
  - `/debate-turn`: mostly ~36s-61s (p95 within target; p50 still near threshold)
- **Functional correctness**:
  - Differential outputs returned 3 diagnoses in sampled runs.
  - Debate and summary flows completed with HTTP 200.

### Issues Still Open
- **Retry churn** remains elevated:
  - Frequent `Differential output likely truncated; retrying with concise JSON constraints`
  - Frequent `Summary output likely truncated; retrying with concise JSON constraints`
- **RAG query length guard** can block retrieval on long prompts:
  - `SECURITY [BLOCKED] ... Query exceeds maximum length of 500 characters`
  - Some blocked turns correlate with `has_guidelines=false` in final debate response.

### Documentation Added
- Added `NEXT_PATCH_PLAN.md` with concrete follow-up patch plan for the next session.
- Updated `README.md`, `CLAUDE.md`, `STURGEON_PROJECT_PLAN.md`, and `DEPLOYMENT.md` with this session's deployment stabilization status and next patch direction.

### Problems Encountered (Required Session Notes)

1. **Problem**: GPU snapshot path was unstable for this workload during earlier production tests.
   - **Why**: Alpha GPU snapshot behavior plus vLLM/NCCL subprocess lifecycle interactions produced instability.
   - **Resolution**: Continued with CPU snapshots as default production mode for reliability.
   - **Lesson**: Treat GPU snapshots as experimental until repeated production runs are clean.

2. **Problem**: RAG retrieval was occasionally blocked despite healthy core inference.
   - **Why**: Constructed retrieval query exceeded retriever max length (500 chars).
   - **Resolution**: Prepared explicit follow-up patch to truncate retrieval query before `retrieve()` call.
   - **Workaround**: Keep debate challenge prompts concise where possible until patch is applied.

## [2026-02-22] Session 25 — Queue/Timeout Mitigation for Vercel 504s

### Backend (modal_backend)

#### Changed
- **Modal input concurrency enabled** (`modal_backend/app.py`):
  - Added class-level `@modal.concurrent(max_inputs=..., target_inputs=...)` for the ASGI service.
  - Added env-tunable scaling/concurrency settings:
    - `MODAL_MAX_CONTAINERS` (default `1`)
    - `MODAL_MAX_INPUTS` (default `8`)
    - `MODAL_TARGET_INPUTS` (default `4`)
- **Queue observability endpoint** (`modal_backend/app.py`):
  - Added `GET /vllm-metrics` to expose selected queue/latency counters from vLLM `/metrics`.
  - Added concurrency config fields to `/health` for runtime visibility.
- **Differential tail-latency tuning** (`modal_backend/app.py`):
  - Tightened default output budget and compactness constraints.
  - Reduced retry token budgets to avoid multi-minute decode tails.

### Frontend (Vercel API routes)

#### Changed
- **Timeout alignment for long-running routes**:
  - Added `runtime="nodejs"` + `maxDuration=300` to `analyze-image`, `differential`, `debate-turn`, and `summary` routes.
  - Increased backend fetch timeout for `analyze-image` and `differential` to `295000ms`.
- **Health-probe pressure control** (`frontend/app/api/health/route.ts`):
  - Added 5s backend timeout to fail fast instead of waiting on long queue stalls.

### Documentation

#### Updated
- `DEPLOYMENT.md` and `modal_backend/README.md` updated with new concurrency env vars and `vllm-metrics` endpoint.

### Problems Encountered (Required Session Notes)

1. **Problem**: Vercel returned 504 while Modal later completed successfully.
   - **Why**: Frontend route timeout elapsed while request was still queued/running on backend.
   - **Resolution**: Increased route max duration/timeout and enabled backend input concurrency.
   - **Lesson**: Timeout budgets must include queue time, not just execution time.

2. **Problem**: Warmup health checks showed long wall-clock durations with tiny execution time.
   - **Why**: Health requests were waiting behind long inference work in a single-lane input path.
   - **Resolution**: Enabled input concurrency and made health route fail fast at 5 seconds on frontend.
   - **Workaround**: Monitor `GET /vllm-metrics` during load to confirm queue behavior.

## [2026-02-22] Session 24 — Snapshot Modes (CPU Default, GPU Opt-In) + RAG Query Cache

### Backend (modal_backend)

#### Changed
- **Snapshot-capable Modal class config** (`modal_backend/app.py`):
  - Added env-driven snapshot toggles:
    - `ENABLE_MEMORY_SNAPSHOT` (default `true`)
    - `ENABLE_GPU_SNAPSHOT` (default `false`, opt-in)
  - Wired `@app.cls(...)` with `enable_memory_snapshot` and optional `experimental_options={"enable_gpu_snapshot": True}`.
  - Split lifecycle into `@modal.enter(snap=True)` + `@modal.enter(snap=False)` phases for snapshot-safe startup.

- **vLLM runtime cache volume** (`modal_backend/app.py`):
  - Added persistent volume mount at `/root/.cache/vllm` (`vllm-cache`) to retain vLLM runtime artifacts.
  - Added `HF_XET_HIGH_PERFORMANCE=1` for faster Hugging Face transfer behavior.

- **RAG retrieval query cache** (`modal_backend/app.py`):
  - Added bounded in-memory LRU-style cache for debate retrieval contexts.
  - Added configurable cache controls:
    - `RAG_CACHE_TTL_SECONDS` (default `900`)
    - `RAG_CACHE_MAX_ENTRIES` (default `256`)
  - Added health visibility for cache hit/miss and entry counts.

- **Dependency baseline refresh** (`modal_backend/app.py`, `modal_backend/requirements.txt`):
  - Updated vLLM floor to `>=0.13.0`.
  - Added `huggingface-hub>=0.36.0` explicit dependency.

### Documentation

#### Updated
- `DEPLOYMENT.md`:
  - Synced runtime config to current values (`scaledown_window=300`, snapshot settings, `vllm-cache` volume).
  - Added optional env vars for snapshot and RAG cache tuning.
- `modal_backend/README.md`:
  - Added snapshot mode documentation and RAG cache env settings.
  - Added `vllm-cache` volume description.

### Problems Encountered (Required Session Notes)

1. **Problem**: Snapshot support was requested, but existing startup path used a single `@modal.enter()` flow.
   - **Why**: Server startup, runtime state, and dependency initialization were tightly coupled.
   - **Resolution**: Split startup lifecycle into snapshot-phase + restore-phase hooks with explicit mode handling.
   - **Lesson**: Snapshot-ready deployments need phase-aware init design, not a single monolithic startup hook.

2. **Problem**: Repeated similar debate prompts paid retrieval cost repeatedly.
   - **Why**: RAG retrieval had persistent index cache, but no short-lived query-result cache.
   - **Resolution**: Added bounded TTL query cache with deterministic keying from challenge + differential context.
   - **Workaround**: Tune TTL/entry limits if stale context or memory pressure appears.

## [2026-02-22] Session 23 — Token Budget Pre-Clamp, Endpoint Speed Tuning, and Cost-Aware Warmup

### Backend (modal_backend)

#### Changed
- **vLLM pre-clamp before first request** (`modal_backend/app.py`, `modal_backend/gemini_orchestrator_modal.py`):
  - Added estimated input-token budgeting to clamp `max_tokens` proactively before first call.
  - Kept existing overflow retry logic as fallback.
- **Token budget tuning for latency/quality balance**:
  - `/differential`: `3072 -> 1792` default, retry down to `1536`, concise retry path at `1280`.
  - `/summary`: `3072 -> 1536` default, concise retry path at `1152`.
  - Debate MedGemma fallback: `2048 -> 1200` (retry `1024`).
  - Orchestrator MedGemma query default now pre-clamped from a lower target (`1200`).
  - `/analyze-image`: `768 -> 512` (retry `320`).
- **Context compaction**:
  - Added summary-specific debate round compaction (latest 4 rounds, capped challenge/response lengths).
  - Added truncation caps for summary and differential prompt sections (history/labs/differential/rounds).
  - `/analyze-image` prompt now uses compact triage summary and tighter concise-output instructions.
- **RAG retrieval relevance hardening** (`modal_backend/app.py`):
  - Debate retrieval call lowered to `top_k=8`.
  - Added lightweight topic hints from challenge + differential names.
  - Added diversity selector (limits repeated topic/source chunks) before prompt injection.
- **Runtime/cost config**:
  - Modal `scaledown_window`: `600 -> 300`.
  - Replaced deprecated `TRANSFORMERS_CACHE` env with `HF_HOME` in Modal image setup.

### Frontend

#### Changed
- **Cost-aware warmup** (`frontend/lib/useWarmup.ts`, `frontend/components/WarmupToast.tsx`, `frontend/app/page.tsx`):
  - Warmup can now be intent-based via `NEXT_PUBLIC_WARMUP_AUTOSTART`.
  - Upload page now starts warmup on Analyze action (on-demand).
  - Added warmup poll cap (default 5 attempts) and paused-state toast copy for credit-saving behavior.
- **Prompt payload compaction from UI**:
  - Upload flow now caps image-context text injected into differential input (`frontend/app/page.tsx`).
  - Summary request now sends compacted recent debate rounds (`frontend/app/summary/page.tsx`).

### Problems Encountered (Required Session Notes)

1. **Problem**: vLLM overflow retries were still happening after endpoint-level retry logic existed.
   - **Why**: Budgets were only reduced after receiving a 400 overflow response.
   - **Resolution**: Added proactive pre-clamp using estimated input-token sizing before the first vLLM call.
   - **Lesson**: First-pass token budgeting should be preventative, not purely reactive.

2. **Problem**: Speed optimization risked reducing answer quality too aggressively.
   - **Why**: Lower max token caps can truncate structured JSON outputs.
   - **Resolution**: Used balanced caps + concise retry prompts only when truncation is likely.
   - **Lesson**: Pair lower budgets with explicit compact-output constraints and targeted retries.

3. **Problem**: Warmup strategy needed to minimize credit burn while preserving usability for unpredictable judge timing.
   - **Why**: Always-on or frequent auto warmup can consume credits during inactivity windows.
   - **Resolution**: Switched warmup to env-controlled intent-based mode and capped warmup polling attempts.
   - **Workaround**: Keep manual/on-demand warmup before active demo/testing sessions.

## [2026-02-22] Session 22 — Modal/Vercel Deployment Track Consolidation

### Scope
- Consolidated this full deployment-track session into the repo docs and changelog.
- Captured Modal backend creation/evolution, parity restoration, reliability fixes, and frontend deployment UX adjustments.

### Backend (modal_backend) — Consolidated Outcomes

#### Added
- `modal_backend/` production backend stack for Modal deployment:
  - `app.py` (Modal class + ASGI endpoints + vLLM/MedSigLIP subprocess orchestration)
  - `gemini_orchestrator_modal.py` (Gemini orchestration integrated with vLLM-hosted MedGemma)
  - `rate_limiter.py`, `structured_logging.py`, `input_sanitization.py`
  - `rag_retriever.py`, `rag_evaluation.py`, guideline corpus mirror
- Endpoint parity additions vs local backend:
  - `GET /rag-status`
  - `POST /rag-evaluate`
  - `POST /extract-labs-file`

#### Changed
- Cold-start and autoscaling controls:
  - Kept `--enforce-eager`
  - Added `max_containers=1`
  - Frontend warmup switched to immediate ping + progressive backoff polling
- vLLM reliability hardening across endpoints:
  - Centralized non-200 handling for chat calls
  - Auto-retry on `max_tokens` overflow with reduced budget
  - Added input-overflow compaction retry for debate prompts
- Debate/orchestrator hardening:
  - Fixed `Event loop is closed` path by removing nested loop usage in modal orchestrator flow
  - Restored RAG context injection in orchestrated synthesis prompts
  - Added `rag_used` signal to distinguish retrieval usage from citation extraction
- Citation trustworthiness:
  - Citation URL normalization/filtering in backend
  - Only valid `http(s)` citations are returned as linked references

### Frontend — Consolidated Outcomes

#### Added/Changed
- Warmup UX:
  - `frontend/lib/useWarmup.ts`: immediate first ping + 20s/30s/45s backoff + single in-flight guard
  - `frontend/components/WarmupToast.tsx`: updated copy/behavior for backoff strategy
  - `frontend/app/api/health/route.ts`: health proxy with `cache: "no-store"`
- Debate citations UI:
  - Link rendering now gated to valid `http(s)` URLs only
  - Guideline section suppressed when no valid linked citations exist
- Summary loading UI:
  - Removed static spinner
  - Kept larger pulsing loading text

### Documentation

#### Updated
- `CHANGELOG.md`: Added Sessions 18-22 coverage for this deployment track.
- `DEPLOYMENT.md`: Rewritten as current-state source of truth; removed stale/contradictory notes and aligned with runtime behavior (`max_containers=1`, `--enforce-eager`, overflow handling, citation URL gating).
- `README.md`: Added pointer to `DEPLOYMENT.md` for production setup.

### Problems Encountered (Required Session Notes)

1. **Problem**: Deployment backend drifted from local `ai-service` behavior.
   - **Why**: Initial Modal extraction prioritized getting a deployable service online quickly.
   - **Resolution**: Reintroduced missing endpoints, orchestration behavior, retries, and response fields.
   - **Lesson**: Use endpoint parity checks and behavior parity tests before deployment sign-off.

2. **Problem**: vLLM context-limit failures appeared in both `max_tokens` and `input_tokens` forms.
   - **Why**: Long accumulated debate context + high output budgets exceeded 4096 context in realistic turns.
   - **Resolution**: Added adaptive token retries, prompt compaction, and constrained debate context assembly.
   - **Lesson**: Budget full prompt context, not just latest user message.

3. **Problem**: Citations were shown in UI without valid external links.
   - **Why**: Empty/invalid citation URLs were still rendered as links.
   - **Resolution**: Backend citation URL normalization + frontend URL gating.
   - **Lesson**: Never present unverifiable citations as clickable references.

## [2026-02-22] Session 21 — Citation URL Gating & Summary Loading UI Cleanup

### Backend (modal_backend)

#### Fixed
- Added citation URL normalization/filtering in `modal_backend/app.py` for debate responses:
  - Keeps only citations with valid absolute `http(s)` URLs
  - Auto-fills URL from canonical source mapping when source is known but URL is missing
  - Drops citations that cannot be mapped to a valid URL
- Applied normalized citations in both debate paths:
  - Orchestrated (`_debate_turn_orchestrated`)
  - MedGemma fallback (`_debate_turn_medgemma_only`)
- `has_guidelines` now reflects **valid linked citations only** (prevents badge/links for unlinked references)

### Frontend

#### Fixed
- Debate citations rendering hardened in `frontend/app/debate/page.tsx`:
  - Renders citation links only for valid `http(s)` URLs
  - Suppresses guideline section if no valid links exist
- Summary loading UI updated in `frontend/app/summary/page.tsx`:
  - Removed static HeroUI spinner
  - Kept pulsing summary-generation text and increased text prominence (`text-lg`/`text-xl` + semibold)

### Problems Encountered (Required Session Notes)

1. **Problem**: Citation links in debate UI navigated to `https://sturgeon.vercel.app/debate` instead of guideline URLs.
   - **Why**: Empty/invalid citation URLs were rendered as `<a href="">...` and treated as same-page links.
   - **Resolution**: Added backend citation URL normalization and frontend URL validity gating before rendering links.
   - **Lesson**: Citation display should be gated by verifiable URLs, not citation text presence alone.

2. **Problem**: Summary loading spinner appeared as a static non-animated ring.
   - **Why**: Spinner animation utility/class behavior was inconsistent in this runtime/theme setup.
   - **Resolution**: Removed spinner and switched to larger pulsing loading text only.
   - **Workaround**: Prefer CSS-controlled text animation for loading states when third-party spinner animations are inconsistent.

## [2026-02-22] Session 20 — Debate Token Overflow, Orchestrator RAG, and Retry UX Fixes

### Backend (modal_backend)

#### Fixed
- **Debate fallback input overflow handling** (`modal_backend/app.py`):
  - Added prompt compaction path for `input_tokens` overflow errors (`parameter=input_tokens`) in vLLM wrapper.
  - Added compact previous-round formatting (last 2 rounds, truncated text) to reduce prompt growth over long debates.
  - Added compact patient history and image context in MedGemma fallback prompts.
  - Limited RAG context injected into debate prompts to top 4 relevant chunks and trimmed context length.

- **Orchestrator event-loop failure** (`modal_backend/gemini_orchestrator_modal.py`):
  - Removed `asyncio.run(...)` call in orchestrator MedGemma query path.
  - Switched orchestrator HTTP client from async client to sync client for thread-safe usage.
  - Eliminated intermittent `Event loop is closed` fallback trigger.

- **Orchestrator RAG prompt wiring restored** (`modal_backend/gemini_orchestrator_modal.py`):
  - Added synthesis prompt builder that injects retrieved guideline context.
  - Added explicit citation guidance with relevance rule: cite retrieved guidelines only when clinically applicable.
  - Restored query formulation prompt using recent rounds for better focused MedGemma questions.

- **Retry UX restoration** (`modal_backend/app.py`):
  - MedGemma fallback hard failures now raise exceptions to route-level handler.
  - `/debate-turn` now returns HTTP 500 on hard backend failure (instead of synthetic 200 "I encountered a processing error" response), enabling frontend error bubble + Retry button flow.

#### Added
- `rag_used` field in debate responses to differentiate:
  - Retrieval/injection occurred (`rag_used=true`)
  - Citation extraction succeeded (`has_guidelines=true`)

### Problems Encountered (Required Session Notes)

1. **Problem**: Simple debate questions could fail with vLLM input overflow (`request has 5838 input tokens`).
   - **Why**: Prompt assembly included cumulative long context (previous rounds + image context + RAG chunks), not just user question text.
   - **Resolution**: Added prompt compaction and RAG context caps, plus overflow-specific retry behavior.
   - **Lesson**: Debate systems must budget full prompt context, not only latest user input.

2. **Problem**: Orchestrator intermittently failed with `Event loop is closed`, forcing fallback paths.
   - **Why**: Async client + `asyncio.run(...)` usage inside threaded orchestration path caused loop lifecycle mismatch.
   - **Resolution**: Switched to sync vLLM HTTP client in orchestrator and removed `asyncio.run(...)`.
   - **Lesson**: Avoid creating nested event loop boundaries inside thread-executed orchestration code.

## [2026-02-22] Session 19 — vLLM Token Budget Guardrails & Endpoint Hardening

### Backend (modal_backend)

#### Fixed
- Added centralized vLLM call wrapper in `modal_backend/app.py` for all direct MedGemma chat calls:
  - Validates non-200 responses before reading `choices`
  - Prevents `'choices'` KeyError crashes when vLLM returns validation errors
  - Detects max-token overflow errors and auto-retries with reduced token budget
- Applied wrapper to all relevant endpoints and retry paths:
  - `/extract-labs`
  - `/extract-labs-file` (including JSON parse retry call)
  - `/differential` (including hallucination-correction retry call)
  - `/debate-turn` MedGemma fallback (including correction retry call)
  - `/analyze-image` (primary + refusal retry)
  - `/summary`
- Hardened orchestrated debate MedGemma tool call in `modal_backend/gemini_orchestrator_modal.py`:
  - Added the same overflow-aware retry behavior for `query_medgemma()`
  - Prevents hidden failures when orchestrator context gets long

#### Performance
- Reduced `/analyze-image` generation output budget:
  - Primary MedGemma image analysis: 2048 -> 768 max tokens
  - Refusal-retry analysis: 2048 -> 512 max tokens
- Added image downscaling before vLLM multimodal request when input is very large (`max side = 1024`) to reduce image token cost and latency.

### Problems Encountered (Required Session Notes)

1. **Problem**: `/differential` returned 500 when vLLM rejected `max_tokens=3072` for long prompts.
   - **Why**: vLLM enforces context budget (`input_tokens + max_tokens <= max_model_len`), and the endpoint read `response.json()["choices"]` even on non-200 errors.
   - **Resolution**: Added centralized vLLM response/error handling + overflow-aware retry with reduced max tokens.
   - **Lesson**: Keep high desired output caps for JSON completeness, but enforce adaptive per-request token budgeting.

2. **Problem**: `/analyze-image` latency spiked (~1m+).
   - **Why**: High output token budget and large multimodal input increased generation/prefill cost.
   - **Resolution**: Reduced output budgets and downscaled large images before MedGemma call.
   - **Workaround**: Maintain concise output format for first-pass image analysis; reserve deeper analysis for follow-up turns.

## [2026-02-22] Session 18 — Modal Backend Parity Restoration

### Backend (modal_backend)

#### Restored
- Endpoint parity with local backend in `modal_backend/app.py`:
  - Added `GET /rag-status`
  - Added `POST /rag-evaluate`
  - Added `POST /extract-labs-file`
- Re-enabled Gemini orchestrated debate path with session state:
  - `debate-turn` now uses orchestrator when available, with MedGemma fallback
  - Restored `orchestrated`, `session_id`, `citations`, and `has_guidelines` response behavior
- Restored hallucination correction retries:
  - Differential endpoint now retries with correction constraints on detected fabrication
  - Debate fallback now retries corrected JSON when hallucinations are detected
- Restored token limits to local parity:
  - Differential `max_tokens`: 2048 -> 3072
  - Summary `max_tokens`: 2048 -> 3072
- Restored image refusal handling:
  - Added `is_pure_refusal()` retry path
  - Added `strip_refusal_preamble()` cleanup
- Restored lab file parsing flow (`.pdf` + `.txt`) with retry-on-JSON-parse-failure behavior
- Added `modal_backend/rag_evaluation.py` to support `/rag-evaluate` in Modal deployment

#### Reliability/Scaling
- Kept `max_containers=1` in `@app.cls(...)` to prevent duplicate cold-start containers.

### Frontend

#### Changed
- Warmup polling behavior (`frontend/lib/useWarmup.ts`):
  - Immediate first health ping
  - Progressive backoff polling (20s -> 30s -> 45s)
  - Single in-flight guard to avoid overlapping health checks
- Warmup toast copy updated to match backoff strategy (`frontend/components/WarmupToast.tsx`)
- Health proxy route uses `cache: "no-store"` (`frontend/app/api/health/route.ts`)

### Documentation

#### Updated
- `DEPLOYMENT.md` synced with current implementation:
  - Added `max_containers=1` rationale/config snippet
  - Replaced stale "60s warmup delay" docs with immediate ping + backoff strategy
  - Fixed stale CORS note (`allow_origins=["*"]` -> restricted origins)
  - Corrected stale `scaledown_window` note (300s -> 600s)
  - Added missing endpoint references (`/extract-labs-file`, `/rag-status`, `/rag-evaluate`)

### Problems Encountered (Required Session Notes)

1. **Problem**: Modal backend had feature drift from `ai-service` (missing endpoints + orchestrated path disabled).
   - **Why**: Initial Modal port prioritized deployment simplicity and omitted some local behaviors.
   - **Resolution**: Reintroduced missing endpoints and restored orchestration/fallback parity in `modal_backend/app.py`.
   - **Lesson**: Keep endpoint parity checks (`grep @app.post/@app.get`) as part of deployment readiness.

2. **Problem**: Cold-start health checks could trigger container fan-out.
   - **Why**: Repeated health probes during long model startup can be interpreted as scale demand.
   - **Resolution**: Combined backend cap (`max_containers=1`) with frontend immediate+backoff warmup polling.
   - **Lesson**: Use both platform autoscaling controls and client polling discipline together.

3. **Problem**: Frontend lint rule (`react-hooks/set-state-in-effect`) failed on warmup toast state updates.
   - **Why**: Synchronous `setState` calls inside `useEffect` are disallowed by the current lint config.
   - **Resolution**: Simplified toast visibility logic to avoid effect-driven synchronous state updates.
   - **Workaround**: Keep transient ready-state UX simple unless introducing a reducer/timer-driven state machine.

## [2026-02-22] Session 17 — Systematic Review Corpus Expansion

### Added
- `ai-service/guidelines/systematic_reviews/pneumonia_antibiotics_sr.md`:
  - CAP antibiotic effectiveness rankings (network meta-analysis)
  - CURB-65 severity assessment scoring table
  - Treatment recommendations by patient risk/setting
  - Duration guidance and antimicrobial stewardship principles
- `ai-service/guidelines/systematic_reviews/sepsis_qsofa_sr.md`:
  - SOFA vs SIRS vs qSOFA mortality prediction comparison
  - Complete scoring tables (SOFA, qSOFA, SIRS)
  - Sensitivity/specificity pooled analysis
  - Clinical integration strategy and timing recommendations

### Changed
- Corpus expanded: 12 guidelines + 3 systematic reviews (Guide-RAG GS-4 config)
- All 3 demo cases (Melanoma, Pneumonia, Sepsis) now have matching guidelines + SRs

---

## [2026-02-21] Session 16 — Documentation & Process Improvements
### Documentation
#### Added
- **Development Methodology** (`CLAUDE.md`):
  - Added guideline #13: **Document problems encountered**
  - Requires documenting in CHANGELOG.md under session entry:
    - The problem/issue faced
    - Why it happened (if understood)
    - How it was resolved
    - Any workarounds or lessons learned
---

## [2026-02-21] Session 15 — Hallucination Hardening, HeroUI v3 Upgrade & Backend Safety
### Backend
#### Fixed
- **Prompt Guardrails** (`ai-service/prompts.py`):
  - Removed hardcoded ferritin example from SYSTEM_PROMPT ("Based on the elevated ferritin of 847...")
  - Changed to generic "[value]" placeholder
  - Non-RAG prompts no longer request guideline citations (prevents fabricated citations)
- **MedGemma CPU Precision** (`ai-service/medgemma.py`):
  - Added explicit float32 fallback for CPU inference (was using float16 which can cause issues)
  - ROCm/AMD still uses bfloat16 as required
- **MedSigLIP Safety** (`ai-service/medsiglip.py`):
  - Added `model.eval()` for inference mode
  - Skip wrong label set for unknown modalities instead of applying chest X-ray labels
- **Hallucination Detection** (`ai-service/hallucination_check.py`):
  - Added position tracking in extracted values for accurate lab matching
  - Added unit normalization (`normalize_unit()`) for cross-unit comparison
  - Added patient history value extraction to allowed values
  - Fixed lab name matching with word boundary regex
- **Session Management** (`ai-service/main.py`):
  - Added `MAX_SESSIONS` cap (500) with LRU eviction
  - Trimmed CORS origins whitespace
  - Added guard for `/rag-evaluate` endpoint (requires `ENABLE_RAG_EVAL` env var)
  - Added retriever cleanup on shutdown
- **RAG Audit Security** (`ai-service/rag_retriever.py`):
  - Added PHI redaction in audit logs (digits masked, queries truncated)
  - Prevents logging of patient-identifiable data
- **Citation Handling** (`ai-service/gemini_orchestrator.py`):
  - AAD melanoma citations now report `source: "AAD"` (not "AAD_MELANOMA") with correct URL
### Frontend
#### Fixed
- **Demo Case Labs** (`frontend/app/page.tsx`):
  - Wired demo case lab values into state for differential generation
  - Lab values now influence AI analysis
- **State Reset** (`frontend/app/page.tsx`):
  - `resetCase()` now called AFTER validation (not before)
  - Prevents wiping state on empty submit
- **Rate Limit UI** (`frontend/components/RateLimitUI.tsx`):
  - Simplified countdown logic to avoid React purity violations
  - Reset rate-limit state on new requests
- **Image Context** (`frontend/app/debate/page.tsx`):
  - Now includes MedGemma summary (truncated) in `image_context` for debate
- **API Routes** (`frontend/app/api/*.ts`):
  - Unified rate-limit header passthrough via `copyRateLimitHeaders()` utility
- **HeroUI v3 Upgrade** (`frontend/package.json`):
  - Upgraded `@heroui/react` to v3 beta
  - Fixed component APIs:
    - `Divider` → `<hr>` element
    - `variant="bordered"` → `variant="outline"`
    - `variant="flat"` → `variant="soft"`
    - `variant="solid"` → `variant="primary"`
    - `color="secondary"` / `color="primary"` → `color="accent"`
    - `isDisabled` → `disabled` on Input
    - `LabValue.reference` made optional
- **HeroUI Styles Import** (`frontend/app/globals.css`):
  - Fixed import path: `@heroui/styles` → `@heroui/styles/css`
### Documentation
#### Fixed
- **README.md**:
  - Fixed screenshot path (`frontend/public/test-data/test1.png`)
  - Test count updated to 156
- **STURGEON_PROJECT_PLAN.md**:
  - License corrected to CC BY 4.0
#### Added
- **Logo** (`frontend/public/sturgeon-logo.svg`):
  - Added SVG logo for README
### Tests
- **156 tests passing** (133 existing + 23 new)
---
## [2026-02-21] Session 14 — Guide-RAG Alignment & Demo Cases
### Architecture Alignment with arXiv:2510.15782
The Guide-RAG paper found that "guideline + systematic reviews" (GS-4 configuration) outperformed both guidelines-only and large-scale literature databases for clinical question-answering. This session aligned Sturgeon's RAG implementation with those findings.
#### Corpus Enhancement
- **Added AAD melanoma guidelines** (`ai-service/guidelines/melanoma_aad.md`):
  - ABCDE criteria for melanoma detection
  - Biopsy recommendations and surgical margins
  - AJCC staging guidelines
  - Total corpus: 14 documents (was 11)
- **Added melanoma systematic review** (`ai-service/guidelines/systematic_reviews/melanoma_diagnosis_ai_sr.md`):
  - AI vs clinicians for skin cancer diagnosis (npj Digital Medicine, 2024)
  - CC BY 4.0 licensed for compatibility
  - First SR in corpus (GS-4 configuration)
#### RAG Parameter Tuning
- `TOP_K_DEFAULT`: 5 → **12** (paper used 25, scaled for corpus size)
- `CHUNK_OVERLAP`: 300 (25%) → **500 (42%)** (paper used 50%)
#### LLM-as-Judge Evaluation Framework
- New `rag_evaluation.py` module implementing Guide-RAG metrics:
  - **Faithfulness**: Response supported by retrieved context
  - **Relevance**: Response addresses the question
  - **Comprehensiveness**: Response covers all aspects
- Uses Gemini as evaluation judge (already in stack, native JSON output)
- New `/rag-evaluate` endpoint for development/debugging
- New `evaluation/test_questions.yaml` (25 clinical questions for evaluation)
#### Demo Cases Realigned
- Updated `frontend/lib/demo-cases.ts` to 3 cases aligned with corpus:
  1. **Melanoma** (Dermatology) — Visual diagnosis showcase
  2. **Pneumonia** (Radiology) — Classic MedGemma strength
  3. **Sepsis** (Multi-modal) — Lab extraction + clinical reasoning
- Removed: Psoriasis, Breast carcinoma, Lung adenocarcinoma (pathology, no RAG support)
- Created `test-data/demo-cases.md` for demo recording guide
#### Citation Handling
- Added AAD_MELANOMA to `GUIDELINE_URLS` and citation detection
- Updated citation extraction patterns for melanoma-related queries
- Citation prompt includes: "(AAD Melanoma Guidelines, 2018)"
### Tests
- Unit tests unchanged (133 passing)
### Documentation
- Updated CLAUDE.md with completed items
- Added References section to README (CHECK, HALO, Guide-RAG, Mayo Reverse RAG)

---
## [2026-02-16] Session 13 — Hallucination Prevention & Research Attribution

### Backend

#### Added
- **Hallucination Detection Module** (`ai-service/hallucination_check.py`):
  - Validates MedGemma outputs against user-provided data
  - Detects fabricated lab values (e.g., hemoglobin 8.2 g/dL when not provided)
  - Extracts numeric values with units from generated text
  - Maps values to closest lab test name by position
  - Functions: `check_hallucination()`, `validate_differential_response()`, `validate_debate_response()`
  - 15 unit tests in `test_hallucination.py`

#### Changed
- **Prompt Guardrails** (`ai-service/prompts.py`):
  - **DIFFERENTIAL_PROMPT**: Removed hardcoded example with specific lab values (8.2 g/dL hemoglobin, 12 ng/mL ferritin)
  - Added CRITICAL CONSTRAINTS section: "ONLY use lab values explicitly provided above. DO NOT fabricate."
  - Replaced specific example with generic template showing format only
  - **SUMMARY_PROMPT**: Same guardrails added
  - **DEBATE_TURN_PROMPT / DEBATE_TURN_PROMPT_WITH_RAG**: Added hallucination prevention constraints

- **Integrated Hallucination Validation** (`ai-service/main.py`):
  - `/differential` endpoint now validates response for fabricated lab values
  - Auto-retry with correction constraints if hallucination detected
  - `/debate-turn` MedGemma-only fallback also includes validation
  - Logs warnings for debugging; corrected response returned to user

### Frontend

#### Changed
- **State Reset on New Case** (`frontend/app/page.tsx`):
  - Added `resetCase()` call at start of `handleAnalyze()`
  - Prevents previous case's `labResults` and `imageAnalysis` from persisting
  - Ensures clean state for each new analysis

### Documentation

#### Added
- **References Section** (`README.md`):
  - Academic attribution for research used in implementation
  - CHECK Framework (arXiv:2506.11129) — hallucination detection
  - HALO Framework (arXiv:2409.10011) — multiple query variations, MMR scoring
  - Guide-RAG (arXiv:2510.15782) — corpus curation, evaluation metrics
  - Mayo Reverse RAG (VentureBeat, March 2025) — verification-first approach

### Tests
- **133 tests passing** (118 existing + 15 new hallucination tests)

---

## [2026-02-15] Session 12 — Comprehensive Citation Detection & Mobile Responsiveness

### Backend

#### Added
- **Expanded Citation Detection** (`ai-service/gemini_orchestrator.py`):
  - Support for 15+ medical organizations: NCCN, AAD, ACR, ADA, AHA, ACC, CHEST, USPSTF, WHO, NICE, ASCO, ESMO (plus existing IDSA, CDC, ATS)
  - Combined organization support: ATS/IDSA, ACC/AHA
  - Smart URL mapping with generic landing pages (ready for Phase B specific URLs)
  - Position-based deduplication prevents duplicate citations
  - Enhanced regex patterns with better boundary detection
- **Comprehensive Test Suite** (`ai-service/tests/test_citations.py`):
  - 26 unit tests covering all supported organizations
  - Tests for combined orgs, duplicates, edge cases
  - All tests passing ✅

#### Changed
- **Citation Prompt Enhancement**: Updated synthesis prompt with examples for all specialty areas (cancer, dermatology, cardiology, diabetes, etc.)

### Frontend

#### Mobile Responsiveness
- **Upload Page** (`frontend/app/page.tsx`):
  - Fixed filename text overflow in green drop zone
  - Truncates long filenames with ellipsis (`truncate` + `min-w-0 flex-1`)
  - Hidden "Medical Image"/"Lab Report" labels on mobile to save space
  - Proper container width constraints (`w-full max-w-full overflow-hidden`)

- **Debate Page** (`frontend/app/debate/page.tsx`):
  - Fixed sidebar header cutoff with extra mobile padding (`pt-6 md:pt-4`)
  - Mobile-optimized sidebar width (`w-[85vw] max-w-[320px]`)
  - Chat container with proper overflow handling (`h-[calc(100vh-52px-3px)]`)
  - Responsive input area with adaptive button text
  - Touch-friendly suggested prompts with snap scrolling

- **Global CSS** (`frontend/app/globals.css`):
  - Touch target minimums (44px) for mobile
  - Smooth scrolling with `-webkit-overflow-scrolling: touch`
  - Scroll snap for suggested prompt chips
  - Custom scrollbar styling
  - Focus-visible states for accessibility

---

## [2026-02-14] Session 11 — Backend Modularization & UI Polish

### Architecture
- **Modular Backend**: Split `ai-service/main.py` (940 lines) into focused modules:
  - `models.py` — All Pydantic request/response models
  - `json_utils.py` — JSON extraction, repair, newline fixing utilities  
  - `refusal.py` — Pure refusal detection (`_is_pure_refusal`) and preamble stripping (`_strip_refusal_preamble`)
  - `formatters.py` — Lab values, differential, and debate rounds formatters
  - `main.py` — Slim: app setup, lifespan, endpoint definitions (imports from above)

### Added
- **Backend Unit Tests** (`ai-service/tests/`, 41 tests passing):
  - `test_json_utils.py` — JSON extraction, truncation repair, newline fixing
  - `test_refusal.py` — Pure refusal detection, preamble stripping edge cases
  - `test_formatters.py` — Lab/differential/rounds formatting
- **Comprehensive Error Handling**: Try/except wrappers on all endpoints with performance timing logs
- **Pydantic Validators**: Empty input prevention on `patient_history`, `lab_values`, `user_challenge`
- **Few-Shot Prompts**: Added complete input/output examples to `extract-labs` and `differential` prompts for JSON stability
- **Chain-of-Thought**: `DIFFERENTIAL_PROMPT` now includes "think step-by-step" instruction before JSON output
- **Confidence Calibration**: `SUMMARY_PROMPT` requests numeric confidence 0-100 with calibration guidance

### Frontend
- **Upload Page**: Input validation with red error banner when neither patient history nor evidence is provided
- **Debate Page**:
  - Suggested Challenge chips above input field (static defaults: "What if...", "Could this be...", "What test would help?")
  - Visual probability bars in sidebar diagnosis cards (green/yellow/red based on probability)
  - Collapsible sidebar for mobile responsive layout
- **Summary Page**: Export PDF button with `@media print` CSS (hides nav, optimizes layout)

### Changed
- Updated all endpoint error responses to include meaningful messages and timing metrics
- Enhanced prompt stability through few-shot examples and explicit reasoning instructions

---

## [2026-02-13] Session 10 - Multi-File Upload & Response Cleaning

### Added

- `frontend/app/page.tsx` - **Multi-file upload**: Simultaneous image + lab report upload
  - Split `file` state → `imageFile` + `labFile` (separate slots)
  - `processFiles()` auto-classifies files by type (image vs PDF/TXT)
  - `Promise.all` runs image analysis + lab extraction in parallel
  - Drop zone shows both files with individual ✕ remove buttons + "Clear all"
  - `<input multiple>` accepts multiple files at once
  - Hint text: "You can upload both an image and a lab report"
- `ai-service/main.py` - **`_strip_refusal_preamble()`**: Strips leading "I am unable to... However..." boilerplate when real analysis (>100 chars) follows. Trailing disclaimers kept.

### Changed

- `ai-service/main.py` - Summary endpoint `max_new_tokens` bumped 2048 → 3072 (prevents truncated JSON on complex cases)
- `ai-service/main.py` - Wired `_strip_refusal_preamble` into `/analyze-image` with logging

### Documentation

- `CLAUDE.md` - Updated completed items, cleared In Progress, refreshed Next Steps
- `STURGEON_PROJECT_PLAN.md` - Marked Week 2/3 milestones (demo cases, UI polish, multi-file upload)

---

## [2026-02-13] Session 9 — Refusal Detection Refactor & JSON Fix

### Problem

1. `strip_disclaimers()` was silently removing AI safety disclaimers from MedGemma output — inappropriate for a medical AI product. Disclaimers like "I am an AI and cannot provide medical advice" are appropriate and should be shown.
2. JSON newline repair used fragile regex `(?<=\w)\n(?=\w)` that only caught newlines between word characters, missing breaks after punctuation like `(B+),\nColor`.

### Changed

- `ai-service/main.py`:
  - **Renamed** `strip_disclaimers()` → `_is_pure_refusal()`: returns boolean instead of modified text. Detects pure refusals (< 50 chars remaining after removing disclaimer patterns) without modifying the output.
  - **Auto-retry for refusals**: When `_is_pure_refusal()` returns True, retries with "describe visual findings" prompt at temp 0.3. Bypasses safety guardrails by reframing the task.
  - **JSON newline fix**: Replaced regex with `_fix_newlines_in_json_strings()` — walks text char-by-char tracking quote boundaries, replaces literal `\n` inside strings with spaces. Works regardless of surrounding characters.

### Tested

- ✅ All 4 demo cases pass E2E (see Session 10 test results above)
- ✅ Melanoma + lung adenocarcinoma: retry mechanism triggers and succeeds
- ✅ Psoriasis + breast carcinoma: no retry needed, disclaimers preserved in output
- ✅ Summary JSON parse: 200 OK on all cases

---

## [2026-02-12] Session 8 — MedSigLIP Triage Accuracy & Robustness

### Problem

MedSigLIP misclassified non-radiology images (e.g., `derm-melanoma.jpg` → "lab report document" at 28.5%) due to vague zero-shot labels and watermarks/logos confusing classification. MedGemma then refused to analyze the image because the triage told it the image was a document.

### Changed

- `ai-service/medsiglip.py` — **Label engineering + confidence fallback**:
  - Rewrote all 8 `image_type` zero-shot labels to be more descriptive and contrastive (e.g., `"a close-up photograph of a skin lesion or rash on a human body"` instead of `"a dermatology photograph of skin"`)
  - Added `IMAGE_TYPE_CONFIDENCE_THRESHOLD = 0.25` constant
  - When confidence < 25%, returns `modality="uncertain"` and skips misleading finding-specific classification. MedGemma then determines the imaging modality directly.
  - Updated modality routing keywords to match new labels (e.g., `"rash"`, `"stained"`)

- `ai-service/main.py` — **Adaptive MedGemma prompt + robustness fixes**:
  - When `modality == "uncertain"`: uses generic multi-modality prompt asking MedGemma to first identify the imaging type, then analyze. System prompt broadened from "specialist radiologist" to "medical imaging specialist experienced in radiology, dermatology, and pathology"
  - When modality is known: keeps original behavior unchanged
  - **Image analysis temperature**: Set to `0.1` (was default 0.7). Google used `0.0` for MedGemma benchmarks; `0.1` is nearly deterministic while avoiding greedy decoding edge cases. Prevents the same image randomly producing a thorough analysis vs a refusal.
  - **Disclaimer stripping**: Added 4 new patterns for MedGemma refusal phrases (`"This is because I am an AI..."`, `"Analyzing medical images requires..."`, `"If you have a medical image..."`, `"I am unable to provide a medical diagnosis..."`). When all content is disclaimers, returns helpful fallback message instead of raw refusal text.
  - **JSON newline fix**: Added pre-processing in `extract_json()` to join literal newlines inside JSON string values (MedGemma wraps long `reasoning_chain` strings across lines, which is invalid JSON). Fixes summary endpoint 500 error.

- `frontend/app/page.tsx` — **Uncertain modality UI**:
  - When `modality === "uncertain"`: hides misleading MedSigLIP triage chips, shows "Image type auto-detected by MedGemma" badge instead
  - Triage divider shown for both uncertain and normal cases

- `frontend/app/debate/page.tsx` — **Adaptive debate display**:
  - Intro message: when uncertain, says "analyzed using MedGemma interpretation" (no mention of MedSigLIP triage)
  - Sidebar image caption: shows "Medical Image / MedGemma direct analysis" instead of low-confidence triage info

### Added

- `test-data/derm-melanoma.jpg` — Melanoma test image (previously added)
- `test-data/demo-cases.md` — 4 demo test cases (melanoma, psoriasis, breast carcinoma, lung adenocarcinoma)

### Tested — All 4 demo cases verified E2E

- ✅ Derm melanoma: MedSigLIP fallback (22.2%) → MedGemma retry → Melanoma (High) 90%
- ✅ Derm psoriasis: MedSigLIP classified correctly (43.3%) → 3535-char analysis → Plaque Psoriasis (High) 90%
- ✅ Breast carcinoma: MedSigLIP classified (33.4%) → IDC (High) 90%, with EGFR/PR/HER2 reasoning
- ✅ Lung adenocarcinoma: MedSigLIP fallback (24.6%) → MedGemma retry → Lung Adenocarcinoma 90%
- ✅ Summary JSON parse: all cases returned 200 OK
- ✅ Debate: agentic flow working (Gemini orchestrator → MedGemma queries → updated differentials)

### Challenges

- **MedSigLIP confidence varies by lesion-to-background ratio**: Small lesions (melanoma on heel) get low confidence, large lesions (psoriasis plaque) classify correctly. Not caused by watermarks — both DermNet images had identical watermarks.
- **MedGemma non-determinism**: At temperature 0.7, the same image produced completely different outputs (detailed analysis vs full refusal). Root cause: sampling randomness. Fixed by setting `temperature=0.1`, though MedGemma may still refuse some images at any temperature.
- **JSON literal newlines**: MedGemma wraps long strings across lines in JSON output, producing invalid JSON. The initial regex fix `(?<=\w)\n(?=\w)` missed newlines after punctuation (e.g., `(B+),\nColor`). Fixed with string-aware char-by-char approach.

### Future Considerations

- Image preprocessing (crop/zoom to lesion area) to improve MedSigLIP confidence — stretch goal
- Fine-tune or add few-shot examples for dermatology/pathology image analysis
- Test with more diverse derm/pathology images to validate label improvements
- Consider adding a `seed` parameter for full reproducibility (hardware-dependent)

---

## [2026-02-08] Session 7 — Light Theme Overhaul & Visual QA

### Theme Redesign: Dark → Light (PubMed/NIH-inspired)

Complete visual overhaul from dark glassmorphism to a clean, clinical light theme.

- **Design language**: White backgrounds, Slate 900 text (#0F172A), Teal 600 accents (#0D9488), Slate 50 surfaces (#F8FAFC), Slate 200 borders (#E2E8F0)
- **Typography**: Swapped Outfit → Source Sans 3 + Source Code Pro (Google Fonts)
- **Branding**: 3px teal top bar (NIH-style), no more glassmorphism/backdrop-blur

### Added

- `frontend/components/Prose.tsx` — Shared markdown renderer using `react-markdown` + `remark-gfm`, applies `.prose-medical` CSS class. Used in chat bubbles, image interpretation, and summary page.
- `frontend/app/globals.css` — `.prose-medical` CSS class (teal list markers, styled headings, tables, code blocks, blockquotes). `.dot-pulse` three-dot loading animation.
- `react-markdown` and `remark-gfm` npm dependencies

### Changed

- `frontend/app/layout.tsx` — Source Sans 3 font, removed `dark` class and data-theme, removed ambient glow divs, added fixed teal top bar
- `frontend/app/globals.css` — Complete rewrite for light theme CSS variables and utility classes
- `frontend/app/page.tsx` (Upload page):
  - Light theme restyle with SVG upload icon
  - White card with subtle border, teal-accented image analysis card (`border-l-4 border-l-teal`)
  - Pill-style Read More/Show Less toggle, teal focus rings on textarea
  - Removed misleading "Image Classification" section (37% confidence, misclassifying X-rays as lab reports) — kept only MedSigLIP Triage Findings + Clinical Interpretation
  - Fixed analyze button loading: removed `animate-pulse`, short "Analyzing..." button text, detailed step text moved below as muted text
  - Fixed "Remove file" button opening file explorer (z-index conflict with hidden file input)
- `frontend/app/debate/page.tsx` (Debate page):
  - White header, `bg-surface` sidebar, teal left border on top diagnosis card
  - AI bubbles: `bg-surface` + teal left border + "STURGEON AI" label + `<Prose>` markdown
  - User bubbles: blue bg + white text + "YOU" label
  - Error bubbles: `bg-red-50` + red border + Retry button
  - Three-dot pulse loading animation, auto-scroll to latest message
  - Better error extraction from response body
- `frontend/app/summary/page.tsx` (Summary page):
  - Teal confidence progress bar, numbered reasoning steps with teal circle numbers
  - `parseRuledOut()` function to extract real reasons from "Diagnosis: reason" strings
  - Flat ruled-out cards with red X (replaced Accordion)
  - Prose rendering for next steps
  - Stripped duplicate leading numbers from reasoning steps (teal circles already show the number)
- `ai-service/main.py` — Wrapped `_debate_turn_medgemma_only()` in try/except for graceful error responses instead of HTTP 500

### Visual QA

- ✅ Upload page: teal top bar, font, header, SVG icon, drop zone, file states, image preview, chips, textarea, button, footer
- ✅ Debate page: white header, sidebar, diagnosis cards, AI/user bubbles, loading animation, send button, agentic mode badge
- ✅ Summary page: header, diagnosis card, confidence bar, reasoning steps, next steps, ruled out cards, session footer

---

## [2026-02-07] Session 6 - Image Pipeline & E2E Testing

### Added

- **Image Analysis Pipeline**:
  - `ai-service/medsiglip.py`: MedSigLIP integration for fast zero-shot image triage (image type detection)
  - `ai-service/main.py`: `/analyze-image` endpoint supporting multipart uploads
  - `frontend/app/api/analyze-image/route.ts`: Next.js proxy for image uploads
  - `frontend/app/page.tsx`: Full image upload UI with preview and analysis results
  - `frontend/app/context/CaseContext.tsx`: Image findings state management
- **Testing Tools**:
  - `verify_models.py`: Script to check model access and dependencies
  - `test-data/`: Added real NIH Chest X-rays for E2E testing

### Changed

- **MedGemma Integration**:
  - Updated `ai-service/medgemma.py` to support multimodal input (text + image)
  - MedGemma now receives MedSigLIP triage summary as context for deeper analysis
- **Configuration**:
  - Added `protobuf` and `sentencepiece` to `requirements.txt` (critical for MedSigLIP)
  - Added `DISABLE_MEDSIGLIP` environment variable support to skip gated model download

### Fixed

- **Gemini JSON Parsing**: Improved robustness in `gemini_orchestrator.py` to auto-repair malformed JSON (missing commas) from LLM responses
- **Backend Stability**: Added graceful fallback if MedSigLIP is unavailable/disabled
- **MedSigLIP Loading**: Fixed `NoneType` error by adding `sentencepiece` and `protobuf` dependencies

### Verified

- ✅ Models Access: MedGemma 1.5 4B and MedSigLIP confirmed accessible
- ✅ E2E Image Flow: Uploaded real NIH Chest X-ray (`test1.png`) -> MedGemma analysis -> Correctly identified cardiomegaly/effusion
- ✅ Error Handling: Validated behavior with disabled MedSigLIP (graceful fallback to MedGemma-only)

---

## [2026-02-07] Session 5 - Agentic Dual-Model Architecture

### Architecture Upgrade

Upgraded from MedGemma-only to **Gemini + MedGemma agentic dual-model**:

- **Gemini** (orchestrator): Manages multi-turn conversation, summarizes debate state, formulates focused questions
- **MedGemma** (callable tool): Handles all clinical reasoning, differential diagnosis, evidence analysis
- Maps directly to the **Agentic Workflow Prize** criteria: "deploying HAI-DEF models as intelligent agents or callable tools"
- Graceful fallback to MedGemma-only if no Gemini API key is set

### Added

- `ai-service/gemini_orchestrator.py` (~477 lines):
  - `ClinicalState` dataclass for structured debate state (keeps prompt size constant)
  - `GeminiOrchestrator` class with two-step flow: Gemini formulates question -> MedGemma answers -> Gemini synthesizes
  - `_parse_orchestrator_response()` with double-wrap JSON detection, regex stripping, nested dict unwrapping
  - System instruction for orchestrator role
- `ai-service/.env.example` - Environment variable template for setup

### Changed

- `ai-service/main.py` - Refactored to v0.2.0:
  - In-memory session store (`_sessions` dict) for clinical state tracking
  - Orchestrated vs fallback debate turn routing (`_debate_turn_orchestrated` / `_debate_turn_medgemma_only`)
  - Extracted `_parse_differential()` helper for robust field name handling (works with both MedGemma and Gemini responses)
  - Health endpoint now reports orchestrator status, mode, active sessions
  - `DebateTurnRequest` / `DebateTurnResponse` extended with `session_id` and `orchestrated` fields
- `ai-service/medgemma.py` - Upgraded to MedGemma v1.5:
  - Model ID: `google/medgemma-4b-it` -> `google/medgemma-1.5-4b-it`
  - Better medical text reasoning, improved image support (CT, MRI, WSI), structured data extraction
- `ai-service/requirements.txt` - Added `google-genai>=1.0.0`, `python-dotenv>=1.0.0`
- `frontend/app/debate/page.tsx`:
  - Fixed chat wipe bug: Changed from `[caseData.differential, router]` dependency to `useRef(false)` one-time init
  - Added `ai_response` cleanup: regex strips `{ "ai_response":` prefix artifacts before display
  - Added session tracking (`sessionId` state, passed to backend)
  - Added "Agentic Mode" badge in header when orchestrator is active
  - Loading indicator shows "Gemini + MedGemma are reasoning..." in agentic mode
  - Redesigned differential cards: full supporting evidence (green +), against evidence (red -), suggested tests (teal)
- `CLAUDE.md` - Updated with dual-model architecture, revised constraints and status
- `STURGEON_PROJECT_PLAN.md` - Updated architecture diagrams, data flow, milestones, risk table

### Fixed

- **Double-wrapped JSON**: Gemini sometimes returned `{ "ai_response": "{ \"ai_response\": \"...\" }" }` -- detected and unwrapped
- **Chat messages wiped**: `useEffect` re-triggered on differential update, resetting messages to initial state
- **AI responses truncated**: Increased `max_output_tokens` from 2048 -> 4096 (Gemini synthesis), `max_new_tokens` from 1536 -> 2048 (MedGemma)
- **Differential cards too sparse**: Only showed `.slice(0, 2)` of supporting evidence

### Model Upgrades

- Gemini: `gemini-2.5-flash` -> `gemini-3-flash-preview`
- MedGemma: `google/medgemma-4b-it` (v1) -> `google/medgemma-1.5-4b-it` (v1.5)

---

## [2026-02-07] Session 4 - Backend Integration & E2E Flow

### Added

- **Frontend API Routes**: Created Next.js API routes to proxy backend calls:
  - `frontend/app/api/differential/route.ts` → POST /differential
  - `frontend/app/api/debate-turn/route.ts` → POST /debate-turn
  - `frontend/app/api/summary/route.ts` → POST /summary
- **State Management**: `frontend/app/context/CaseContext.tsx` — React Context for sharing case data (patient history, differential, debate rounds) across pages

### Changed

- `frontend/app/page.tsx` - Wired to `/api/differential`, stores results in context, navigates to debate
- `frontend/app/debate/page.tsx` - Loads from context, calls `/api/debate-turn` for AI responses
- `frontend/app/summary/page.tsx` - Calls `/api/summary`, displays final diagnosis
- `frontend/app/layout.tsx` - Wrapped with `CaseProvider`

### Fixed

- `ai-service/main.py`:
  - Fixed `ruled_out` parsing to handle dict format from MedGemma
  - Fixed `updated_differential` parsing with robust field name mapping
- `ai-service/prompts.py`:
  - Made `DEBATE_TURN_PROMPT` explicit about expected JSON format

### Verified

- ✅ Empty input validation (button disabled)
- ✅ Special characters & lab values with units
- ✅ Full E2E flow: Upload → Debate → Summary

### Known Issues

- Multi-turn debate chat history persistence needs re-architecture

---

## [2026-02-06] Session 3 - Frontend UI with HeroUI v3

### Added

- **HeroUI v3** component library (`@heroui/react@beta`, `@heroui/styles@beta`)
- **HeroUI Agent Skills** for component documentation access
- `frontend/app/page.tsx` - Upload page with:
  - File drop zone (drag & drop + click to browse)
  - Patient history TextArea
  - "Analyze & Begin Debate" Button with loading state
- `frontend/app/debate/page.tsx` - Debate page with:
  - Split layout (diagnosis panel + chat interface)
  - Diagnosis cards with probability Chips (high/medium/low)
  - Chat bubbles for AI debate
  - Challenge input TextField

### Changed

- `frontend/app/globals.css` - Medical dark theme with HeroUI:
  - Background: #0F172A (Slate)
  - Accent: #1E40AF (Medical Blue)
  - Secondary: #0D9488 (Teal)
  - Status colors: success/warning/danger
- `frontend/app/layout.tsx` - Inter font, dark mode, SEO metadata
- `.gitignore` - Added for Node/Python project

### Technical Notes

- HeroUI v3 uses **compound components**: `<Card><Card.Header>...</Card.Header></Card>`
- Uses **oklch color space** for theming
- **No Provider needed** (unlike v2)
- Skills available: `node scripts/get_component_docs.mjs Button Card`

### Polished

- **UI Design System**: Applied Glassmorphism and Pulse animations for premium feel
  - `Header`: Sticky backdrop-blur-md on all pages
  - `Cards`: Hover effects (border-teal, shadow, scale)
  - `Button`: Pulse animation during loading state
  - `DropZone`: Glow effect on valid file drag
- **Configuration**: Consolidated `frontend/.gitignore` into root `.gitignore`

### Repository

- GitHub repo created: https://github.com/weekijie/Sturgeon
- Initial commit pushed (57 files)

---

## [2026-02-06] Session 2 - Backend Integration

### Changed

- `ai-service/main.py` - Wired all 4 endpoints to MedGemma:
  - `/extract-labs` - Extracts structured lab values from text
  - `/differential` - Generates 3-4 differential diagnoses
  - `/debate-turn` - Handles debate rounds with context injection
  - `/summary` - Creates final diagnosis summary
- Added `lifespan` context manager to load model on startup
- Added JSON extraction helper with markdown code block handling
- Added formatting helpers for lab values, differential, debate rounds

---

## [2026-02-06] Session 1 - Project Setup

### Added

- `frontend/` - Next.js 14 with TypeScript and Tailwind CSS
- `ai-service/main.py` - FastAPI backend with endpoint stubs
- `ai-service/medgemma.py` - MedGemma model loader (bfloat16 for AMD)
- `ai-service/prompts.py` - Prompt templates for all endpoints
- `ai-service/requirements.txt` - Python dependencies
- `README.md` - Project overview and quick start
- `CLAUDE.md` - AI assistant instructions

### Configuration

- **AMD GPU (ROCm 7.2)**: Requires `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`
- **Model**: MedGemma 4B-it with bfloat16 precision
- **API Classes**: `AutoModelForImageTextToText` + `AutoProcessor`

### Technical Discoveries

- MedGemma 4B-it is a vision-language model, not a standard LLM
- Must use `AutoModelForImageTextToText` (not `AutoModelForCausalLM`)
- Must use `AutoProcessor` (not `AutoTokenizer`)
- AMD GPUs require bfloat16 (not float16) for proper generation
- Content format: `[{"type": "text", "text": "..."}]` (not plain strings)

---
