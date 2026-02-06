# Sturgeon - Complete Project Plan

> **Deadline**: February 24, 2026 (~20 days remaining)  
> **Status**: Ready to Build

---

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Prize Strategy](#prize-strategy)
3. [Hackathon Compliance](#hackathon-compliance)
4. [Technical Stack](#technical-stack)
5. [Architecture](#architecture)
6. [The Debate Flow](#the-debate-flow)
7. [Prompt Engineering](#prompt-engineering)
8. [Hardware Setup](#hardware-setup)
9. [Project Structure](#project-structure)
10. [Timeline](#timeline)
11. [Demo Script](#demo-script)
12. [Submission Checklist](#submission-checklist)
13. [Risk Mitigation](#risk-mitigation)

---

## Project Overview

### The Problem
> **12 million Americans are misdiagnosed each year** (1 in 20 patients).
> *Source: BMJ Quality & Safety*

Misdiagnosis leads to delayed treatment, unnecessary procedures, and preventable deaths. The challenge: no clinician can hold all possible diagnoses in mind while evaluating a complex case.

### The Solution
**Sturgeon** is a diagnostic debate AI inspired by House MD. It simulates the collaborative reasoning that happens when a medical team debates a case:

1. Clinician uploads evidence (lab reports, patient history)
2. AI generates initial differential diagnoses with reasoning
3. Clinician challenges the AI's thinking
4. AI defends or updates its reasoning
5. Process repeats until diagnosis is reached

### Why This Works
In medical dramas like House MD, correct diagnoses emerge from debate—not from a single doctor's first impression. Sturgeon brings that collaborative reasoning process to every clinician.

---

## Prize Strategy

### Target Tracks

| Track | Prize Pool | Sturgeon Fit | Strategy |
|-------|-----------|--------------|----------|
| **Main Track** | $75K (Top 4) | ⭐⭐⭐⭐⭐ | Clear problem, quantified impact |
| **Agentic Workflow** | $10K (2 winners) | ⭐⭐⭐⭐⭐ | **Primary target** |
| Novel Task | $10K (2 winners) | ⭐⭐⭐ | Not the best fit |
| Edge AI | $5K | ⭐⭐ | Not targeting |

### Agentic Workflow Positioning

**Prize criteria** (from competition rules):
> "Awarded for the project that most effectively reimagines a complex workflow by deploying HAI-DEF models as intelligent agents or callable tools."

**How Sturgeon meets this**:

| Agentic Criterion | Sturgeon Implementation |
|-------------------|------------------------|
| Complex workflow reimagined | Differential diagnosis via multi-round debate |
| HAI-DEF as intelligent agent | MedGemma reasons, defends, updates autonomously |
| Callable tool behavior | Extract labs → Reason → Suggest tests → Update |
| Improved outcomes | Catches overlooked diagnoses |

---

## Hackathon Compliance

### Judging Criteria Mapping

| Criterion | Weight | How Sturgeon Scores |
|-----------|--------|---------------------|
| **Effective HAI-DEF Use** | 20% | MedGemma handles ALL reasoning: extraction, differential, debate, summary |
| **Problem Importance** | 15% | 12M misdiagnoses/year is quantifiable, severe |
| **Impact Potential** | 15% | Directly reduces diagnostic errors |
| **Technical Feasibility** | 20% | Proven stack (Next.js + FastAPI + MedGemma) |
| **Execution & Communication** | 30% | Structured demo, clear write-up, clean code |

*Source: [medgemma_hackathon_analysis.md](file:///C:/Users/weeki/.gemini/antigravity/brain/0317cc99-b5d0-40dd-a0ee-1df59c76af76/medgemma_hackathon_analysis.md)*

### Submission Requirements

| Requirement | Plan |
|-------------|------|
| Video Demo (≤3 min) | Scripted demo showing full debate flow |
| Write-up (≤3 pages) | Problem → Solution → Technical → Impact |
| Reproducible Code | GitHub repo with README, requirements.txt |
| **Bonus**: Live demo | Deploy to Vercel (free) |

---

## Technical Stack

**Single AI model. No alternatives. No Gemini.**

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Next.js 14 (App Router) | UI + API routes |
| Backend | Python FastAPI | MedGemma inference |
| AI Model | **MedGemma 4B-it** (bfloat16) | ALL medical reasoning |
| Hosting | Vercel (frontend) + local/Kaggle (AI) | Free deployment |

### Why MedGemma Only

1. **HAI-DEF requirement**: Must use at least one HAI-DEF model
2. **Maximize utilization score**: 20% of judging is "effective HAI-DEF use"
3. **Simplicity**: One model = fewer failure points, easier debugging
4. **MedGemma capabilities cover all needs**: Document understanding, clinical reasoning, text generation

### MedGemma 4B Capabilities Used

*Source: [hai_def_models_reference.md](file:///C:/Users/weeki/.gemini/antigravity/brain/0317cc99-b5d0-40dd-a0ee-1df59c76af76/hai_def_models_reference.md)*

| Capability | Sturgeon Usage |
|------------|----------------|
| Document Understanding | Extract lab values from PDF |
| Medical Text Reasoning | Generate differential diagnoses |
| Clinical Q&A | Respond to challenges |
| Text Generation | Produce explanations |

### MedGemma 4B Limitations & Mitigations

| Limitation | Mitigation |
|------------|------------|
| Not optimized for multi-turn | Re-inject full context each round (structured debate) |
| Prompt sensitivity | Carefully engineered prompts (see below) |
| Not clinical-grade | Clear disclaimers, educational framing |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NEXT.JS FRONTEND                            │
│                                                                     │
│  /                    → Upload lab PDF, enter patient history       │
│  /debate              → Chat-like debate interface                  │
│  /summary             → Final diagnosis display                     │
│                                                                     │
│  /api/extract         → Proxy to Python backend                     │
│  /api/differential    → Proxy to Python backend                     │
│  /api/debate          → Proxy to Python backend                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP (localhost:8000)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PYTHON FASTAPI                                │
│                                                                     │
│  POST /extract-labs                                                 │
│       Input: Lab report text/PDF                                    │
│       Output: Structured lab values                                 │
│       Model: MedGemma 4B                                            │
│                                                                     │
│  POST /differential                                                 │
│       Input: Lab values + patient history                           │
│       Output: 3-4 differential diagnoses with reasoning             │
│       Model: MedGemma 4B                                            │
│                                                                     │
│  POST /debate-turn                                                  │
│       Input: Full case context + user challenge                     │
│       Output: Defense/update + revised differential                 │
│       Model: MedGemma 4B                                            │
│                                                                     │
│  POST /summary                                                      │
│       Input: Full case context + final differential                 │
│       Output: Final diagnosis with reasoning chain                  │
│       Model: MedGemma 4B                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Debate Flow

### State Management

```typescript
interface CaseState {
  patientHistory: string;
  labValues: Record<string, { value: number; unit: string; isAbnormal: boolean }>;
  differential: Diagnosis[];
  debateRounds: Round[];
  currentRound: number;
}

interface Diagnosis {
  name: string;
  probability: "high" | "medium" | "low";
  supportingEvidence: string[];
  againstEvidence: string[];
}

interface Round {
  userChallenge: string;
  aiResponse: string;
  differentialUpdate: Diagnosis[];
}
```

### Flow Diagram

```
┌──────────────┐
│ Upload Labs  │
│ Enter History│
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌─────────────────────────────────┐
│ /extract-labs│────▶│ Structured lab values extracted │
└──────┬───────┘     └─────────────────────────────────┘
       │
       ▼
┌──────────────┐     ┌─────────────────────────────────┐
│ /differential│────▶│ Initial 3-4 diagnoses generated │
└──────┬───────┘     └─────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│            DEBATE LOOP (3-5 rounds)      │
│  ┌────────────────────────────────────┐  │
│  │ User: "But what about X symptom?"  │  │
│  └──────────────────┬─────────────────┘  │
│                     │                    │
│                     ▼                    │
│  ┌────────────────────────────────────┐  │
│  │ AI: Defends or updates reasoning   │  │
│  │     Updates differential           │  │
│  └──────────────────┬─────────────────┘  │
│                     │                    │
│         (Repeat until confident)         │
└─────────────────────┬────────────────────┘
                      │
                      ▼
┌──────────────┐     ┌─────────────────────────────────┐
│  /summary    │────▶│ Final diagnosis + reasoning     │
└──────────────┘     └─────────────────────────────────┘
```

---

## Prompt Engineering

### System Prompt (Used for All Endpoints)

```
You are a diagnostic team member in a clinical case discussion. Your role is to:
1. Analyze clinical evidence carefully
2. Generate and defend differential diagnoses
3. Acknowledge valid challenges and update your reasoning
4. Explain your thinking clearly

Always cite specific evidence from the case when making claims.
Use phrases like "Based on the elevated ferritin of 847..." not just "The labs suggest..."
```

### Extract Labs Prompt

```
Extract all lab values from the following report. For each value, provide:
- Test name
- Value
- Unit
- Reference range (if available)
- Whether it is abnormal (high/low/normal)

Return as structured JSON.

Report:
{lab_report_text}
```

### Initial Differential Prompt

```
Based on the following case, generate 3-4 differential diagnoses.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

For each diagnosis, provide:
1. Diagnosis name
2. Probability (high/medium/low)
3. Supporting evidence from this case
4. Evidence that argues against this diagnosis
5. Tests that would help confirm or rule out

Format as structured JSON.
```

### Debate Turn Prompt

```
You are in a diagnostic debate. The current case and your previous reasoning are below.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

Current Differential:
{current_differential}

Previous Reasoning:
{previous_rounds}

The clinician challenges your thinking:
"{user_challenge}"

Respond by:
1. Acknowledging the point if valid
2. Defending your reasoning with evidence, or updating it
3. Providing an updated differential if warranted
4. Suggesting a test if it would help clarify

Be conversational but precise.
```

---

## Hardware Setup

### Verified Configuration

| Component | Spec | Purpose |
|-----------|------|---------|
| GPU | **AMD RX 9060 XT (16GB VRAM)** | MedGemma inference |
| CPU | AMD Ryzen 5 3600 | General compute |
| RAM | 32GB | Model loading headroom |

### AMD GPU Requirements (ROCm 7.2)

**Required environment variable:**
```powershell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"
```

### MedGemma 4B Memory Footprint

| Precision | VRAM Required | Fits 9060 XT? | Quality |
|-----------|---------------|---------------|---------|
| **bfloat16 (required for AMD)** | **~8-10 GB** | ✅ Yes | **Full quality** |
| float16 | ~8-10 GB | ❌ Empty output on AMD | N/A |

### Model Setup (AMD ROCm - Verified Working)

```python
# ai-service/medgemma.py
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch

# MedGemma 4B-it is a vision-language model!
processor = AutoProcessor.from_pretrained("google/medgemma-4b-it")
model = AutoModelForImageTextToText.from_pretrained(
    "google/medgemma-4b-it",
    torch_dtype=torch.bfloat16,  # MUST be bfloat16 for AMD
    device_map="auto"
)

# Chat format with content lists
messages = [{
    "role": "user",
    "content": [{"type": "text", "text": "Your prompt here"}]
}]

inputs = processor.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_dict=True,
    return_tensors="pt"
).to(model.device, dtype=torch.bfloat16)
```

### Kaggle Backup Option

If local GPU issues arise, use Kaggle notebooks:
- Free T4 GPU (16GB VRAM)
- Can run MedGemma 4B in FP16 directly
- Judges can reproduce this setup

---

## Project Structure

```
dxdebate/
├── frontend/                        # Next.js 14
│   ├── app/
│   │   ├── page.tsx                # Home: upload + history
│   │   ├── debate/
│   │   │   └── page.tsx            # Debate chat UI
│   │   ├── summary/
│   │   │   └── page.tsx            # Final diagnosis
│   │   └── api/
│   │       ├── extract/route.ts    # → Python /extract-labs
│   │       ├── differential/route.ts # → Python /differential
│   │       └── debate/route.ts     # → Python /debate-turn
│   ├── components/
│   │   ├── LabUpload.tsx           # PDF upload component
│   │   ├── LabDisplay.tsx          # Show extracted values
│   │   ├── DifferentialCard.tsx    # Single diagnosis card
│   │   ├── DifferentialList.tsx    # List of diagnoses
│   │   └── DebateChat.tsx          # Chat interface
│   ├── lib/
│   │   └── api.ts                  # API client
│   ├── package.json
│   └── tailwind.config.js
│
├── ai-service/                      # Python FastAPI
│   ├── main.py                     # FastAPI app + routes
│   ├── medgemma.py                 # Model loading + inference
│   ├── prompts.py                  # Prompt templates
│   ├── schemas.py                  # Pydantic models
│   └── requirements.txt
│
├── docker-compose.yml              # Local development
├── README.md                       # Setup instructions
└── SUBMISSION/
    ├── video.mp4                   # Demo video
    └── writeup.md                  # Technical write-up
```

---

## Timeline

**Available time**: ~85 hours (2-3h weekdays + full weekends)

| Week | Dates | Focus | Deliverable | Hours |
|------|-------|-------|-------------|-------|
| **1** | Feb 4-9 | Foundation | MedGemma inference working, FastAPI endpoints, Next.js shell | 20h |
| **2** | Feb 10-16 | Core Features | Full debate flow, UI complete, 2 demo cases working | 24h |
| **3** | Feb 17-23 | Polish | Demo video, write-up, GitHub cleanup, Vercel deploy | 20h |
| Buffer | Ongoing | Issues | Bug fixes, edge cases | 15h |

### Week 1 Milestones
- [x] MedGemma 4B running locally (bfloat16 on AMD)
- [x] HuggingFace login verified
- [x] Next.js frontend initialized
- [x] FastAPI backend initialized
- [ ] `/extract-labs` endpoint working
- [ ] `/differential` endpoint working

### Week 2 Milestones
- [ ] `/debate-turn` endpoint working
- [ ] Full debate flow from upload to summary
- [ ] 2 demo cases prepared and tested
- [ ] UI polished

### Week 3 Milestones
- [ ] Demo video recorded (≤3 min)
- [ ] Write-up completed (≤3 pages)
- [ ] GitHub repo cleaned up with README
- [ ] Live demo on Vercel
- [ ] Submitted to Kaggle

---

## Demo Script

**Total: 3 minutes**

### [0:00-0:20] Hook
> "12 million Americans are misdiagnosed every year. In shows like House MD, correct diagnoses come from debate—doctors challenging each other's thinking. Sturgeon brings that process to every clinician."

### [0:20-0:50] Upload Evidence
- Show: Upload lab report PDF
- Show: MedGemma extracts values, highlights abnormals
- Show: Enter patient history (text input)

### [0:50-1:20] Initial Differential
- Show: AI generates 3-4 diagnoses
- Show: Each has probability, supporting evidence, counter-evidence
- Highlight: "Let's challenge the AI's thinking"

### [1:20-2:20] Debate Rounds (2-3)
**Round 1:**
- User: "But the CRP is elevated with normal WBC—doesn't that rule out bacterial infection?"
- AI: "Good point. Elevated CRP with normal WBC suggests viral or inflammatory etiology. Updating bacterial pneumonia to low probability."

**Round 2:**
- User: "What test would differentiate the remaining diagnoses?"
- AI: "A ferritin level would help. Elevated ferritin with these findings would point toward hemochromatosis."
- User: "Ferritin is 847."
- AI: "That strongly supports hemochromatosis. Recommend genetic testing for HFE mutations."

### [2:20-2:50] Summary
- Show: Final diagnosis with full reasoning chain
- Show: What was ruled out and why
- Show: Recommended next steps

### [2:50-3:00] Closing
> "DxDebate: Every clinician deserves a team to challenge their thinking."

---

## Submission Checklist

### Required
- [ ] Video demo uploaded (≤3 min, MP4)
- [ ] Write-up completed (≤3 pages, using Kaggle template)
- [ ] Public GitHub repository with:
  - [ ] README with setup instructions
  - [ ] requirements.txt / package.json
  - [ ] MIT license
  - [ ] Clear code organization
- [ ] Kaggle Writeup created and submitted

### Bonus (Improves Score)
- [ ] Live demo on Vercel
- [ ] HuggingFace model page (prompt templates)

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| MedGemma multi-turn degrades | Medium | High | Re-inject full context each round |
| Quantization hurts quality | N/A | N/A | Using FP16 (full quality) |
| Time overrun | Medium | High | Scope down to labs-only first |
| Demo case fails on video | Medium | High | Prepare 3 cases, use most reliable |
| GPU issues on 9060 XT | Low | Medium | Kaggle backup ready |

---

## Pre-Build Checklist

- [x] Accept MedGemma license on HuggingFace
- [x] Install ROCm 7.2 and PyTorch with ROCm support
- [x] Create GitHub repo
- [x] Initialize Next.js project
- [x] Initialize Python FastAPI project
- [x] Verify MedGemma inference runs locally (bfloat16 on AMD)

---

**Ready to build. All details verified. MedGemma only.**
