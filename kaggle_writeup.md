### Project name
Sturgeon: Diagnostic Debate AI

### Your team
Ki Jie (solo)

- Role: Product, ML engineering, backend, frontend, deployment
- Specialty: Agentic medical AI workflows, full-stack implementation, production hardening

### Problem statement
Diagnostic error remains a major healthcare problem, especially in settings where clinicians cannot easily access specialist teams. Many AI workflows still operate as one-shot generators, which can reinforce anchoring bias instead of reducing it. Clinicians need iterative reasoning support, not static outputs.

Sturgeon addresses this by simulating a diagnostic case conference: users upload evidence, receive an initial differential, challenge the system's reasoning, and refine conclusions over multiple rounds. This debate-first design is intended to reduce premature closure, improve explainability, and support safer decisions in resource-constrained settings.

### Overall solution:
Sturgeon is an agentic clinical reasoning system that uses HAI-DEF models as callable tools in a multi-step workflow.

Core model roles:

- MedGemma 1.5 4B-it (HAI-DEF): primary medical specialist for lab extraction, differential generation, debate reasoning, and final summary
- Gemini Flash: orchestration layer for multi-turn state management, routing, and synthesis
- MedSigLIP: image triage layer before deep MedGemma image interpretation

Workflow:

1. User provides multimodal evidence (history, labs, image)
2. System generates initial differentials with evidence
3. User challenges assumptions in debate turns
4. System updates probabilities/rationale with retrieved clinical guidance when relevant
5. System returns final diagnosis summary and recommended next steps

Why this is strong for HAI-DEF evaluation:

- MedGemma is used repeatedly as a specialist tool across multiple stages, not as a single endpoint
- The architecture demonstrates practical agentic composition (orchestrator + specialist + retrieval + safeguards)
- The workflow mirrors real diagnostic reasoning (hypothesis -> challenge -> revision)

### Technical details
Architecture:

- Frontend: Next.js + HeroUI (upload, debate, summary flows)
- Backend tracks:
  - Local development backend: `ai-service/` (FastAPI + direct model invocation)
  - Cloud deployment backend: `modal_backend/` (FastAPI + vLLM + Modal runtime)
- Production runtime: Modal backend + Vercel frontend
- APIs: `/analyze-image`, `/extract-labs-file`, `/differential`, `/debate-turn`, `/summary`, `/rag-status`
- RAG stack: ChromaDB + `sentence-transformers/all-MiniLM-L6-v2` embeddings

Local vs cloud implementation differences:

- Local (`ai-service/`): direct in-process MedGemma calls, simpler runtime and logging, optimized for iteration/debugging.
- Cloud (`modal_backend/`): vLLM OpenAI-compatible serving, separate MedSigLIP service, Modal snapshots/volumes/concurrency controls, structured logging with request IDs, and richer health telemetry.
- Cloud-only operational hardening includes query clamp + retrieval compaction, deterministic PDF lab fast-path before LLM fallback, adaptive token overflow retries, queue observability (`/vllm-metrics`), and runtime counters in `/health`.

RAG and evidence handling:

- Curated clinical corpus (guidelines + systematic reviews)
- Retriever defaults: `TOP_K_DEFAULT=12`, `CHUNK_OVERLAP=500`
- Production debate retrieval: `top_k=8` + relevance filtering + diversity compaction
- Citation normalization ensures only valid guideline links are surfaced

Reliability and safety:

- Hallucination checks with retry on suspect outputs
- Deterministic PDF lab parsing fast-path before LLM fallback
- Adaptive token/timeout handling for long prompts and queue pressure
- Partial-success UX: if one modality fails, successful evidence path is preserved
- Rate limiting and standardized API headers for operational safety

Feasibility and execution quality:

- End-to-end product runs with real demo cases across dermatology, radiology, and critical care contexts
- Production hardening completed (queue/timeout behavior, cold-start strategy, observability endpoints)
- Backend test suite passes (156 tests), supporting reproducibility and maintainability
- Deployment is practical for judges (public web demo + documented local/production setup)
