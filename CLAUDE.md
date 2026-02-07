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

| Layer         | Technology                                                 | Role                          |
| ------------- | ---------------------------------------------------------- | ----------------------------- |
| Frontend      | Next.js 14 (App Router) + **HeroUI v3**                    | UI + API routes               |
| Backend       | Python FastAPI                                             | Orchestration + inference     |
| Medical AI    | **MedGemma 4B-it** (bfloat16, via AutoModelForImageTextToText) | Medical reasoning, image analysis, differential diagnosis |
| Orchestrator  | **Gemini Pro/Flash** (Google AI API)                        | Conversation management, context summarization, debate flow |
| Hosting       | Vercel (frontend) + local/Kaggle (AI)                      | Free deployment               |

> **Note**: Tailwind v4 uses `@theme` syntax which may trigger "Unknown at rule" warnings in IDEs. These are false positives.

### Architecture: Agentic Dual-Model

- **MedGemma** = Medical Specialist (callable tool). Handles all clinical reasoning, medical image analysis, lab extraction, differential diagnosis. This is the HAI-DEF model.
- **Gemini** = Orchestrator. Manages multi-turn conversation context, summarizes debate state, routes medical questions to MedGemma. Handles what MedGemma wasn't trained for (multi-turn conversation).

This framing directly maps to the Agentic Workflow Prize: "deploying HAI-DEF models as intelligent agents or callable tools."

### Brand Identity

- **Design System**: Medical Dark Theme (Slate #0F172A)
- **Key UI Elements**: Glassmorphism headers, Pulse animations, Teal accents
- **Typography**: Outfit (Modern, Geometric)

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

1. **Surgical changes only**: Make minimal, focused fixes
2. **Evidence-based debugging**: Add minimal, targeted logging
3. **Fix root causes**: Address underlying issues, not symptoms
4. **Simple > Complex**: Let TypeScript catch errors, not excessive runtime checks
5. **Collaborative process**: Work with user to identify most efficient solution
6. **Web search when uncertain**: Verify APIs/libraries via documentation, don't assume

---

## Project Structure

```
Sturgeon/
├── frontend/                   # Next.js 14
│   ├── app/
│   │   ├── page.tsx           # Upload + history
│   │   ├── debate/page.tsx    # Debate chat
│   │   └── api/               # Routes → Python
│   └── components/
│
├── ai-service/                 # Python FastAPI
│   ├── main.py                # Endpoints
│   ├── medgemma.py            # Model inference
│   └── prompts.py             # Prompt templates
│
├── CLAUDE.md                   # This file
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

| Constraint       | Details                                                   |
| ---------------- | --------------------------------------------------------- |
| HAI-DEF Required | Must use MedGemma (Gemini allowed as orchestrator)        |
| Hardware         | AMD RX 9060 XT (16GB) → Use bfloat16                     |
| Deadline         | February 24, 2026 (ahead of schedule with AI assistance)  |
| MedGemma API     | Use `AutoModelForImageTextToText` + `AutoProcessor`       |
| AMD GPU          | Set `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`           |
| Gemini API       | Paid key available. Free tier also works for reproducibility |

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

### In Progress

- [ ] Test full E2E agentic flow (Gemini orchestrator + MedGemma)

### Next Steps (Priority Order)

1. [ ] Test and validate agentic debate flow end-to-end
2. [ ] Add medical image analysis (MedGemma multimodal -- chest X-ray, dermatology, pathology)
3. [ ] Add lab report file parsing (`/extract-labs`)
4. [ ] Add session persistence (localStorage)
5. [ ] Prepare demo cases
6. [ ] RAG with clinical guidelines (stretch goal)
7. [ ] Fine-tune MedGemma for debate (stretch goal)

---

## Changelog

See `CHANGELOG.md` for all code changes.

**Feb 7, 2026**: Backend integration complete. E2E flow working with MedGemma.
**Feb 7, 2026**: Architecture upgraded to Gemini orchestrator + MedGemma specialist (agentic dual-model).
**Feb 7, 2026**: Gemini orchestrator implemented (`gemini_orchestrator.py`). Agentic debate flow with Gemini managing conversation + MedGemma as callable tool. Graceful fallback to MedGemma-only if no API key. New SDK: `google-genai`.

---

## When Uncertain

1. **API/Library questions**: Web search for documentation
2. **Technical details**: Verify, don't speculate
3. **Architecture decisions**: Check existing artifacts first
4. **Hackathon rules**: Reference `medgemma_hackathon_analysis.md`
