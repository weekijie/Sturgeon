# Sturgeon Modal Backend

Serverless deployment of the Sturgeon AI diagnostic service on Modal with vLLM.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Modal Container (L4 GPU)                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ vLLM Server  │  │ MedSigLIP    │  │ FastAPI App      │  │
│  │ :6501        │  │ Server :6502 │  │ (web_endpoints)  │  │
│  │ MedGemma 4B  │  │ Image triage │  │ /extract-labs    │  │
│  │              │  │              │  │ /differential    │  │
│  │              │  │              │  │ /debate-turn     │  │
│  │              │  │              │  │ /analyze-image   │  │
│  │              │  │              │  │ /summary         │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  Volumes:                                                   │
│  - medgemma-cache/ (HuggingFace model cache)               │
│  - vllm-cache/ (vLLM runtime/cache artifacts)              │
│  - chroma-db/ (RAG vector index + query cache)             │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Modal CLI

```bash
pip install modal
modal setup  # Authenticate
```

### 2. Create Secrets

```bash
modal secret create gemini-api-key GEMINI_API_KEY=your_key_here
```

### 3. Deploy

```bash
cd modal_backend
modal deploy app.py
```

### 4. Test Locally

```bash
modal serve app.py  # Hot reload for development
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Main Modal app with all endpoints |
| `medgemma_client.py` | HTTP client for vLLM OpenAI API |
| `medsiglip_server.py` | Standalone MedSigLIP triage server |
| `gemini_orchestrator_modal.py` | Gemini orchestrator adapted for vLLM |
| `prompts.py` | Prompt templates |
| `models.py` | Pydantic request/response models |
| `json_utils.py` | JSON extraction utilities |
| `formatters.py` | Lab/differential/round formatters |
| `hallucination_check.py` | Hallucination detection |
| `rag_retriever.py` | Vector retrieval for guidelines |
| `guidelines/` | Medical guideline documents |

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/vllm-metrics` | vLLM queue/throughput debug metrics |
| POST | `/extract-labs` | Extract lab values from text |
| POST | `/differential` | Generate differential diagnoses |
| POST | `/debate-turn` | Handle debate turn |
| POST | `/analyze-image` | Analyze medical image |
| POST | `/summary` | Generate final diagnosis |

## Cost Estimates

| GPU | Cost/hr | Use Case |
|-----|---------|----------|
| L4 | ~$0.20 | 4B model inference (recommended) |
| A10G | ~$0.60 | More concurrent requests |
| A100 | ~$3.00 | Overkill for 4B model |

**Free tier**: $30/month free credits = ~150 hours L4 time

## Environment Variables

Set via Modal secrets/environment:

- `GEMINI_API_KEY` - Required for orchestrator
- `GEMINI_MODEL` - Optional (default: gemini-2.0-flash)
- `DISABLE_MEDSIGLIP` - Set to disable image triage
- `ENABLE_MEMORY_SNAPSHOT` - Optional (default: `1`)
- `ENABLE_GPU_SNAPSHOT` - Optional (default: `0`, experimental)
- `RAG_CACHE_TTL_SECONDS` - Optional (default: `900`)
- `RAG_CACHE_MAX_ENTRIES` - Optional (default: `256`)
- `MODAL_MAX_CONTAINERS` - Optional (default: `1`)
- `MODAL_MAX_INPUTS` - Optional (default: `8`)
- `MODAL_TARGET_INPUTS` - Optional (default: `4`)

## Snapshot Modes

- CPU snapshot default: `ENABLE_MEMORY_SNAPSHOT=1`, `ENABLE_GPU_SNAPSHOT=0`
- GPU snapshot opt-in (alpha): `ENABLE_GPU_SNAPSHOT=1`
- Both modes keep RAG index cache on the persistent `chroma-db` volume.

## Vercel Frontend Integration

After deployment, set in Vercel:

```env
NEXT_PUBLIC_API_URL=https://your-workspace--sturgeon-medgemma-sturgeonservice.modal.run
```
