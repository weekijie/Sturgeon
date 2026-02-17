# Sturgeon Deployment Plan

> **Architecture:** Vercel (Frontend) + RunPod Serverless (Backend)  
> **Strategy:** Pre-built RAG index in Docker image  
> **Deadline:** February 24, 2026 (MedGemma Impact Challenge)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Backend Deployment (RunPod Serverless)](#backend-deployment-runpod-serverless)
4. [Frontend Deployment (Vercel)](#frontend-deployment-vercel)
5. [Integration & Testing](#integration--testing)
6. [Cost Estimates](#cost-estimates)
7. [Troubleshooting](#troubleshooting)
8. [Pre-Submission Checklist](#pre-submission-checklist)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER                                    │
│                         ↓                                       │
│              https://sturgeon.vercel.app                        │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VERCEL (Frontend)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│  │ Upload Page  │  │ Debate Page  │  │  Summary Page    │      │
│  │  (Next.js)   │  │  (Next.js)   │  │   (Next.js)      │      │
│  └──────────────┘  └──────────────┘  └──────────────────┘      │
│                          ↓                                      │
│              Calls RunPod API endpoints                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP POST/GET
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RUNPOD SERVERLESS (Backend)                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              DOCKER CONTAINER                           │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  FastAPI App                                    │   │   │
│  │  │  ├── MedGemma 4B Model (loaded on startup)     │   │   │
│  │  │  ├── MedSigLIP (image analysis)                │   │   │
│  │  │  ├── Pre-built ChromaDB Index (RAG)            │   │   │
│  │  │  ├── API Routes:                               │   │   │
│  │  │  │   ├── /health                               │   │   │
│  │  │  │   ├── /analyze-image                        │   │   │
│  │  │  │   ├── /extract-labs                         │   │   │
│  │  │  │   ├── /differential                         │   │   │
│  │  │  │   ├── /debate-turn                          │   │   │
│  │  │  │   └── /summary                              │   │   │
│  │  │  └── CORS enabled for Vercel domain           │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          ↓                                      │
│              Auto-scales to zero when idle                      │
│              Wakes up on first request (~10 sec)                │
└─────────────────────────────────────────────────────────────────┘
```

**Cold Start Flow:**
1. First request arrives → GPU spins up (~5-8 seconds)
2. Container loads → Model loads from cache (~3-5 seconds)
3. ChromaDB index loads from disk (~1-2 seconds)
4. Request processes (~15-20 seconds)
5. Container stays warm for 60 seconds after last request
6. Scales to zero → No cost until next request

---

## Prerequisites

### Accounts Needed

1. **Hugging Face** (https://huggingface.co/)
   - Access to MedGemma-1.5-4b-it model
   - Create access token: Settings → Access Tokens → New Token

2. **RunPod** (https://www.runpod.io/)
   - Add payment method (credit card or PayPal)
   - Verify email

3. **Vercel** (https://vercel.com/)
   - Connect GitHub account
   - Import repository

4. **Docker Hub** (https://hub.docker.com/) (optional)
   - For storing Docker images
   - Can also use RunPod's registry

### Local Development Requirements

```bash
# Docker Desktop installed
# Python 3.10+
# Node.js 18+
# Git configured
```

### API Keys to Collect

| Service | Token/Key Name | Where to Get |
|---------|----------------|--------------|
| HuggingFace | `HF_TOKEN` | Settings → Access Tokens |
| Gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| RunPod | `RUNPOD_API_KEY` | RunPod Settings → API Keys |

---

## Backend Deployment (RunPod Serverless)

### Step 1: Prepare Pre-Built RAG Index

**Goal:** Create `.chroma_cache/` directory with embedded guidelines

```bash
# Navigate to ai-service directory
cd ai-service

# Create a script to build the index
python scripts/build_rag_index.py
```

**Create `scripts/build_rag_index.py`:**
```python
"""Build RAG index locally before Docker build."""
import sys
sys.path.append('.')
from rag_retriever import get_retriever
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_index():
    logger.info("Building RAG index...")
    retriever = get_retriever(
        guidelines_dir="./guidelines",
        cache_dir="./.chroma_cache"
    )
    
    success = retriever.initialize(force_reindex=True)
    if success:
        logger.info(f"✓ Index built successfully!")
        logger.info(f"  Files: {retriever.indexing_stats['num_files']}")
        logger.info(f"  Chunks: {retriever.indexing_stats['num_chunks']}")
    else:
        logger.error("✗ Failed to build index")
        sys.exit(1)

if __name__ == "__main__":
    build_index()
```

**Run the script:**
```bash
# Make sure virtual environment is activated
.venv\Scripts\activate

# Install dependencies if needed
pip install chromadb sentence-transformers

# Build the index
python scripts/build_rag_index.py

# Verify the cache directory was created
ls -la .chroma_cache/
```

**Expected output:**
```
.chroma_cache/
├── chroma.sqlite3
└── ... (other ChromaDB files)
```

---

### Step 2: Create Dockerfile

**Create `ai-service/Dockerfile`:**

```dockerfile
# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the pre-built RAG index
COPY .chroma_cache/ /app/.chroma_cache/

# Copy guidelines (for reference/metadata)
COPY guidelines/ /app/guidelines/

# Copy application code
COPY *.py /app/

# Copy tests (optional)
COPY tests/ /app/tests/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_CACHE=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

# Create cache directory for models
RUN mkdir -p /app/.cache/huggingface

# Pre-download MedGemma model during build (optional but speeds up cold start)
# This adds ~8GB to image size but eliminates model download at runtime
ARG HF_TOKEN
RUN python -c "
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch
print('Pre-downloading MedGemma model...')
AutoProcessor.from_pretrained('google/medgemma-1.5-4b-it')
AutoModelForImageTextToText.from_pretrained(
    'google/medgemma-1.5-4b-it',
    torch_dtype=torch.float16,
    device_map='auto'
)
print('Model downloaded successfully!')
" || echo "Model download skipped - will download at runtime"

# Expose the port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Update `requirements.txt` (ensure all deps included):**
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-multipart==0.0.17
pydantic==2.9.2
torch>=2.0.0
transformers>=4.45.0
pillow==10.4.0
accelerate>=0.26.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
PyYAML==6.0.2
pdfplumber==0.11.4
google-genai==0.3.0
httpx==0.27.2
python-dotenv==1.0.1
```

---

### Step 3: Build and Push Docker Image

**Option A: Docker Hub (Recommended)**

```bash
# Login to Docker Hub
docker login

# Build the image (with HF token for model pre-download)
docker build \
  --platform linux/amd64 \
  --build-arg HF_TOKEN=your_hf_token_here \
  -t yourusername/sturgeon-backend:latest \
  .

# Push to Docker Hub
docker push yourusername/sturgeon-backend:latest
```

**Option B: GitHub Container Registry**

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Build and tag
docker build \
  --platform linux/amd64 \
  -t ghcr.io/yourusername/sturgeon-backend:latest \
  .

# Push
docker push ghcr.io/yourusername/sturgeon-backend:latest
```

**Option C: RunPod Direct Upload**
- Skip this step
- Upload Dockerfile directly in RunPod console

---

### Step 4: Update Backend Code for CORS

**Update `ai-service/main.py`:**

```python
from fastapi.middleware.cors import CORSMiddleware

# Add after app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://your-app.vercel.app",  # Production (update after Vercel deploy)
        "https://*.vercel.app",  # All Vercel preview deployments
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```

**Add health check endpoint (if not exists):**
```python
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "medgemma_loaded": medgemma_model is not None,
        "rag_available": rag_retriever is not None if 'rag_retriever' in globals() else False
    }
```

---

### Step 5: Deploy to RunPod Serverless

**1. Log into RunPod Console**
- Go to https://www.runpod.io/console
- Navigate to "Serverless" → "My Endpoints"

**2. Create New Endpoint**
- Click "New Endpoint"
- **Endpoint Name:** `sturgeon-backend`
- **GPU Type:** NVIDIA T4 (cheapest, sufficient)
- **GPU Count:** 1
- **Worker Type:** Flex (scales to zero)
- **Max Workers:** 1 (start with 1, increase if needed)
- **Idle Timeout:** 60 seconds

**3. Configure Container**
- **Image:** `yourusername/sturgeon-backend:latest`
- **Container Port:** 8000
- **Command:** Leave empty (uses Dockerfile CMD)
- **Environment Variables:**
  ```
  HF_TOKEN=your_huggingface_token
  GEMINI_API_KEY=your_gemini_key
  ALLOWED_ORIGINS=https://your-app.vercel.app
  ```

**4. Advanced Settings**
- **Container Disk:** 20 GB (enough for model + cache)
- **Volume:** None (we baked everything into image)
- **API Key:** Generate and save this!

**5. Deploy**
- Click "Create Endpoint"
- Wait for deployment (2-5 minutes)

**6. Get Endpoint URL**
- Once deployed, copy the endpoint URL
- Format: `https://api.runpod.ai/v2/your-endpoint-id/run`
- Also get direct URL: `https://your-endpoint-id-123.runpod.io`

---

### Step 6: Test Backend

```bash
# Test health endpoint
curl https://your-endpoint-id-123.runpod.io/health

# Expected response (might take 10-15 sec for cold start):
{"status": "healthy", "medgemma_loaded": true, "rag_available": true}

# Test differential endpoint
curl -X POST https://your-endpoint-id-123.runpod.io/differential \
  -H "Content-Type: application/json" \
  -d '{
    "patient_history": "45yo female, dry cough 3 weeks",
    "lab_values": {"WBC": "11.2"}
  }'
```

---

## Frontend Deployment (Vercel)

### Step 1: Prepare Frontend Environment

**Create `frontend/.env.local`:**
```bash
# Local development
NEXT_PUBLIC_API_URL=http://localhost:8000

# Production (update after RunPod deploy)
# NEXT_PUBLIC_API_URL=https://your-endpoint-id-123.runpod.io
```

**Create `frontend/.env.production`:**
```bash
# Will be set in Vercel dashboard
NEXT_PUBLIC_API_URL=https://your-endpoint-id-123.runpod.io
```

**Update API client to handle cold start:**

Create `frontend/lib/api.ts`:
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: any;
  timeout?: number;
}

export async function apiRequest(
  endpoint: string, 
  options: RequestOptions = {}
) {
  const { method = 'GET', body, timeout = 120000 } = options;
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(`${API_URL}${endpoint}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}
```

---

### Step 2: Add Cold Start UI

**Create `frontend/components/ColdStartLoader.tsx`:**
```typescript
'use client';

import { useState, useEffect } from 'react';

interface ColdStartLoaderProps {
  isLoading: boolean;
  loadingTime: number;
}

export default function ColdStartLoader({ isLoading, loadingTime }: ColdStartLoaderProps) {
  const [dots, setDots] = useState('');
  
  useEffect(() => {
    if (!isLoading) return;
    
    const interval = setInterval(() => {
      setDots(prev => prev.length >= 3 ? '' : prev + '.');
    }, 500);
    
    return () => clearInterval(interval);
  }, [isLoading]);
  
  if (!isLoading) return null;
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-md text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <h3 className="text-lg font-semibold mb-2">
          Warming up AI models{dots}
        </h3>
        <p className="text-gray-600 text-sm mb-4">
          This happens when the demo hasn't been used recently.
          GPU is spinning up (5-15 seconds).
        </p>
        {loadingTime > 5 && (
          <p className="text-xs text-gray-500">
            Still loading... {loadingTime}s elapsed
          </p>
        )}
      </div>
    </div>
  );
}
```

**Update upload/debate pages to use it:**
```typescript
import ColdStartLoader from '@/components/ColdStartLoader';

export default function UploadPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [loadingTime, setLoadingTime] = useState(0);
  
  const handleSubmit = async () => {
    setIsLoading(true);
    setLoadingTime(0);
    
    const timer = setInterval(() => {
      setLoadingTime(t => t + 1);
    }, 1000);
    
    try {
      const result = await apiRequest('/differential', {
        method: 'POST',
        body: formData,
        timeout: 180000, // 3 minutes for cold start + inference
      });
      // Handle result
    } finally {
      clearInterval(timer);
      setIsLoading(false);
    }
  };
  
  return (
    <>
      <ColdStartLoader isLoading={isLoading} loadingTime={loadingTime} />
      {/* Rest of your UI */}
    </>
  );
}
```

---

### Step 3: Deploy to Vercel

**Option A: Vercel CLI (Recommended)**

```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Navigate to frontend
cd frontend

# Deploy
vercel --prod

# Follow prompts:
# - Link to existing project? (No)
# - What's your project name? sturgeon
# - Which directory? ./
```

**Option B: Git Integration**

1. Push code to GitHub
2. Go to https://vercel.com/new
3. Import your GitHub repository
4. Configure:
   - **Framework:** Next.js
   - **Root Directory:** frontend
   - **Build Command:** next build
   - **Environment Variables:**
     - `NEXT_PUBLIC_API_URL=https://your-runpod-endpoint.runpod.io`
5. Click Deploy

**Option C: Vercel Dashboard**

1. Go to https://vercel.com/dashboard
2. Click "Add New" → Project
3. Select repository
4. Configure as above
5. Deploy

---

### Step 4: Configure Environment Variables in Vercel

**In Vercel Dashboard:**
1. Go to Project Settings → Environment Variables
2. Add:
   ```
   NEXT_PUBLIC_API_URL=https://your-endpoint-id-123.runpod.io
   ```
3. Redeploy if needed

---

## Integration & Testing

### Step 1: End-to-End Test

```bash
# 1. Visit Vercel URL
open https://sturgeon-yourusername.vercel.app

# 2. Test upload
# - Upload a test image
# - Enter patient history
# - Click "Generate Differential"

# 3. Observe cold start
# - Should see "Warming up AI models" spinner
# - Wait 10-15 seconds
# - Result should appear

# 4. Test again (warm GPU)
# - Should be much faster (2-5 seconds)
```

### Step 2: Verify RAG is Working

In debate page, ask a question that requires guidelines:
- "What does ACR say about chest X-ray interpretation?"
- Check response includes guideline citations

### Step 3: Monitor Logs

**RunPod Console:**
- Go to your endpoint
- Click "Logs" tab
- Watch for:
  - Model loading messages
  - RAG index loading
  - Request processing times

**Vercel Dashboard:**
- Go to project → Functions tab
- Check for API errors
- Monitor response times

---

## Cost Estimates

### RunPod Serverless (Pay-Per-Use)

**Pricing:**
- T4 GPU: ~$0.00011 per second
- Billed only when processing

**Scenario 1: Minimal Usage (Judging Only)**
```
20 requests × 20 seconds × $0.00011/sec = $0.04
Cold starts: 5 × 10 seconds × $0.00011/sec = $0.006
Total: ~$0.05
```

**Scenario 2: Moderate Traffic**
```
100 requests × 20 seconds × $0.00011/sec = $0.22
Cold starts: 10 × 10 seconds × $0.00011/sec = $0.011
Total: ~$0.23
```

**Scenario 3: High Traffic (LinkedIn viral)**
```
500 requests × 20 seconds × $0.00011/sec = $1.10
Cold starts: 20 × 10 seconds × $0.00011/sec = $0.022
Total: ~$1.12
```

**Worst Case:** ~$5-10 if extremely popular

### Vercel Frontend

**Pricing:**
- **Free tier:** 100GB bandwidth, 6000 build minutes
- Your usage: ~1-5GB bandwidth
- **Cost: FREE**

### Docker Hub

**Pricing:**
- Free tier: Unlimited public repos
- Image storage: ~8GB
- **Cost: FREE**

### Total Estimated Cost

| Scenario | RunPod | Vercel | Docker Hub | **Total** |
|----------|--------|--------|------------|-----------|
| Minimal | $0.05 | Free | Free | **$0.05** |
| Moderate | $0.23 | Free | Free | **$0.23** |
| High | $1.12 | Free | Free | **$1.12** |
| Worst case | $10.00 | Free | Free | **$10.00** |

---

## Troubleshooting

### Issue: Cold Start Taking Too Long (>30 seconds)

**Solutions:**
1. Pre-download model in Dockerfile (increases image size but speeds up cold start)
2. Reduce max_new_tokens in generation
3. Use quantized model (4-bit)

### Issue: RAG Not Working

**Check:**
1. Verify `.chroma_cache/` was copied in Dockerfile
2. Check logs for "Loading existing vector index"
3. Ensure guidelines files are in correct directory

### Issue: CORS Errors

**Solutions:**
1. Update `allow_origins` in FastAPI with exact Vercel URL
2. Check that `ALLOWED_ORIGINS` env var is set correctly
3. Include `http://localhost:3000` for local testing

### Issue: Model Fails to Load

**Solutions:**
1. Check HF_TOKEN is valid and has MedGemma access
2. Verify model name is correct: `google/medgemma-1.5-4b-it`
3. Check GPU has enough VRAM (T4 has 16GB, sufficient)

### Issue: Out of Memory

**Solutions:**
1. Use 4-bit quantization
2. Reduce batch size
3. Use smaller GPU (but T4 is already minimum)

### Issue: Request Timeouts

**Solutions:**
1. Increase timeout in frontend (up to 180 seconds)
2. Reduce max_new_tokens
3. Enable response streaming

---

## Pre-Submission Checklist

### Backend Verification

- [ ] Docker image builds successfully
- [ ] RAG index pre-built and included in image
- [ ] CORS configured for Vercel domain
- [ ] All API endpoints working:
  - [ ] GET /health
  - [ ] POST /analyze-image
  - [ ] POST /extract-labs
  - [ ] POST /differential
  - [ ] POST /debate-turn
  - [ ] POST /summary
- [ ] Cold start <20 seconds
- [ ] Warm requests <5 seconds
- [ ] Environment variables set in RunPod

### Frontend Verification

- [ ] Vercel deployment successful
- [ ] NEXT_PUBLIC_API_URL points to RunPod
- [ ] Cold start loader displays correctly
- [ ] All pages working:
  - [ ] Upload page
  - [ ] Debate page
  - [ ] Summary page
- [ ] Mobile responsive
- [ ] Error handling works

### Integration Testing

- [ ] E2E flow works:
  1. Upload evidence → 2. Debate → 3. Summary
- [ ] Cold start message appears
- [ ] RAG citations appear in responses
- [ ] Image analysis works
- [ ] Lab extraction works
- [ ] Session persistence works (localStorage)

### Documentation

- [ ] README.md updated with:
  - [ ] Live demo link
  - [ ] Setup instructions
  - [ ] Architecture diagram
  - [ ] API documentation
- [ ] DEPLOYMENT_OPTIONS.md updated
- [ ] Demo video recorded (≤3 min)

### Competition Submission

- [ ] GitHub repo is public
- [ ] All code committed and pushed
- [ ] LICENSE file present (CC BY 4.0)
- [ ] requirements.txt up to date
- [ ] package.json up to date
- [ ] Kaggle writeup submitted
- [ ] Video demo uploaded to Kaggle

---

## Quick Reference

### Important URLs

| Service | URL | Notes |
|---------|-----|-------|
| Vercel Project | https://vercel.com/yourusername/sturgeon | Frontend dashboard |
| Vercel Live Site | https://sturgeon-yourusername.vercel.app | Public URL |
| RunPod Console | https://www.runpod.io/console | Backend management |
| RunPod Endpoint | https://api.runpod.ai/v2/xxx/run | API base URL |
| HuggingFace | https://huggingface.co/settings/tokens | API keys |

### Useful Commands

```bash
# Build Docker image
docker build --platform linux/amd64 -t sturgeon-backend:latest .

# Push to Docker Hub
docker push yourusername/sturgeon-backend:latest

# Test API locally
curl http://localhost:8000/health

# Deploy frontend
vercel --prod

# View logs
vercel logs --production
```

### Environment Variables Summary

**Backend (RunPod):**
```
HF_TOKEN=hf_xxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaxxxxxxxxxxxxx
ALLOWED_ORIGINS=https://sturgeon-yourusername.vercel.app
```

**Frontend (Vercel):**
```
NEXT_PUBLIC_API_URL=https://your-endpoint-id-123.runpod.io
```

---

## Next Steps

1. **Build RAG index locally** (Step 1)
2. **Create Dockerfile** (Step 2)
3. **Test Docker build locally**
4. **Push to Docker Hub**
5. **Create RunPod endpoint**
6. **Test backend**
7. **Deploy frontend to Vercel**
8. **Test full integration**
9. **Submit to competition!**

**Need help?** Check troubleshooting section or ask!

---

*Document version: 1.0*  
*Created: February 16, 2026*  
*Target deadline: February 24, 2026*
