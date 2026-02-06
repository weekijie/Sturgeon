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

## Future Changes

_Document all code changes below with date and description._
