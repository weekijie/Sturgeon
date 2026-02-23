# Sturgeon - Project Instructions

> **Project**: Sturgeon - Diagnostic Debate AI  
> **Workspace**: `c:\Users\weeki\Documents\GitHub\Sturgeon`  
> **Deadline**: February 24, 2026  
> **GitHub**: https://github.com/weekijie/Sturgeon

> **New Chat?** Always `@mention` this file so the AI reads project context!

---

## Project Summary

**Sturgeon** is a House MD / Good Doctor-style diagnostic debate AI for the MedGemma Impact Challenge. Users upload evidence (text, images, lab reports), AI generates differentials, users challenge the AI, and together they arrive at a diagnosis.

**Prize Target**: Main Track + Agentic Workflow Prize

---

## Tech Stack

| Layer        | Technology                                                     | Role                                                        |
| ------------ | -------------------------------------------------------------- | ----------------------------------------------------------- |
| Frontend     | Next.js 14 (App Router) + **HeroUI v3**                        | UI + API routes                                             |
| Backend      | Python FastAPI                                                 | Orchestration + inference                                   |
| Medical AI   | **MedGemma 4B-it** (bfloat16, via AutoModelForImageTextToText) | Medical reasoning, image analysis, differential diagnosis   |
| Orchestrator | **Gemini Pro/Flash** (Google AI API)                           | Conversation management, context summarization, debate flow |
| Hosting      | Vercel (frontend) + local/Kaggle (AI)                          | Free deployment                                             |

> **Note**: Tailwind v4 uses `@theme` syntax which may trigger "Unknown at rule" warnings in IDEs. These are false positives.

### HeroUI v3 — IMPORTANT

**Always load the `heroui-react` agent skill before making frontend UI changes.** This ensures correct v3 patterns are used.

Key v3 rules:

- **No Provider needed** (unlike v2 — do NOT add `HeroUIProvider`)
- **Compound components**: `<Card><Card.Header>...</Card.Header></Card>` (not flat props)
- **Use `onPress` not `onClick`** for Button/interactive components
- **Tailwind v4 required** — uses `@theme` and `oklch` color space
- **Packages**: `@heroui/react@beta` + `@heroui/styles@beta`
- **Fetch component docs before implementing**: `node scripts/get_component_docs.mjs Button Card`
- Skill scripts location: `.agents/skills/heroui-react/scripts/`

### Architecture: Agentic Dual-Model

- **MedGemma** = Medical Specialist (callable tool). Handles all clinical reasoning, medical image analysis, lab extraction, differential diagnosis. This is the HAI-DEF model.
- **Gemini** = Orchestrator. Manages multi-turn conversation context, summarizes debate state, routes medical questions to MedGemma. Handles what MedGemma wasn't trained for (multi-turn conversation).

This framing directly maps to the Agentic Workflow Prize: "deploying HAI-DEF models as intelligent agents or callable tools."

### Brand Identity

- **Design System**: Medical Light Theme (PubMed/NIH-inspired)
- **Key UI Elements**: Clean white backgrounds, Teal accents (#0D9488)
- **Typography**: Source Sans 3 + Source Code Pro (Google Fonts)

### AMD GPU Setup (Required)

```powershell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"
```

---

## Design Principles

1. **Don't overengineer**: Simple beats complex
2. **Clarity over compatibility**: Clear code beats backward compatibility
3. **Throw errors**: Fail fast when preconditions aren't met
4. **Separation of concerns**: Each function has single responsibility
5. **Medical Dark Theme**: Use `#0F172A` Slate specific branding only. Glassmorphism for depth.

---

## Development Methodology

1. **Plan first, build second**: Always present a clear plan before making changes. Wait for explicit "build mode" approval before executing code changes. Never skip ahead.
2. **Test intensively before committing**: Every change must be verified (build check, manual test plan, or runtime test) before committing or moving to the next task. No "ship and pray."
3. **Surgical changes only**: Make minimal, focused fixes
4. **Evidence-based debugging**: Add minimal, targeted logging
5. **Fix root causes**: Address underlying issues, not symptoms
6. **Simple > Complex**: Let TypeScript catch errors, not excessive runtime checks
7. **Collaborative process**: Work with user to identify most efficient solution
8. **Web search when uncertain**: Verify APIs/libraries via documentation, don't assume
9. **Always load `heroui-react` skill** before making any frontend UI changes
10. **Git: generate commit messages only**: Do NOT run `git add`, `git commit`, or `git push` commands. Instead, generate the commit message/description for the user to input manually via VS Code Source Control or GitHub Desktop. PowerShell's PSReadLine crashes on multiline commit messages (terminal buffer overflow), and `&&` chaining is not supported in older PowerShell versions.
11. **Read before editing**: Always read/view the file (or relevant section) before making edits. Do not edit files blindly from memory — the file may have changed since you last saw it.
12. **ALWAYS use `.venv/Scripts/python` for backend**: All Python commands (tests, scripts, pip installs) MUST use the virtual environment Python at `.venv/Scripts/python`. Never use system Python or global pip. This prevents dependency conflicts and ensures reproducibility.
13. **Document problems encountered**: When you face issues, bugs, or unexpected challenges during a session, document them in CHANGELOG.md under the session entry. Include:
    - The problem/issue faced
    - Why it happened (if understood)
    - How it was resolved
    - Any workarounds or lessons learned

---

## Project Structure

```
Sturgeon/
├── frontend/                   # Next.js 14
│   ├── app/
│   │   ├── page.tsx           # Upload + history
│   │   ├── debate/page.tsx    # Debate chat
│   │   ├── summary/page.tsx   # Final diagnosis
│   │   ├── context/           # React Context
│   │   └── api/               # Routes → Python
│   └── components/
│
├── ai-service/                 # Python FastAPI (modular)
│   ├── main.py                # App setup + endpoints
│   ├── models.py              # Pydantic request/response models
│   ├── json_utils.py          # JSON extraction & repair utilities
│   ├── refusal.py             # Refusal detection & preamble stripping
│   ├── formatters.py          # Lab/differential/round formatters
│   ├── medgemma.py            # Model inference
│   ├── prompts.py             # Prompt templates
│   ├── gemini_orchestrator.py # Conversation orchestrator
│   ├── medsiglip.py           # Image triage
│   └── tests/                 # Unit tests (41 passing)
│
├── modal_backend/              # Modal production backend (vLLM + FastAPI)
│   ├── app.py                 # Modal class + ASGI app + endpoints
│   ├── gemini_orchestrator_modal.py
│   ├── rag_retriever.py
│   └── README.md
│
├── CLAUDE.md                   # This file
├── CHANGELOG.md               # Session-by-session changes
├── NEXT_PATCH_PLAN.md         # Next session patch queue
└── README.md
```

---

## Key Files Reference

| File                                       | Purpose                 |
| ------------------------------------------ | ----------------------- |
| `brain/.../sturgeon_project_summary.md`    | Complete technical plan |
| `brain/.../hai_def_models_reference.md`    | MedGemma capabilities   |
| `brain/.../medgemma_hackathon_analysis.md` | Hackathon details       |

---

## Critical Constraints

| Constraint       | Details                                                      |
| ---------------- | ------------------------------------------------------------ |
| HAI-DEF Required | Must use MedGemma (Gemini allowed as orchestrator)           |
| Hardware         | AMD RX 9060 XT (16GB) → Use bfloat16                         |
| Deadline         | February 24, 2026 (ahead of schedule with AI assistance)     |
| MedGemma API     | Use `AutoModelForImageTextToText` + `AutoProcessor`          |
| AMD GPU          | Set `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`              |
| Gemini API       | Paid key available. Free tier also works for reproducibility |

---

## Competition Rules & Licensing

### Winner Obligations (Section 5)

**CRITICAL**: If you win the MedGemma Impact Challenge, you must:
- Grant **CC BY 4.0 license** to your submission to the Competition Sponsor
- Provide detailed methodology description (architecture, preprocessing, hyperparameters, training details)
- Include complete code repository with reproduction instructions
- Ensure results are reproducible by judges

**Current License**: CC BY 4.0 (see LICENSE file)
- Changed from MIT to comply with competition winner requirements
- More permissive: allows commercial use with attribution
- Ensures medical AI research remains open and accessible

### External Tools & Data (Section 6)

**✅ ALLOWED - Meet Reasonableness Standard**:
| Tool/Service | Cost | Accessibility | License |
|-------------|------|---------------|---------|
| **MedGemma** | Free | HuggingFace gated model | HAI-DEF Terms |
| **Gemini API** | Free tier + paid | All participants | Google AI Terms |
| **PyTorch** | Free | Open source | BSD-3 |
| **Transformers** | Free | Open source | Apache 2.0 |
| **FastAPI** | Free | Open source | MIT |
| **Next.js** | Free | Open source | MIT |
| **HeroUI** | Free | Open source | MIT |
| **pdfplumber** | Free | Open source | MIT |
| **pytest** | Free | Open source | MIT |

**❌ NOT ALLOWED**:
- Proprietary datasets exceeding prize value
- Commercial software requiring expensive licenses
- Tools with geo-restrictions or limited accessibility
- APIs with per-call costs that exclude participants

### Compliance Checklist for New Features

Before suggesting or implementing any new external tool, library, or API:

- [ ] **Free/Open Source?** Must be MIT, Apache, BSD, or CC BY compatible
- [ ] **Accessible to all?** No paywalls, geo-restrictions, or limited access
- [ ] **Reproducible?** Judges must be able to replicate results without special access
- [ ] **Documented?** Clear setup instructions in README
- [ ] **Compatible with CC BY 4.0?** Can be included in open source release

**When in doubt**: Use only tools already listed in requirements.txt or package.json

---

## Current Status

### Completed

- [x] Project planning
- [x] Tech stack finalized
- [x] Architecture designed (v1: MedGemma-only)
- [x] Architecture upgraded (v2: Gemini orchestrator + MedGemma specialist)
- [x] Accept MedGemma license on HuggingFace
- [x] Set up Next.js frontend
- [x] Set up Python FastAPI backend
- [x] Test MedGemma 4B inference locally (AMD GPU working!)
- [x] Wire up FastAPI endpoints with MedGemma
- [x] Install HeroUI v3 + Agent Skills
- [x] Build Upload page (`/`)
- [x] Build Debate page (`/debate`)
- [x] Build Summary page (`/summary`)
- [x] Create GitHub repo (weekijie/Sturgeon)
- [x] Connect frontend to backend API
- [x] Test full E2E flow (Upload → Debate → Summary)
- [x] Implement Gemini orchestrator for multi-turn debate management
- [x] Structured clinical state for debate context
- [x] Gemini + MedGemma agentic architecture (code complete)
- [x] Add lab report file parsing (`/extract-labs-file`) — PDF/TXT upload, pdfplumber extraction, MedGemma structured parsing, lab values table UI
- [x] Add session persistence (localStorage) — lazy `useState` initializer reads from localStorage, `setCaseDataAndPersist` wrapper writes on every state change, zero `useEffect`, SSR-safe
- [x] Agentic flow code review — 12 fixes across backend + frontend
- [x] Verify MedSigLIP triage fixes (Validated with derm-melanoma.jpg E2E test)
- [x] Multi-file upload — simultaneous image + lab report upload, parallel `Promise.all` processing, individual remove buttons
- [x] Refusal preamble stripping — `_strip_refusal_preamble()` strips "I am unable to... However..." prefix when real analysis follows
- [x] Summary token limit bumped (2048 → 3072) to prevent truncated JSON
- [x] **Backend modularization** — split `main.py` (940 lines) into focused modules: `models.py`, `json_utils.py`, `refusal.py`, `formatters.py`
- [x] **Backend unit tests** — 41/41 passing (JSON parsing, refusal detection, formatters)
- [x] **Comprehensive error handling** — try/except on all endpoints with performance timing logs
- [x] **Pydantic request validation** — prevents empty inputs on all endpoints
- [x] **Few-shot prompt examples** — added to `extract-labs` and `differential` prompts for JSON stability
- [x] **Chain-of-Thought reasoning** — "think step-by-step" instruction for differential diagnosis
- [x] **Confidence percentage scale** — numeric 0-100 instead of high/medium/low
- [x] **Image context in debate fallback** — MedGemma-only path includes `image_context` from uploads
- [x] **Upload page input validation** — error banner when no evidence provided
- [x] **Suggested challenge prompts** — chip buttons in debate UI ("What if...", "Could this be...")
- [x] **Export case as PDF** — print-optimized `@media print` CSS on summary page
- [x] **Mobile responsive layout** — collapsible sidebar on debate page
- [x] **Visual probability bars** — sidebar diagnosis cards show probability as colored bars
- [x] **Comprehensive citation detection** — 15+ medical organizations (NCCN, AAD, ACR, ADA, AHA, ACC, CHEST, USPSTF, WHO, NICE, ASCO, ESMO) with smart deduplication
- [x] **Citation test suite** — 26 passing tests for all guideline sources
- [x] **Mobile UI polish** — Fixed text overflow in upload page, sidebar header spacing, touch-friendly interactions
- [x] **Hallucination prevention** — Prompt guardrails + validation module + auto-retry on detected fabrications
- [x] **Research attribution** — Added References section to README (CHECK, HALO, Guide-RAG, Mayo Reverse RAG)
- [x] **Hallucination test suite** — 15 tests for detection module (156 total tests passing)
- [x] **Guide-RAG alignment** — Aligned RAG implementation with arXiv:2510.15782 paper findings
- [x] **Added AAD melanoma guidelines** — ABCDE criteria, biopsy recommendations, staging (14 total guidelines)
- [x] **Added melanoma systematic review** — AI vs clinicians for skin cancer diagnosis (CC BY 4.0)
- [x] **RAG parameter tuning** — TOP_K=12, CHUNK_OVERLAP=500 for better comprehensiveness
- [x] **LLM-as-Judge evaluation framework** — Faithfulness, relevance, comprehensiveness metrics (Gemini-based)
- [x] **RAG evaluation endpoint** — `/rag-evaluate` for development/debugging
- [x] **Demo case realignment** — 3 cases: Melanoma, Pneumonia, Sepsis (aligned with corpus)
- [x] **Prompt guardrails hardening** — Removed hardcoded lab examples, prevents fabricated citations
- [x] **MedGemma CPU precision fix** — float32 fallback for CPU inference
- [x] **MedSigLIP safety** — model.eval() + skip wrong labels for unknown modality
- [x] **Hallucination detection improvements** — Position tracking, unit normalization, history extraction
- [x] **Session management** — MAX_SESSIONS cap, CORS trim, RAG eval guard
- [x] **RAG audit PHI redaction** — Digits masked, queries truncated in logs
- [x] **Frontend HeroUI v3 upgrade** — Fixed all component APIs for v3 compatibility
- [x] **Demo labs wiring** — Lab values now influence differential generation
- [x] **Rate-limit UI improvements** — Simplified countdown, reset on new requests
- [x] **Image context in debate** — MedGemma summary included for richer context
- [x] **API header unification** — Consistent rate-limit passthrough across routes
- [x] **Logo and branding** — Added SVG logo for README
- [x] **Pneumonia systematic review** — CAP antibiotic network meta-analysis, CURB-65 scoring (JGIM 2024)
- [x] **Sepsis systematic review** — SOFA/qSOFA/SIRS mortality prediction comparison (Arch Iran Med 2024)
- [x] **Guide-RAG GS-4 config complete** — 12 guidelines + 3 systematic reviews (all demo cases covered)
- [x] **Modal snapshot rollout** — CPU snapshot default, GPU snapshot opt-in (experimental)
- [x] **Modal runtime cache volumes** — Added vLLM cache volume alongside model and Chroma caches
- [x] **RAG query cache** — In-memory TTL+LRU-style retrieval cache for debate context
- [x] **Queue/timeout hardening** — Enabled input concurrency + aligned Vercel route maxDuration/timeouts
- [x] **vLLM queue observability** — Added `/vllm-metrics` debug endpoint
- [x] **NEXT_PATCH_PLAN applied** — RAG query clamp (<=480), token rebalance, and `/health` counters
- [x] **Citation fallback hardening** — CAP/PMC guideline links preserved via broader source mapping
- [x] **Demo PDF lab flow enabled** — Demo cases now load real lab PDFs through `/extract-labs-file`
- [x] **Analyze partial-success UX** — Image success preserved when lab extraction fails/timeouts
- [x] **Warmup probe simplification** — Immediate + 2-minute + fallback checks to reduce noisy health polling
- [x] **Deterministic lab parser hardening** — Multi-parser (`table-fast`/`table-full`/`flat-full`) before LLM fallback
- [x] **Production smoke recheck passed** — Demo + local sample PDFs extract successfully with fast-path counter deltas

### Next Steps (Priority Order)

1. [x] Apply `NEXT_PATCH_PLAN.md` (RAG query-length clamp + retry-churn reduction + counters)
2. [ ] Prepare demo script (`DEMO_SCRIPT.md`)
3. [ ] Record demo video (≤3 min)
4. [ ] Write submission document
5. [ ] Polish README with screenshots
6. [ ] Submit to Kaggle

---

## Changelog

See `CHANGELOG.md` for all code changes.

**Feb 7, 2026**: Backend integration complete. E2E flow working with MedGemma.
**Feb 7, 2026**: Architecture upgraded to Gemini orchestrator + MedGemma specialist (agentic dual-model).
**Feb 7, 2026**: Gemini orchestrator implemented (`gemini_orchestrator.py`). Agentic debate flow with Gemini managing conversation + MedGemma as callable tool. Graceful fallback to MedGemma-only if no API key. New SDK: `google-genai`.
**Feb 8, 2026**: Lab report file parsing feature complete. New `/extract-labs-file` endpoint (PDF via pdfplumber, TXT direct read, MedGemma structured parsing). Frontend: proxy route, CaseContext types, Upload page lab table UI (color-coded H/L/N), Debate page sidebar lab section. Bug fixes: button overflow, error message parsing (proxy JSON extraction + `errData.detail` fallback), MedGemma retry on JSON parse failure, max_new_tokens bumped to 2048.
**Feb 8, 2026**: Session persistence via localStorage. Zero-`useEffect` approach: lazy `useState` initializer for read, `setCaseDataAndPersist` wrapper for write. SSR-safe, size guard (strips imagePreviewUrl on quota exceeded), clean reset via `localStorage.removeItem`.
**Feb 8, 2026**: Agentic flow code review — 12 fixes. Backend: asyncio.to_thread for non-blocking inference, temperature parameterization (0.3 structured / 0.4 orchestrator / 0.7 debate), 60s Gemini timeout, dead code removal. Frontend: summary double-fire fix, error detail field consistency, sessionId persistence + chat reconstruction, suggested test banner, retry auto-resend, hydration mismatch fix, global-error.tsx for Next.js 16 Turbopack bug.
**Feb 12, 2026**: MedSigLIP triage accuracy improvement. Label engineering (8 zero-shot labels), confidence threshold fallback (modality="uncertain"), adaptive MedGemma prompt, image analysis temp=0.1.
**Feb 13, 2026**: Refactored `strip_disclaimers` → `_is_pure_refusal` (boolean refusal detector, no text modification). Fixed JSON newline repair with string-aware `_fix_newlines_in_json_strings()`. Added auto-retry for image analysis refusals. All 4 demo cases verified E2E.
**Feb 13, 2026**: Multi-file upload — `page.tsx` rewritten from single `file` state to `imageFile` + `labFile` slots. `processFiles()` classifies by type, `Promise.all` runs image analysis + lab extraction in parallel. Drop zone shows both files with individual ✕ remove buttons. Added `_strip_refusal_preamble()` to strip "I am unable to... However..." prefix. Summary `max_new_tokens` bumped 2048→3072.

**Feb 14, 2026**: Backend modularization + UI polish + test suite. Split monolithic `main.py` into focused modules (`models.py`, `json_utils.py`, `refusal.py`, `formatters.py`). Added comprehensive unit test suite (41 tests covering JSON parsing, refusal detection, formatters). Enhanced prompts with few-shot examples and Chain-of-Thought reasoning. Added input validation, suggested challenge chips, PDF export, mobile-responsive collapsible sidebar, and visual probability bars.

**Feb 16, 2026**: Hallucination prevention system. New `hallucination_check.py` module detects fabricated lab values. Integrated validation into `/differential` and `/debate-turn` endpoints with auto-retry. Added prompt guardrails removing hardcoded example values (8.2 g/dL hemoglobin). Fixed frontend state reset on new case. Added academic references (CHECK, HALO, Guide-RAG, Mayo Reverse RAG). 133 tests passing.

**Feb 21, 2026**: Hallucination hardening + HeroUI v3 upgrade. Backend: removed hardcoded ferritin from prompts, fixed MedGemma CPU precision (float32), MedSigLIP eval mode, improved hallucination detection (position/unit tracking), added session cap/CORS trim/RAG eval guard/PHI redaction, fixed AAD citation mapping. Frontend: wired demo labs, fixed reset after validation, simplified rate-limit UI, added MedGemma summary to image_context, unified API headers, upgraded to HeroUI v3 (fixed all component APIs), added logo. 156 tests passing.

**Feb 22, 2026**: Systematic review corpus expansion. Added `pneumonia_antibiotics_sr.md` (CAP antibiotic network meta-analysis, CURB-65, treatment recommendations — JGIM 2024) and `sepsis_qsofa_sr.md` (SOFA/qSOFA/SIRS mortality prediction comparison, scoring tables — Arch Iran Med 2024). Corpus: 12 guidelines + 3 systematic reviews. Guide-RAG GS-4 config complete for all 3 demo cases (Melanoma, Pneumonia, Sepsis).
**Feb 22-23, 2026**: Modal/Vercel production hardening complete for this pass. Added snapshot modes (CPU default, GPU opt-in), vLLM cache volume, RAG query cache, input concurrency, route timeout alignment, and `/vllm-metrics` observability. Post-deploy logs now meet key latency goals with remaining follow-up captured in `NEXT_PATCH_PLAN.md`.
**Feb 23, 2026**: Session 27 patch applied from `NEXT_PATCH_PLAN.md`. Added RAG query clamp (<=480 chars) before retrieval, increased differential/summary token budgets to reduce concise retries, and exposed retry/block counters in `/health` for faster `logchecklist.md` verification.
**Feb 23, 2026**: Sessions 28-33 follow-up hardening. Fixed CAP citation fallback mapping, switched demo cases to real PDF lab extraction, aligned warmup/timeout/partial-success frontend behavior, added deterministic multi-parser extraction (`table-fast`/`table-full`/`flat-full`) before LLM fallback, and validated production smoke tests on demo + local sample PDFs with `/health` extraction counters.

---

## When Uncertain

1. **API/Library questions**: Web search for documentation
2. **Technical details**: Verify, don't speculate
3. **Architecture decisions**: Check existing artifacts first
4. **Hackathon rules**: Reference `medgemma_hackathon_analysis.md`
