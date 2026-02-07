# Sturgeon - Changelog

All notable changes to this project will be documented in this file.

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

## [2026-02-08] Sessions 8-9 — Light Theme Overhaul & Visual QA

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

## Future Changes

_Document all code changes below with date and description._
