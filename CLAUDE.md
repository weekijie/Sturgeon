# Sturgeon - Project Instructions

> **Project**: Sturgeon - Diagnostic Debate AI
> **Workspace**: `c:\Users\weeki\Documents\GitHub\Sturgeon`
> **Deadline**: February 24, 2026

---

## 🎯 Project Summary

**Sturgeon** is a House MD / Good Doctor-style diagnostic debate AI for the MedGemma Impact Challenge. Users upload evidence, AI generates differentials, users challenge the AI, and together they arrive at a diagnosis.

**Prize Target**: Main Track + Agentic Workflow Prize ($5K)

---

## 🔧 Tech Stack (Final, No Alternatives)

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 (App Router) |
| Backend | Python FastAPI |
| AI Model | MedGemma 4B-it (bfloat16, via AutoModelForImageTextToText) |
| Hosting | Vercel (free) |

**No Gemini. No fallbacks. MedGemma only.**

### AMD GPU Setup (Required)
```powershell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"
```

---

## 📋 Design Principles

1. **Don't overengineer**: Simple beats complex
2. **No fallbacks**: One correct path, no alternatives
3. **One way**: One way to do things, not many
4. **Clarity over compatibility**: Clear code beats backward compatibility
5. **Throw errors**: Fail fast when preconditions aren't met
6. **No backups**: Trust the primary mechanism
7. **Separation of concerns**: Each function has single responsibility

---

## 🛠️ Development Methodology

1. **Surgical changes only**: Make minimal, focused fixes
2. **Evidence-based debugging**: Add minimal, targeted logging
3. **Fix root causes**: Address underlying issues, not symptoms
4. **Simple > Complex**: Let TypeScript catch errors, not excessive runtime checks
5. **Collaborative process**: Work with user to identify most efficient solution
6. **Web search when uncertain**: Verify APIs/libraries via documentation, don't assume

---

## 📁 Project Structure

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

## 🔑 Key Files Reference

| File | Purpose |
|------|---------|
| `brain/.../sturgeon_project_summary.md` | Complete technical plan |
| `brain/.../hai_def_models_reference.md` | MedGemma capabilities |
| `brain/.../medgemma_hackathon_analysis.md` | Hackathon details |

---

## ⚠️ Critical Constraints

| Constraint | Details |
|------------|---------|
| HAI-DEF Required | Must use MedGemma (no vanilla Gemini) |
| Hardware | AMD RX 9060 XT (16GB) → Use bfloat16 |
| Time | ~19 days remaining |
| MedGemma API | Use `AutoModelForImageTextToText` + `AutoProcessor` |
| AMD GPU | Set `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` |

---

## 🚀 Current Status

### Completed
- [x] Project planning
- [x] Tech stack finalized
- [x] Architecture designed
- [x] Accept MedGemma license on HuggingFace
- [x] Set up Next.js frontend
- [x] Set up Python FastAPI backend
- [x] Test MedGemma 4B inference locally (AMD GPU working!)

### In Progress
- [ ] Wire up FastAPI endpoints with MedGemma
- [ ] Build frontend UI

---

## 📝 Changelog

See `CHANGELOG.md` for all code changes.

**Feb 6, 2026**: Project setup complete. MedGemma 4B working on AMD RX 9060 XT with bfloat16.

---

## 🔍 When Uncertain

1. **API/Library questions**: Web search for documentation
2. **Technical details**: Verify, don't speculate
3. **Architecture decisions**: Check existing artifacts first
4. **Hackathon rules**: Reference `medgemma_hackathon_analysis.md`
