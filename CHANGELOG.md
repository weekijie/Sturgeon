# Sturgeon - Changelog

All notable changes to this project will be documented in this file.

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