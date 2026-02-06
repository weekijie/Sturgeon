# Sturgeon AI Service

FastAPI backend for MedGemma inference.

## Setup

```bash
cd ai-service
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Run

**For AMD GPUs (ROCm):**
```powershell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"
uvicorn main:app --reload --port 8000
```

## Endpoints

- `POST /extract-labs` - Extract lab values from text
- `POST /differential` - Generate differential diagnoses
- `POST /debate-turn` - Handle debate round
- `POST /summary` - Generate final diagnosis
