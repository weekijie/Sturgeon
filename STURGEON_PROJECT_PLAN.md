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
> _Source: BMJ Quality & Safety_

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

| Track                | Prize Pool       | Sturgeon Fit | Strategy                         |
| -------------------- | ---------------- | ------------ | -------------------------------- |
| **Main Track**       | $75K (Top 4)     | ⭐⭐⭐⭐⭐   | Clear problem, quantified impact |
| **Agentic Workflow** | $10K (2 winners) | ⭐⭐⭐⭐⭐   | **Primary target**               |
| Novel Task           | $10K (2 winners) | ⭐⭐⭐       | Not the best fit                 |
| Edge AI              | $5K              | ⭐⭐         | Not targeting                    |

### Agentic Workflow Positioning

**Prize criteria** (from competition rules):

> "Awarded for the project that most effectively reimagines a complex workflow by deploying HAI-DEF models as intelligent agents or callable tools."

**How Sturgeon meets this**:

| Agentic Criterion            | Sturgeon Implementation                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------------------- |
| Complex workflow reimagined  | Differential diagnosis via multi-round debate                                                     |
| HAI-DEF as intelligent agent | MedGemma as callable medical specialist tool                                                      |
| Callable tool behavior       | Gemini orchestrator calls MedGemma for: extract labs, reason, analyze images, update differential |
| Improved outcomes            | Catches overlooked diagnoses through structured debate                                            |

---

## Hackathon Compliance

### Judging Criteria Mapping

| Criterion                     | Weight | How Sturgeon Scores                                                       |
| ----------------------------- | ------ | ------------------------------------------------------------------------- |
| **Effective HAI-DEF Use**     | 20%    | MedGemma handles ALL reasoning: extraction, differential, debate, summary |
| **Problem Importance**        | 15%    | 12M misdiagnoses/year is quantifiable, severe                             |
| **Impact Potential**          | 15%    | Directly reduces diagnostic errors                                        |
| **Technical Feasibility**     | 20%    | Proven stack (Next.js + FastAPI + MedGemma)                               |
| **Execution & Communication** | 30%    | Structured demo, clear write-up, clean code                               |

_Source: [medgemma_hackathon_analysis.md](file:///C:/Users/weeki/.gemini/antigravity/brain/0317cc99-b5d0-40dd-a0ee-1df59c76af76/medgemma_hackathon_analysis.md)_

### Submission Requirements

| Requirement          | Plan                                      |
| -------------------- | ----------------------------------------- |
| Video Demo (≤3 min)  | Scripted demo showing full debate flow    |
| Write-up (≤3 pages)  | Problem → Solution → Technical → Impact   |
| Reproducible Code    | GitHub repo with README, requirements.txt |
| **Bonus**: Live demo | Deploy to Vercel (free)                   |

---

## Technical Stack

### Dual-Model Agentic Architecture

| Layer        | Technology                            | Purpose                               |
| ------------ | ------------------------------------- | ------------------------------------- |
| Frontend     | Next.js 14 (App Router) + HeroUI v3   | UI + API routes                       |
| Backend      | Python FastAPI                        | Orchestration + inference             |
| Medical AI   | **MedGemma 4B-it** (bfloat16)         | ALL medical reasoning + images        |
| Orchestrator | **Gemini Flash** (Google AI API)      | Conversation management + debate flow |
| Hosting      | Vercel (frontend) + local/Kaggle (AI) | Free deployment                       |

### Why Dual-Model (MedGemma + Gemini)

1. **HAI-DEF requirement**: MedGemma handles ALL medical reasoning (maximizes HAI-DEF utilization score)
2. **Agentic Workflow Prize**: MedGemma as callable medical specialist tool, Gemini as orchestrator -- textbook agentic architecture
3. **MedGemma's limitation**: Not optimized for multi-turn conversation. Gemini handles what MedGemma can't (context management, summarization)
4. **Competition rules**: Gemini is explicitly permitted as an external tool (Section 6.c of rules)
5. **Quality**: Each model does what it's best at -- MedGemma for medicine, Gemini for conversation

### MedGemma 4B Capabilities Used

_Source: [hai_def_models_reference.md](file:///C:/Users/weeki/.gemini/antigravity/brain/0317cc99-b5d0-40dd-a0ee-1df59c76af76/hai_def_models_reference.md)_

| Capability                 | Sturgeon Usage                              |
| -------------------------- | ------------------------------------------- |
| Document Understanding     | Extract lab values from PDF                 |
| Medical Text Reasoning     | Generate differential diagnoses             |
| Clinical Q&A               | Respond to challenges                       |
| Text Generation            | Produce explanations                        |
| **Medical Image Analysis** | Chest X-ray, dermatology, pathology, fundus |

### MedGemma 4B Limitations & Mitigations

| Limitation                   | Mitigation                                                                              |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| Not optimized for multi-turn | Gemini orchestrates conversation, MedGemma handles medical queries as single-turn calls |
| Prompt sensitivity           | Carefully engineered prompts (see below)                                                |
| Not clinical-grade           | Clear disclaimers, educational framing                                                  |
| Single-image tasks only      | One image per MedGemma call, orchestrated by Gemini                                     |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NEXT.JS FRONTEND                            │
│                                                                     │
│  /                    → Upload labs, images, patient history        │
│  /debate              → Chat-like debate interface                  │
│  /summary             → Final diagnosis display                     │
│                                                                     │
│  /api/extract         → Proxy to Python backend                     │
│  /api/differential    → Proxy to Python backend                     │
│  /api/debate          → Proxy to Python backend                     │
│  /api/analyze-image   → Proxy to Python backend                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP (localhost:8000)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PYTHON FASTAPI                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              GEMINI ORCHESTRATOR                             │   │
│  │                                                             │   │
│  │  - Manages multi-turn conversation context                  │   │
│  │  - Maintains structured clinical state                      │   │
│  │  - Summarizes debate history                                │   │
│  │  - Decides when to call MedGemma                            │   │
│  │  - Routes medical questions to MedGemma                     │   │
│  │  - Formats final responses to user                          │   │
│  └──────────────────────┬──────────────────────────────────────┘   │
│                          │ (calls as tool)                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              MEDGEMMA SPECIALIST (HAI-DEF)                  │   │
│  │                                                             │   │
│  │  - Extract lab values from text/PDF                         │   │
│  │  - Analyze medical images (X-ray, derm, pathology)          │   │
│  │  - Generate differential diagnoses                          │   │
│  │  - Clinical reasoning for specific questions                │   │
│  │  - Evidence-based responses with citations                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow Per Debate Turn

```
User sends challenge
        │
        ▼
Gemini receives: clinical_state + conversation_summary + user_challenge
        │
        ├─→ Decides: Does this need MedGemma? (medical question)
        │       │
        │       ▼ YES
        │   MedGemma receives: focused medical query + relevant patient data
        │   MedGemma returns: clinical reasoning + updated differential
        │       │
        │       ▼
        │   Gemini integrates MedGemma's response
        │
        ├─→ NO (conversational/clarification)
        │   Gemini handles directly
        │
        ▼
Gemini returns: response + updated clinical_state + updated conversation_summary
```

---

## The Debate Flow

### State Management

```typescript
interface CaseState {
  patientHistory: string;
  labValues: Record<
    string,
    { value: number; unit: string; isAbnormal: boolean }
  >;
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

| Component | Spec                           | Purpose                |
| --------- | ------------------------------ | ---------------------- |
| GPU       | **AMD RX 9060 XT (16GB VRAM)** | MedGemma inference     |
| CPU       | AMD Ryzen 5 3600               | General compute        |
| RAM       | 32GB                           | Model loading headroom |

### AMD GPU Requirements (ROCm 7.2)

**Required environment variable:**

```powershell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"
```

### MedGemma 4B Memory Footprint

| Precision                       | VRAM Required | Fits 9060 XT?          | Quality          |
| ------------------------------- | ------------- | ---------------------- | ---------------- |
| **bfloat16 (required for AMD)** | **~8-10 GB**  | ✅ Yes                 | **Full quality** |
| float16                         | ~8-10 GB      | ❌ Empty output on AMD | N/A              |

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
Sturgeon/
├── frontend/                        # Next.js 14
│   ├── app/
│   │   ├── page.tsx                # Home: upload + history ✅
│   │   ├── debate/
│   │   │   └── page.tsx            # Debate chat UI ✅
│   │   ├── summary/
│   │   │   └── page.tsx            # Final diagnosis ✅
│   │   ├── context/
│   │   │   └── CaseContext.tsx     # State management ✅
│   │   └── api/
│   │       ├── differential/route.ts # → Python /differential ✅
│   │       ├── debate-turn/route.ts  # → Python /debate-turn ✅
│   │       └── summary/route.ts      # → Python /summary ✅
│   ├── package.json
│   └── tailwind.config.js
│
├── ai-service/                      # Python FastAPI
│   ├── main.py                     # FastAPI app + routes ✅
│   ├── medgemma.py                 # Model loading + inference ✅
│   ├── prompts.py                  # Prompt templates ✅
│   └── requirements.txt
│
├── CLAUDE.md                       # AI assistant instructions
├── CHANGELOG.md                    # Session-by-session changes
├── STURGEON_PROJECT_PLAN.md        # This file
├── README.md                       # Setup instructions
└── SUBMISSION/
    ├── video.mp4                   # Demo video
    └── writeup.md                  # Technical write-up
```

---

## Timeline

**Available time**: ~85 hours (2-3h weekdays + full weekends)

| Week   | Dates     | Focus         | Deliverable                                                  | Hours |
| ------ | --------- | ------------- | ------------------------------------------------------------ | ----- |
| **1**  | Feb 4-9   | Foundation    | MedGemma inference working, FastAPI endpoints, Next.js shell | 20h   |
| **2**  | Feb 10-16 | Core Features | Full debate flow, UI complete, 2 demo cases working          | 24h   |
| **3**  | Feb 17-23 | Polish        | Demo video, write-up, GitHub cleanup, Vercel deploy          | 20h   |
| Buffer | Ongoing   | Issues        | Bug fixes, edge cases                                        | 15h   |

### Week 1 Milestones ✅

- [x] MedGemma 4B running locally (bfloat16 on AMD)
- [x] HuggingFace login verified
- [x] Next.js frontend initialized
- [x] FastAPI backend initialized
- [x] `/extract-labs` endpoint working
- [x] `/differential` endpoint working

### Week 2 Milestones (In Progress)

- [x] `/debate-turn` endpoint working
- [x] `/summary` endpoint working
- [x] Full E2E flow from upload to summary
- [x] Architecture upgraded to Gemini + MedGemma agentic dual-model
- [x] Implement Gemini orchestrator + structured clinical state
- [x] Fix multi-turn debate with Gemini as conversation manager
- [x] Add medical image analysis (MedGemma multimodal)
- [x] 4 demo cases prepared and tested (melanoma, psoriasis, carcinoma, adenocarcinoma)
- [x] UI polished

### Week 3 Milestones

- [x] Add lab report file parsing (`/extract-labs`)
- [x] Add session persistence (localStorage)
- [x] Multi-file upload (image + lab report simultaneously)
- [x] Refusal preamble stripping for cleaner MedGemma output
- [ ] RAG with clinical guidelines (stretch goal)
- [ ] Fine-tune MedGemma for debate (stretch goal)
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
- [ ] CC BY 4.0 license
  - [ ] Clear code organization
- [ ] Kaggle Writeup created and submitted

### Bonus (Improves Score)

- [ ] Live demo on Vercel
- [ ] HuggingFace model page (prompt templates)

---

## Risk Mitigation

| Risk                         | Probability | Impact   | Mitigation                                                                   |
| ---------------------------- | ----------- | -------- | ---------------------------------------------------------------------------- |
| MedGemma multi-turn degrades | ~~Medium~~  | ~~High~~ | Solved: Gemini handles multi-turn, MedGemma does single-turn medical queries |
| Gemini API downtime          | Low         | High     | Can fall back to structured-state-only approach                              |
| Quantization hurts quality   | N/A         | N/A      | Using bfloat16 (full quality)                                                |
| Time overrun                 | Low         | Medium   | Ahead of schedule with AI assistance                                         |
| Demo case fails on video     | Medium      | High     | Prepare 3 cases, use most reliable                                           |
| GPU issues on 9060 XT        | Low         | Medium   | Kaggle backup ready                                                          |

---

## Pre-Build Checklist

- [x] Accept MedGemma license on HuggingFace
- [x] Install ROCm 7.2 and PyTorch with ROCm support
- [x] Create GitHub repo
- [x] Initialize Next.js project
- [x] Initialize Python FastAPI project
- [x] Verify MedGemma inference runs locally (bfloat16 on AMD)

---

**Ready to build. Architecture upgraded to agentic dual-model (Gemini + MedGemma).**
