# Sturgeon

> Diagnostic Debate AI - House MD-style clinical reasoning

A web application that helps clinicians reduce diagnostic errors through structured AI-assisted debate.

## Project Structure

```
Sturgeon/
├── frontend/          # Next.js 14 (TypeScript + Tailwind)
├── ai-service/        # Python FastAPI + MedGemma
├── CLAUDE.md          # AI assistant instructions
└── STURGEON_PROJECT_PLAN.md
```

## Quick Start

### Frontend
```bash
cd frontend
npm install
npm run dev
# Opens http://localhost:3000
```

### AI Service
```bash
cd ai-service
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# API at http://localhost:8000
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | Python FastAPI |
| AI Model | MedGemma 4B (FP16) |

## MedGemma Impact Challenge

This project is built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/medgemma-impact-challenge) hackathon.

**Target**: Main Track + Agentic Workflow Prize

## License

MIT
