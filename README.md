<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]



<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/weekijie/Sturgeon">
    <img src="frontend/public/sturgeon-logo.svg" alt="Logo" width="80" height="80">
  </a>

<h3 align="center">Sturgeon</h3>

  <p align="center">
    Clinical Debate AI for Differential Diagnosis
    <br />
    <em>Like House MD's diagnostic team, but AI-powered</em>
    <br />
    <br />
    <a href="https://github.com/weekijie/Sturgeon/blob/main/STURGEON_PROJECT_PLAN.md"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="#usage">View Demo</a>
    &middot;
    <a href="https://github.com/weekijie/Sturgeon/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    &middot;
    <a href="https://github.com/weekijie/Sturgeon/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#key-features">Key Features</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#configuration">Configuration</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#architecture">Architecture</a></li>
    <li><a href="#api-reference">API Reference</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#research--references">Research & References</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

**Sturgeon** is a Clinical Debate AI that brings House MD-style differential diagnosis to solo practitioners and resource-constrained settings. When you don't have a diagnostic team to challenge your thinking, Sturgeon acts as your AI colleague—generating differentials, defending its reasoning, and adapting when you challenge its conclusions.

### The Problem

Medical diagnosis is hard, especially when working alone:
- **Cognitive bias** - Confirmation bias leads to missed diagnoses
- **No second opinion** - Solo practitioners lack diagnostic teams
- **Information overload** - Too many possible conditions, too little time
- **Diagnostic errors** - Leading cause of medical mistakes and patient harm

### The Solution

Sturgeon simulates a **diagnostic case conference** using AI:

1. **Upload evidence** - Medical images, lab reports, patient history
2. **Get differential** - AI generates ranked diagnoses with reasoning
3. **Challenge the AI** - Question its conclusions, suggest alternatives
4. **Refine together** - AI updates its differential based on your input
5. **Reach consensus** - Final diagnosis with full reasoning chain

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/medgemma-impact-challenge) - targeting the Main Track + Agentic Workflow Prize.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Key Features

- **🧠 Agentic Dual-Model Architecture** - Gemini orchestrator + MedGemma specialist
- **📊 Multi-Modal Analysis** - Process medical images + lab reports simultaneously  
- **🔍 RAG-Enhanced Reasoning** - Clinical guidelines with automatic citation extraction
- **🚀 Production Queue Hardening** - Modal input concurrency + Vercel timeout alignment
- **🛡️ Hallucination Prevention** - Auto-validation with retry on detected fabrications
- **⚡ Smart Rate Limiting** - Per-endpoint quota management with visual feedback
- **💾 Session Persistence** - Cases saved locally, resume anytime
- **🎙️ Voice-to-Text Input** - Dictate patient history and debate prompts (browser-native)
- **📝 Streaming Chat UX** - Progressive response rendering + lightweight request stage indicator
- **📱 Mobile Responsive** - Full functionality on any device
- **🎯 MedSigLIP Triage** - Fast image classification before deep analysis

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Built With

* [![Next][Next.js]][Next-url]
* [![React][React.js]][React-url]
* [![TypeScript][TypeScript]][TypeScript-url]
* [![Python][Python]][Python-url]
* [![FastAPI][FastAPI]][FastAPI-url]
* [![PyTorch][PyTorch]][PyTorch-url]
* [![Tailwind][Tailwind]][Tailwind-url]
* [![HeroUI][HeroUI]][HeroUI-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

For production deployment (Modal + Vercel), see `DEPLOYMENT.md`.

### Prerequisites

- **Node.js** 18+ 
- **Python** 3.10+
- **GPU** with 8GB+ VRAM (NVIDIA CUDA or AMD ROCm)
- **MedGemma Access** - [Request on HuggingFace](https://huggingface.co/google/medgemma-1.5-4b-it)
- **Gemini API Key** (optional) - [Get free key](https://aistudio.google.com/apikey)

### Installation

#### 1. Clone the repository

```bash
git clone https://github.com/weekijie/Sturgeon.git
cd Sturgeon
```

#### 2. Set up Python backend

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
# source .venv/bin/activate

# Install dependencies
pip install -r ai-service/requirements.txt
```

#### 3. Set up frontend

```bash
cd frontend
npm install
cd ..
```

### Configuration

#### 1. Environment Variables

```bash
# Copy example environment file
cp ai-service/.env.example ai-service/.env

# Edit ai-service/.env with your keys:
# GEMINI_API_KEY=your_api_key_here
# ALLOWED_ORIGINS=http://localhost:3000
```

#### 2. AMD GPU Setup (if applicable)

```bash
# Windows PowerShell
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"

# Linux/Mac
export TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1
```

#### 3. Start the services

**Terminal 1 - Backend:**
```bash
.venv\Scripts\activate
python -m uvicorn ai-service.main:app --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**Open** http://localhost:3000

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

### Example Workflow

1. **Upload Evidence**
   - Drag & drop medical images (X-rays, CT scans, dermatology photos)
   - Upload lab reports (PDF or TXT)
   - Enter or dictate patient history

2. **Review Analysis**
   - AI analyzes images using MedSigLIP + MedGemma
   - Lab values extracted and structured
   - Initial differential generated with probabilities

3. **Challenge the Diagnosis**
    - Ask "What if this is autoimmune instead?"
    - Request "What test would differentiate these?"
    - Question the reasoning
    - Type or dictate your challenges (voice input supported on Chromium browsers)

4. **Iterate**
   - AI updates differential based on your challenges
   - Probabilities adjust with new information
   - Clinical guidelines cited when relevant

5. **Final Summary**
    - Consensus diagnosis with confidence level
    - Full reasoning chain documented
    - Next steps and ruled-out conditions

### Cold Start Note

> **First load can take 2-3 minutes.** The AI runs on serverless GPU infrastructure to keep costs low. In production, CPU memory snapshots are enabled by default and reduce repeated initialization overhead, but the first cold request can still take a couple of minutes while model services become ready.
>
> Warmup uses bounded polling and may pause to save credits. Once you see "AI ready!", subsequent requests in the same warm window are significantly faster.

### API Example

```bash
# Generate differential
curl -X POST http://localhost:8000/differential \
  -H "Content-Type: application/json" \
  -d '{
    "patient_history": "45yo female, dry cough 3 weeks, chest tightness",
    "lab_values": {"WBC": "11.2", "CRP": "15"}
  }'

# Response includes rate limit headers:
# X-RateLimit-Limit: 10
# X-RateLimit-Remaining: 9
# X-RateLimit-Window: 60
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ARCHITECTURE -->
## Architecture

Sturgeon uses an **agentic dual-model architecture** that maps directly to the Agentic Workflow Prize criteria:

```
┌─────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Upload Page  │  │ Debate Page  │  │  Summary Page    │  │
│  │  (Next.js)   │  │  (Next.js)   │  │   (Next.js)      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              AGENTIC ORCHESTRATION                       ││
│  │  ┌──────────────┐      ┌──────────────────────────┐    ││
│  │  │   Gemini 3   │─────▶│  MedGemma 4B-it         │    ││
│  │  │  Flash       │◀─────│  (HAI-DEF Specialist)    │    ││
│  │  │              │      │                          │    ││
│  │  │ • Manages    │      │ • Clinical reasoning     │    ││
│  │  │   conversation    │      │ • Differential diagnosis │    ││
│  │  │ • Summarizes│      │ • Medical image analysis │    ││
│  │  │   debate state    │      │ • Evidence evaluation    │    ││
│  │  │ • Routes to │      │                          │    ││
│  │  │   MedGemma  │      │                          │    ││
│  │  └──────────────┘      └──────────────────────────┘    ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Supporting Services:                                        │
│  • MedSigLIP (image triage)                                 │
│  • RAG Retriever (clinical guidelines)                      │
│  • Hallucination Checker (validation)                       │
│  • Rate Limiter (API protection)                            │
└─────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

- **MedGemma** wasn't trained for multi-turn conversation, but excels at medical reasoning
- **Gemini** handles what MedGemma can't: context management, debate flow, synthesis
- **Result**: Best of both worlds - medical accuracy + conversational fluency

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- API REFERENCE -->
## API Reference

| Endpoint | Method | Rate Limit | Description |
|----------|--------|------------|-------------|
| `/health` | GET | - | Service status + model availability |
| `/analyze-image` | POST | 5/min | Medical image analysis (MedSigLIP + MedGemma) |
| `/extract-labs` | POST | 15/min | Extract structured lab values from text |
| `/extract-labs-file` | POST | 5/min | Extract labs from PDF/TXT files |
| `/differential` | POST | 10/min | Generate initial differential diagnoses |
| `/debate-turn` | POST | 20/min | Handle debate round (orchestrated) |
| `/summary` | POST | 10/min | Generate final diagnosis summary |
| `/rag-status` | GET | - | RAG retriever status & statistics |
| `/vllm-metrics` | GET | - | vLLM queue/throughput debug metrics |

All endpoints return rate limit headers:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Window`: Window size in seconds
- `Retry-After`: Seconds until retry (when rate limited)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

### ✅ Completed

- [x] Agentic dual-model architecture (Gemini + MedGemma)
- [x] Multi-modal upload (images + lab reports)
- [x] RAG integration with clinical guidelines (14 documents)
- [x] Comprehensive citation detection (15+ medical organizations)
- [x] Hallucination prevention with auto-retry
- [x] Rate limiting with visual UI feedback
- [x] Session persistence via localStorage
- [x] Mobile responsive design
- [x] 156 backend unit tests passing
- [x] Modal + Vercel production deployment (queue/timeout hardening)

### 🚧 In Progress

- [ ] Demo video recording
- [ ] Submission documentation
- [ ] Final logchecklist pass with retry-churn patch (`NEXT_PATCH_PLAN.md`)

See [CHANGELOG.md](CHANGELOG.md) for detailed development history.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- RESEARCH -->
## Research & References

This project incorporates techniques from cutting-edge medical AI research:

### Hallucination Prevention
- **CHECK Framework** - Garcia-Fernandez et al. "Trustworthy AI for Medicine: Continuous Hallucination Detection and Elimination with CHECK." *arXiv:2506.11129* (2025)
- **HALO Framework** - Anjum et al. "HALO: Hallucination Analysis and Learning Optimization to Empower LLMs with Retrieval-Augmented Context for Guided Clinical Decision Making." *arXiv:2409.10011* (2024)

### RAG & Citations
- **Guide-RAG** - DiGiacomo et al. "Guide-RAG: Evidence-Driven Corpus Curation for Retrieval-Augmented Generation in Long COVID." *arXiv:2510.15782* (2025)
  - Implemented: GS-4 configuration (guidelines + systematic reviews)
  - Parameters: TOP_K=12, CHUNK_OVERLAP=500
  - Evaluation: LLM-as-Judge framework (faithfulness, relevance, comprehensiveness)
- **Mayo Reverse RAG** - Plumb, Taryn. "Mayo Clinic's secret weapon against AI hallucinations: Reverse RAG in action." *VentureBeat* (2025)

### Medical AI
- **MedGemma** - Google's medical foundation model (HAI-DEF)
- **MedSigLIP** - Biomedical vision-language model for image understanding

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Distributed under the CC BY 4.0 License. See [LICENSE](LICENSE) for more information.

This project uses the CC BY 4.0 license to comply with MedGemma Impact Challenge winner obligations, ensuring open access to medical AI research.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [Google](https://ai.google/) - MedGemma model and Gemini API
* [HeroUI](https://heroui.com/) - Modern React component library
* [FastAPI](https://fastapi.tiangolo.com/) - High-performance Python web framework
* [HuggingFace](https://huggingface.co/) - Model hosting and Transformers library
* [Vercel](https://vercel.com/) - Frontend deployment platform

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/weekijie/Sturgeon.svg?style=for-the-badge
[contributors-url]: https://github.com/weekijie/Sturgeon/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/weekijie/Sturgeon.svg?style=for-the-badge
[forks-url]: https://github.com/weekijie/Sturgeon/network/members
[stars-shield]: https://img.shields.io/github/stars/weekijie/Sturgeon.svg?style=for-the-badge
[stars-url]: https://github.com/weekijie/Sturgeon/stargazers
[issues-shield]: https://img.shields.io/github/issues/weekijie/Sturgeon.svg?style=for-the-badge
[issues-url]: https://github.com/weekijie/Sturgeon/issues
[license-shield]: https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg?style=for-the-badge
[license-url]: https://github.com/weekijie/Sturgeon/blob/main/LICENSE
[product-screenshot]: frontend/public/test-data/test1.png

[Next.js]: https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white
[Next-url]: https://nextjs.org/
[React.js]: https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB
[React-url]: https://reactjs.org/
[TypeScript]: https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white
[TypeScript-url]: https://www.typescriptlang.org/
[Python]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[FastAPI]: https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi
[FastAPI-url]: https://fastapi.tiangolo.com/
[PyTorch]: https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white
[PyTorch-url]: https://pytorch.org/
[Tailwind]: https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white
[Tailwind-url]: https://tailwindcss.com/
[HeroUI]: https://img.shields.io/badge/HeroUI-000000?style=for-the-badge&logo=react&logoColor=white
[HeroUI-url]: https://heroui.com/
