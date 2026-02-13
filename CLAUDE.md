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

| Constraint       | Details                                                      |
| ---------------- | ------------------------------------------------------------ |
| HAI-DEF Required | Must use MedGemma (Gemini allowed as orchestrator)           |
| Hardware         | AMD RX 9060 XT (16GB) → Use bfloat16                         |
| Deadline         | February 24, 2026 (ahead of schedule with AI assistance)     |
| MedGemma API     | Use `AutoModelForImageTextToText` + `AutoProcessor`          |
| AMD GPU          | Set `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`              |
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
- [x] Add lab report file parsing (`/extract-labs-file`) — PDF/TXT upload, pdfplumber extraction, MedGemma structured parsing, lab values table UI
- [x] Add session persistence (localStorage) — lazy `useState` initializer reads from localStorage, `setCaseDataAndPersist` wrapper writes on every state change, zero `useEffect`, SSR-safe
- [x] Agentic flow code review — 12 fixes across backend + frontend
- [x] Verify MedSigLIP triage fixes (Validated with derm-melanoma.jpg E2E test)
- [x] Multi-file upload — simultaneous image + lab report upload, parallel `Promise.all` processing, individual remove buttons
- [x] Refusal preamble stripping — `_strip_refusal_preamble()` strips "I am unable to... However..." prefix when real analysis follows
- [x] Summary token limit bumped (2048 → 3072) to prevent truncated JSON

### Next Steps (Priority Order)

1. [ ] Get higher-res breast carcinoma test image (current is 50×50px)
2. [ ] Prepare demo script (`DEMO_SCRIPT.md`)
3. [ ] Record demo video (≤3 min)
4. [ ] Write submission document
5. [ ] Polish README with screenshots
6. [ ] Deploy frontend to Vercel
7. [ ] Submit to Kaggle

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

---

## When Uncertain

1. **API/Library questions**: Web search for documentation
2. **Technical details**: Verify, don't speculate
3. **Architecture decisions**: Check existing artifacts first
4. **Hackathon rules**: Reference `medgemma_hackathon_analysis.md`
