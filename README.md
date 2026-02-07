# Sturgeon

> Diagnostic Debate AI - House MD-style clinical reasoning

A web application that helps clinicians reduce diagnostic errors through structured AI-assisted debate. Users upload medical evidence, AI generates differential diagnoses, users challenge the AI's reasoning, and together they iterate toward a diagnosis.

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/medgemma-impact-challenge) hackathon.

**Target**: Main Track + Agentic Workflow Prize

## Architecture

Sturgeon uses an **agentic dual-model architecture**:

- **MedGemma 1.5 4B-it** (HAI-DEF model) = Medical Specialist. Handles all clinical reasoning, differential diagnosis, medical image analysis, and evidence evaluation as a callable tool.
- **Gemini 3 Flash** = Orchestrator. Manages multi-turn conversation context, summarizes debate state, formulates focused questions for MedGemma, and synthesizes responses.

This maps directly to the Agentic Workflow Prize: _"deploying HAI-DEF models as intelligent agents or callable tools."_

```
User challenge
  -> Gemini: formulate focused question for MedGemma
    -> MedGemma: clinical reasoning (single-turn)
  -> Gemini: synthesize into response + updated differential
<- Response with updated diagnoses
```

## Tech Stack

| Layer        | Technology                                                 |
| ------------ | ---------------------------------------------------------- |
| Frontend     | Next.js 14 (App Router) + HeroUI v3                        |
| Backend      | Python FastAPI                                             |
| Medical AI   | MedGemma 1.5 4B-it (bfloat16, AutoModelForImageTextToText) |
| Orchestrator | Gemini 3 Flash Preview (Google AI API)                     |
| Hosting      | Vercel (frontend) + local/Kaggle (AI)                      |

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.10+
- CUDA-compatible GPU (16GB+ VRAM) or AMD GPU with ROCm
- [MedGemma access on HuggingFace](https://huggingface.co/google/medgemma-1.5-4b-it)
- [Gemini API key](https://aistudio.google.com/apikey) (optional -- falls back to MedGemma-only mode)

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens http://localhost:3000
```

### AI Service

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r ai-service/requirements.txt

# Set up environment
cp ai-service/.env.example ai-service/.env
# Edit ai-service/.env with your GEMINI_API_KEY

# AMD GPU only:
# set TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1

# Run the service
python -m uvicorn ai-service.main:app --port 8000
# API at http://localhost:8000
```

## Project Structure

```
Sturgeon/
├── frontend/                   # Next.js 14
│   ├── app/
│   │   ├── page.tsx           # Upload + history
│   │   ├── debate/page.tsx    # Debate chat
│   │   ├── summary/page.tsx   # Final diagnosis
│   │   ├── context/           # React Context (case state)
│   │   └── api/               # Routes -> Python backend
│   └── components/
│
├── ai-service/                 # Python FastAPI
│   ├── main.py                # Endpoints + session management
│   ├── medgemma.py            # MedGemma model loader + inference
│   ├── gemini_orchestrator.py # Gemini orchestrator + clinical state
│   ├── prompts.py             # Prompt templates
│   └── .env.example           # Environment variable template
│
├── CLAUDE.md                   # AI assistant instructions
├── STURGEON_PROJECT_PLAN.md    # Full technical plan
└── CHANGELOG.md                # All code changes
```

## API Endpoints

| Endpoint         | Method | Description                                                         |
| ---------------- | ------ | ------------------------------------------------------------------- |
| `/health`        | GET    | Health check + orchestrator status                                  |
| `/analyze-image` | POST   | Analyze medical images (MedSigLIP triage + MedGemma interpretation) |
| `/extract-labs`  | POST   | Extract structured lab values from text                             |
| `/differential`  | POST   | Generate initial differential diagnoses                             |
| `/debate-turn`   | POST   | Handle a debate round (orchestrated)                                |
| `/summary`       | POST   | Generate final diagnosis summary                                    |

## License

MIT
