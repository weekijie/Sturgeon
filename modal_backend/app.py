"""
Sturgeon AI Service - Modal Deployment (ASGI App)

Architecture:
- vLLM server (port 6501): OpenAI-compatible API for MedGemma
- MedSigLIP server (port 6502): Image triage (separate process)
- FastAPI app: Single ASGI app with all endpoints

Features:
- Rate limiting per endpoint
- Structured JSON logging with request IDs
- Input sanitization
- CORS restricted to production domain

All running in a single Modal container with shared GPU.
"""
import modal

MODEL_CACHE_DIR = "/root/.cache/huggingface"
CHROMA_DB_DIR = "/root/chroma_db"

base_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .uv_pip_install(
        "vllm>=0.11.0",
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "python-multipart>=0.0.12",
        "google-genai>=1.0.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "Pillow>=10.0.0",
        "pdfplumber>=0.11.0",
        "httpx",
        "pyyaml>=6.0.0",
        "chromadb>=0.4.0",
        "sentence-transformers>=2.2.0",
        "transformers>=4.50.0",
        "torch>=2.5.0",
        "hf_transfer",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "TRANSFORMERS_CACHE": MODEL_CACHE_DIR,
    })
    .add_local_dir(".", "/root")
)

model_cache = modal.Volume.from_name("medgemma-cache", create_if_missing=True)
chroma_db = modal.Volume.from_name("chroma-db", create_if_missing=True)
gemini_secret = modal.Secret.from_name("gemini-api-key")
hf_secret = modal.Secret.from_name("huggingface-token")

app = modal.App("sturgeon-medgemma")

MODEL_ID = "google/medgemma-1.5-4b-it"
VLLM_PORT = 6501
MEDSIGLIP_PORT = 6502


@app.cls(
    image=base_image,
    gpu="L4",
    volumes={
        MODEL_CACHE_DIR: model_cache,
        CHROMA_DB_DIR: chroma_db,
    },
    secrets=[gemini_secret, hf_secret],
    timeout=600,
    scaledown_window=600,
    memory=16384,
    cpu=4,
    max_containers=1,
)
class SturgeonService:
    """Modal class hosting vLLM, MedSigLIP, and FastAPI ASGI app."""
    
    @modal.enter()
    def start_servers(self):
        """Start vLLM and MedSigLIP servers on container startup."""
        import subprocess
        import time
        import httpx
        import os
        import sys
        
        sys.path.insert(0, "/root")
        
        from structured_logging import setup_logging, StructuredLogger, set_request_id
        setup_logging()
        self.logger = StructuredLogger(__name__)
        
        self.set_request_id = set_request_id
        self.sessions = {}
        self.max_sessions = int(os.getenv("MAX_SESSIONS", "500"))
        
        self.logger.info("Starting vLLM server...")
        env = os.environ.copy()
        self.vllm_proc = subprocess.Popen([
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", MODEL_ID,
            "--host", "0.0.0.0",
            "--port", str(VLLM_PORT),
            "--trust-remote-code",
            "--max-model-len", "4096",
            "--gpu-memory-utilization", "0.70",
            "--enforce-eager",
            "--disable-log-requests",
        ], env=env)
        
        self.logger.info("Starting MedSigLIP server...")
        self.medsiglip_proc = subprocess.Popen([
            "python", "-m", "uvicorn",
            "medsiglip_server:app",
            "--host", "0.0.0.0",
            "--port", str(MEDSIGLIP_PORT),
        ], cwd="/root")
        
        self.logger.info("Waiting for servers to be ready...")
        for i in range(180):
            try:
                vllm_health = httpx.get(f"http://localhost:{VLLM_PORT}/health", timeout=5)
                siglip_health = httpx.get(f"http://localhost:{MEDSIGLIP_PORT}/health", timeout=5)
                if vllm_health.status_code == 200 and siglip_health.status_code == 200:
                    self.logger.info("All servers ready!")
                    break
            except Exception as e:
                if i % 10 == 0:
                    self.logger.info(f"Waiting for servers... ({i}/180): {e}")
            time.sleep(2)
        else:
            self.logger.error("Servers failed to start in time")
        
        self._init_clients()
        self._init_rag()
        self._init_gemini()
    
    def _init_clients(self):
        """Initialize HTTP clients for vLLM and MedSigLIP."""
        import httpx
        
        self.vllm_client = httpx.AsyncClient(
            base_url=f"http://localhost:{VLLM_PORT}",
            timeout=300.0
        )
        self.siglip_client = httpx.AsyncClient(
            base_url=f"http://localhost:{MEDSIGLIP_PORT}",
            timeout=30.0
        )
        self.logger.info("HTTP clients initialized")
    
    def _init_rag(self):
        """Initialize RAG retriever."""
        from rag_retriever import get_retriever
        
        try:
            guidelines_dir = "/root/guidelines"
            self.retriever = get_retriever(
                guidelines_dir=guidelines_dir,
                cache_dir=f"{CHROMA_DB_DIR}/.chroma_cache"
            )
            if self.retriever.initialize():
                self.rag_available = True
                self.logger.info(f"RAG initialized: {self.retriever.indexing_stats['num_chunks']} chunks")
            else:
                self.rag_available = False
                self.logger.warning("RAG initialization failed")
        except Exception as e:
            self.logger.warning(f"RAG not available: {e}")
            self.rag_available = False
    
    def _init_gemini(self):
        """Initialize Gemini orchestrator."""
        import os
        
        try:
            from gemini_orchestrator_modal import get_orchestrator
            
            self.orchestrator = get_orchestrator()
            self.orchestrator.vllm_base_url = f"http://localhost:{VLLM_PORT}"
            self.orchestrator.initialize()
            self.gemini_available = True
            self.logger.info("Gemini orchestrator initialized")
        except Exception as e:
            self.logger.warning(f"Gemini orchestrator not available: {e}")
            self.gemini_available = False
    
    @modal.exit()
    def cleanup(self):
        """Cleanup on container shutdown."""
        if hasattr(self, 'vllm_proc'):
            self.vllm_proc.terminate()
        if hasattr(self, 'medsiglip_proc'):
            self.medsiglip_proc.terminate()
        self.logger.info("Servers stopped")
    
    @modal.asgi_app()
    def serve(self):
        """Return FastAPI ASGI app with all endpoints."""
        from fastapi import FastAPI, HTTPException, UploadFile, File, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from pydantic import ValidationError
        import sys
        import os
        import uuid
        import base64
        import io
        import time
        import asyncio
        import re
        import pdfplumber
        from PIL import Image

        sys.path.insert(0, "/root")
        from prompts import SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT
        from prompts import DEBATE_TURN_PROMPT, DEBATE_TURN_PROMPT_WITH_RAG, SUMMARY_PROMPT
        from models import (
            ExtractLabsRequest,
            ExtractLabsResponse,
            ExtractLabsFileResponse,
            DifferentialRequest,
            DifferentialResponse,
            DebateTurnRequest,
            SummaryRequest,
            SummaryResponse,
            Diagnosis,
        )
        from json_utils import extract_json
        from refusal import is_pure_refusal, strip_refusal_preamble
        from formatters import format_lab_values, format_differential, format_rounds
        from hallucination_check import validate_differential_response, validate_debate_response
        from rate_limiter import check_rate_limit
        from input_sanitization import (
            sanitize_patient_history,
            sanitize_lab_text,
            sanitize_challenge,
            sanitize_filename,
            validate_file_type,
            validate_image_type,
        )
        from structured_logging import StructuredLogger, log_request
        from gemini_orchestrator_modal import ClinicalState, extract_citations, GUIDELINE_URLS
        from rag_evaluation import get_evaluator, RetrievedContext

        logger = StructuredLogger("api")
        rag_distance_threshold = 1.3

        fastapi_app = FastAPI(
            title="Sturgeon AI Service",
            description="Medical diagnostic debate API",
            version="0.6.0",
        )

        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "https://sturgeon.vercel.app",
                "http://localhost:3000",
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

        def _parse_differential(updated_diff: list) -> list[dict]:
            diagnoses = []
            for dx in updated_diff:
                if not isinstance(dx, dict):
                    continue
                name = dx.get("name") or dx.get("diagnosis") or dx.get("diagnosis_name") or "Unknown"
                probability = dx.get("probability") or dx.get("likelihood") or "medium"
                supporting = dx.get("supporting_evidence") or dx.get("supporting") or dx.get("evidence_for") or []
                against = dx.get("against_evidence") or dx.get("against") or dx.get("evidence_against") or []
                tests = dx.get("suggested_tests") or dx.get("tests") or dx.get("workup") or []

                if probability not in ["high", "medium", "low"]:
                    probability = "medium"

                diagnoses.append(
                    Diagnosis(
                        name=name,
                        probability=probability,
                        supporting_evidence=supporting if isinstance(supporting, list) else [str(supporting)],
                        against_evidence=against if isinstance(against, list) else [str(against)],
                        suggested_tests=tests if isinstance(tests, list) else [str(tests)],
                    ).model_dump()
                )
            return diagnoses

        def _is_valid_http_url(url: str) -> bool:
            return url.startswith("https://") or url.startswith("http://")

        def _normalize_citations(citations: list[dict]) -> list[dict]:
            normalized = []
            seen = set()

            for citation in citations or []:
                if not isinstance(citation, dict):
                    continue

                text = str(citation.get("text", "")).strip()
                source = str(citation.get("source", "")).strip() or "Unknown"
                url = str(citation.get("url", "")).strip()

                if (not url or not _is_valid_http_url(url)) and source in GUIDELINE_URLS:
                    url = GUIDELINE_URLS[source]

                if not _is_valid_http_url(url):
                    continue

                if not text:
                    text = source

                key = (text, url)
                if key in seen:
                    continue
                seen.add(key)

                normalized.append({
                    "text": text,
                    "url": url,
                    "source": source,
                })

            return normalized

        def _extract_vllm_error_message(response_payload: object, raw_text: str) -> str:
            if isinstance(response_payload, dict):
                error = response_payload.get("error")
                if isinstance(error, dict):
                    return str(error.get("message") or error.get("type") or error)
                if error:
                    return str(error)

                detail = response_payload.get("detail")
                if detail:
                    return str(detail)

            return raw_text[:1000] if raw_text else "Unknown vLLM error"

        def _truncate_text(text: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            head = int(max_chars * 0.7)
            tail = max_chars - head - 32
            return text[:head] + "\n...[truncated for token budget]...\n" + text[-tail:]

        def _is_input_overflow_error(error_message: str) -> bool:
            return (
                "parameter=input_tokens" in error_message
                or ("maximum context length" in error_message and "input tokens" in error_message)
            )

        def _compact_messages_for_retry(messages: list[dict]) -> list[dict]:
            compacted: list[dict] = []
            for message in messages:
                content = message.get("content")
                new_message = dict(message)

                if isinstance(content, str):
                    new_message["content"] = _truncate_text(content, 2800)
                elif isinstance(content, list):
                    new_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                            new_part = dict(part)
                            new_part["text"] = _truncate_text(part["text"], 1800)
                            new_parts.append(new_part)
                        else:
                            new_parts.append(part)
                    new_message["content"] = new_parts

                compacted.append(new_message)

            return compacted

        def _infer_retry_max_tokens(error_message: str, requested_max_tokens: int) -> int | None:
            if "max_tokens" not in error_message and "max_completion_tokens" not in error_message:
                return None

            max_len = None
            input_tokens = None

            expression_match = re.search(r"\((\d+)\s*>\s*(\d+)\s*-\s*(\d+)\)", error_message)
            if expression_match:
                max_len = int(expression_match.group(2))
                input_tokens = int(expression_match.group(3))
            else:
                max_len_match = re.search(r"maximum context length is\s*(\d+)", error_message, re.IGNORECASE)
                input_match = re.search(r"request has\s*(\d+)\s*input tokens", error_message, re.IGNORECASE)
                if max_len_match and input_match:
                    max_len = int(max_len_match.group(1))
                    input_tokens = int(input_match.group(1))

            if max_len is None or input_tokens is None:
                return None

            safe_margin = 32
            retry_max_tokens = max(128, max_len - input_tokens - safe_margin)
            if retry_max_tokens >= requested_max_tokens:
                return None
            return retry_max_tokens

        async def _call_vllm_chat(
            *,
            endpoint_name: str,
            messages: list[dict],
            max_tokens: int,
            temperature: float,
        ) -> tuple[str, int]:
            requested_max_tokens = max_tokens
            last_error = "Unknown error"
            messages_to_send = messages
            compacted_for_input_overflow = False

            for attempt in range(2):
                response = await self.vllm_client.post(
                    "/v1/chat/completions",
                    json={
                        "model": MODEL_ID,
                        "messages": messages_to_send,
                        "max_tokens": requested_max_tokens,
                        "temperature": temperature,
                    },
                )

                raw_text = response.text
                try:
                    payload = response.json()
                except Exception:
                    payload = None

                if response.status_code == 200 and isinstance(payload, dict):
                    choices = payload.get("choices")
                    if isinstance(choices, list) and choices:
                        message = choices[0].get("message", {})
                        content = message.get("content")
                        if isinstance(content, str):
                            return content, requested_max_tokens

                    last_error = "vLLM returned 200 without choices/message content"
                    break

                error_message = _extract_vllm_error_message(payload, raw_text)
                last_error = f"{response.status_code}: {error_message}"

                retry_max_tokens = _infer_retry_max_tokens(error_message, requested_max_tokens)
                if retry_max_tokens and attempt == 0:
                    logger.warning(
                        "vLLM max token overflow; retrying with reduced output budget",
                        endpoint=endpoint_name,
                        requested_max_tokens=requested_max_tokens,
                        retry_max_tokens=retry_max_tokens,
                    )
                    requested_max_tokens = retry_max_tokens
                    continue

                if _is_input_overflow_error(error_message) and attempt == 0 and not compacted_for_input_overflow:
                    logger.warning(
                        "vLLM input token overflow; retrying with compacted prompt",
                        endpoint=endpoint_name,
                    )
                    messages_to_send = _compact_messages_for_retry(messages_to_send)
                    requested_max_tokens = min(requested_max_tokens, 1024)
                    compacted_for_input_overflow = True
                    continue

                break

            raise RuntimeError(f"vLLM call failed ({endpoint_name}): {last_error}")

        def _compact_previous_rounds(
            rounds: list[dict],
            max_rounds: int = 2,
            challenge_chars: int = 240,
            response_chars: int = 320,
        ) -> list[dict]:
            if not rounds:
                return []

            compacted = []
            for round_data in rounds[-max_rounds:]:
                challenge = str(round_data.get("user_challenge", round_data.get("challenge", "")))
                response = str(round_data.get("ai_response", round_data.get("response", "")))
                compacted.append(
                    {
                        "user_challenge": _truncate_text(challenge, challenge_chars),
                        "ai_response": _truncate_text(response, response_chars),
                    }
                )
            return compacted

        def _trim_retrieved_context(context: str, max_chars: int = 2400) -> str:
            if not context:
                return ""
            return _truncate_text(context, max_chars)

        async def _retrieve_rag_context(user_challenge: str, current_differential: list, timeout_seconds: float = 5.0) -> str:
            if not self.rag_available:
                return ""

            dx_names = [d.name for d in current_differential[:3]]
            rag_query = (
                f"{user_challenge} | Clinical context: {', '.join(dx_names)}"
                if dx_names
                else user_challenge
            )

            try:
                chunks, rag_error = await asyncio.to_thread(
                    self.retriever.retrieve,
                    query=rag_query,
                    ip_address="internal",
                )
                if rag_error or not chunks:
                    return ""

                relevant_chunks = [c for c in chunks if c.distance <= rag_distance_threshold]
                if not relevant_chunks:
                    return ""

                compact_chunks = relevant_chunks[:4]
                return _trim_retrieved_context(self.retriever.format_retrieved_context(compact_chunks))
            except asyncio.TimeoutError:
                logger.warning("RAG retrieval timed out", timeout_seconds=timeout_seconds)
                return ""
            except Exception as e:
                logger.warning("RAG retrieval failed", error=str(e))
                return ""

        async def _debate_turn_orchestrated(request_model: DebateTurnRequest, session_id: str) -> dict:
            rag_task = asyncio.create_task(
                _retrieve_rag_context(request_model.user_challenge, request_model.current_differential)
            )

            if session_id not in self.sessions:
                if len(self.sessions) >= self.max_sessions:
                    oldest_session = next(iter(self.sessions))
                    self.sessions.pop(oldest_session, None)
                self.sessions[session_id] = ClinicalState(
                    patient_history=request_model.patient_history,
                    lab_values=request_model.lab_values,
                    differential=[d.model_dump() for d in request_model.current_differential],
                    image_context=request_model.image_context or "",
                )

            clinical_state = self.sessions[session_id]
            clinical_state.differential = [d.model_dump() for d in request_model.current_differential]

            retrieved_context = ""
            try:
                retrieved_context = await asyncio.wait_for(rag_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("RAG retrieval timed out after 5s")

            try:
                result = await asyncio.to_thread(
                    self.orchestrator.process_debate_turn,
                    user_challenge=request_model.user_challenge,
                    clinical_state=clinical_state,
                    previous_rounds=_compact_previous_rounds(request_model.previous_rounds or []),
                    retrieved_context=retrieved_context,
                )

                diagnoses = _parse_differential(result.get("updated_differential", []))
                citations = _normalize_citations(result.get("citations", []))
                return {
                    "ai_response": result.get("ai_response", "I need more information to respond."),
                    "updated_differential": diagnoses if diagnoses else [d.model_dump() for d in request_model.current_differential],
                    "suggested_test": result.get("suggested_test"),
                    "session_id": session_id,
                    "orchestrated": True,
                    "citations": citations,
                    "has_guidelines": len(citations) > 0,
                    "rag_used": bool(retrieved_context),
                }
            except Exception as e:
                logger.error("Orchestrator failed, falling back to MedGemma", error=str(e))
                return await _debate_turn_medgemma_only(request_model, session_id)

        async def _debate_turn_medgemma_only(request_model: DebateTurnRequest, session_id: str) -> dict:
            rag_task = asyncio.create_task(
                _retrieve_rag_context(request_model.user_challenge, request_model.current_differential)
            )

            formatted_labs = format_lab_values(request_model.lab_values)
            formatted_diff = format_differential([d.model_dump() for d in request_model.current_differential])
            compact_rounds = _compact_previous_rounds(request_model.previous_rounds)
            formatted_rounds = format_rounds(compact_rounds)
            image_context = _truncate_text(request_model.image_context or "No image evidence available", 900)
            compact_history = _truncate_text(request_model.patient_history, 1800)

            retrieved_guidelines = ""
            try:
                retrieved_guidelines = await asyncio.wait_for(rag_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("RAG fallback retrieval timed out after 5s")

            if retrieved_guidelines:
                prompt = DEBATE_TURN_PROMPT_WITH_RAG.format(
                    patient_history=compact_history,
                    formatted_lab_values=formatted_labs,
                    current_differential=formatted_diff,
                    previous_rounds=formatted_rounds,
                    user_challenge=request_model.user_challenge,
                    image_context=image_context,
                    retrieved_guidelines=retrieved_guidelines,
                )
            else:
                prompt = DEBATE_TURN_PROMPT.format(
                    patient_history=compact_history,
                    formatted_lab_values=formatted_labs,
                    current_differential=formatted_diff,
                    previous_rounds=formatted_rounds,
                    user_challenge=request_model.user_challenge,
                    image_context=image_context,
                )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                content, _ = await _call_vllm_chat(
                    endpoint_name="debate-turn-fallback",
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.7,
                )
                data = extract_json(content)

                validation = validate_debate_response(
                    data,
                    request_model.lab_values,
                    request_model.patient_history,
                )
                if validation["has_hallucination"]:
                    logger.warning("Hallucination detected", warnings=validation["warnings"])
                    correction_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Your previous response contained fabricated lab values not provided by the user. "
                        + "Only use data from the Patient History and Lab Values sections above. "
                        + "If a lab value was not provided, do not invent one.\n\nReturn corrected JSON:"
                    )
                    correction_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": correction_prompt},
                    ]
                    retry_content, _ = await _call_vllm_chat(
                        endpoint_name="debate-turn-fallback-retry",
                        messages=correction_messages,
                        max_tokens=2048,
                        temperature=0.2,
                    )
                    data = extract_json(retry_content)

                diagnoses = _parse_differential(data.get("updated_differential", []))
                ai_response_text = data.get("ai_response", "")
                _, citations_raw = extract_citations(ai_response_text)
                citations = _normalize_citations(citations_raw)

                return {
                    "ai_response": ai_response_text,
                    "updated_differential": diagnoses if diagnoses else [d.model_dump() for d in request_model.current_differential],
                    "suggested_test": data.get("suggested_test"),
                    "session_id": session_id,
                    "orchestrated": False,
                    "citations": citations,
                    "has_guidelines": len(citations) > 0,
                    "rag_used": bool(retrieved_guidelines),
                }
            except Exception as e:
                logger.error("MedGemma-only debate turn failed", error=str(e))
                raise RuntimeError(str(e)) from e

        @fastapi_app.middleware("http")
        async def request_logging_middleware(request: Request, call_next):
            """Middleware for request ID tracking and logging."""
            start_time = time.time()
            request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
            self.set_request_id(request_id)

            response = await call_next(request)

            duration_ms = (time.time() - start_time) * 1000

            if request.url.path not in ["/health", "/docs", "/openapi.json"]:
                log_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

            response.headers["X-Request-ID"] = request_id
            return response

        @fastapi_app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "vllm": "running",
                "medsiglip": "running",
                "gemini_orchestrator": self.gemini_available,
                "rag_retriever": self.rag_available,
                "mode": "agentic" if self.gemini_available else "medgemma-only",
                "image_triage": "medsiglip+medgemma",
                "guideline_retrieval": "vector-rag" if self.rag_available else "prompt-only",
                "active_sessions": len(self.sessions),
            }

        @fastapi_app.get("/rag-status")
        async def rag_status():
            if not self.rag_available:
                return {
                    "available": False,
                    "message": "RAG retriever not initialized. Check ChromaDB initialization logs.",
                }
            try:
                return {
                    "available": True,
                    **self.retriever.get_status(),
                }
            except Exception as e:
                return {
                    "available": False,
                    "error": str(e),
                }

        @fastapi_app.post("/rag-evaluate")
        async def rag_evaluate(request: dict):
            if not os.getenv("ENABLE_RAG_EVAL"):
                raise HTTPException(status_code=404, detail="Not found")

            question = request.get("question", "")
            response_text = request.get("response", "")
            contexts_data = request.get("retrieved_contexts", [])

            if not question or not response_text:
                raise HTTPException(status_code=400, detail="question and response are required")

            contexts = [
                RetrievedContext(
                    content=c.get("content", ""),
                    source=c.get("source", "Unknown"),
                    topic=c.get("topic", "general"),
                    distance=c.get("distance", 0.0),
                )
                for c in contexts_data
            ]

            try:
                evaluator = get_evaluator()
                result = await asyncio.to_thread(
                    evaluator.evaluate_response,
                    question,
                    response_text,
                    contexts,
                )
                return result.to_dict()
            except Exception as e:
                logger.error("RAG evaluation failed", error=str(e))
                raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

        @fastapi_app.post("/extract-labs")
        async def extract_labs(request: dict, req: Request):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("extract-labs", req)

            try:
                request_model = ExtractLabsRequest.model_validate(request)
            except ValidationError as e:
                return JSONResponse(
                    {"error": str(e.errors()[0].get("msg", "Invalid request"))},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            lab_report_text = sanitize_lab_text(request_model.lab_report_text)
            if not lab_report_text:
                return JSONResponse(
                    {"error": "lab_report_text is required"},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=lab_report_text)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                content, _ = await _call_vllm_chat(
                    endpoint_name="extract-labs",
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.3,
                )
                data = extract_json(content)
                response_data = ExtractLabsResponse(
                    lab_values=data.get("lab_values", {}),
                    abnormal_values=data.get("abnormal_values", []),
                )

                logger.info("extract-labs completed", duration_ms=round((time.time() - start_time) * 1000, 2))
                return JSONResponse(response_data.model_dump(), headers=rate_limit_headers)
            except Exception as e:
                logger.error("extract-labs failed", error=str(e))
                return JSONResponse(
                    {"error": f"Processing error: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        @fastapi_app.post("/extract-labs-file")
        async def extract_labs_file(req: Request, file: UploadFile = File(...)):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("extract-labs-file", req)

            safe_filename = sanitize_filename(file.filename or "")
            if not validate_file_type(safe_filename, {".pdf", ".txt"}):
                return JSONResponse(
                    {"error": f"Unsupported file type: {safe_filename}. Accepted: .pdf, .txt"},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            raw_text = ""
            try:
                contents = await file.read()
                if safe_filename.lower().endswith(".pdf"):
                    pdf_bytes = io.BytesIO(contents)
                    with pdfplumber.open(pdf_bytes) as pdf:
                        pages_text = []
                        for page in pdf.pages:
                            tables = page.extract_tables()
                            if tables:
                                for table in tables:
                                    for row in table:
                                        cells = [str(cell).strip() for cell in row if cell]
                                        if cells:
                                            pages_text.append("  |  ".join(cells))
                                pages_text.append("")

                            page_text = page.extract_text()
                            if page_text:
                                pages_text.append(page_text)
                        raw_text = "\n".join(pages_text).strip()
                else:
                    raw_text = contents.decode("utf-8", errors="replace").strip()

                raw_text = sanitize_lab_text(raw_text)
                if not raw_text:
                    return JSONResponse(
                        {"error": "Could not extract any text from the uploaded file"},
                        status_code=400,
                        headers=rate_limit_headers,
                    )

                prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=raw_text)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]

                content, _ = await _call_vllm_chat(
                    endpoint_name="extract-labs-file",
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.3,
                )

                try:
                    data = extract_json(content)
                except Exception:
                    logger.warning("extract-labs-file JSON parse failed on first attempt, retrying")
                    retry_content, _ = await _call_vllm_chat(
                        endpoint_name="extract-labs-file-retry",
                        messages=messages,
                        max_tokens=2048,
                        temperature=0.3,
                    )
                    data = extract_json(retry_content)

                response_data = ExtractLabsFileResponse(
                    lab_values=data.get("lab_values", {}),
                    abnormal_values=data.get("abnormal_values", []),
                    raw_text=raw_text[:5000],
                )

                logger.info("extract-labs-file completed", duration_ms=round((time.time() - start_time) * 1000, 2))
                return JSONResponse(response_data.model_dump(), headers=rate_limit_headers)
            except Exception as e:
                logger.error("extract-labs-file failed", error=str(e))
                return JSONResponse(
                    {"error": f"Failed to extract lab values: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        @fastapi_app.post("/differential")
        async def differential(request: dict, req: Request):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("differential", req)

            try:
                request_model = DifferentialRequest.model_validate(request)
            except ValidationError as e:
                return JSONResponse(
                    {"error": str(e.errors()[0].get("msg", "Invalid request"))},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            patient_history = sanitize_patient_history(request_model.patient_history)
            if not patient_history:
                return JSONResponse(
                    {"error": "patient_history is required"},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            formatted_labs = format_lab_values(request_model.lab_values)
            prompt = DIFFERENTIAL_PROMPT.format(
                patient_history=patient_history,
                formatted_lab_values=formatted_labs,
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                content, _ = await _call_vllm_chat(
                    endpoint_name="differential",
                    messages=messages,
                    max_tokens=3072,
                    temperature=0.3,
                )
                data = extract_json(content)

                validation = validate_differential_response(
                    data,
                    request_model.lab_values,
                    patient_history,
                )
                if validation["has_hallucination"]:
                    logger.warning("Hallucination detected", warnings=validation["warnings"])
                    correction_prompt = f"""{prompt}

IMPORTANT CORRECTION: Your previous response contained fabricated lab values that were not provided by the user.
The following values were hallucinated and must not be included:
{chr(10).join(f'- {w}' for w in validation['warnings'])}

Only use data explicitly provided in the Patient History and Lab Values sections above.
If a lab value is not provided, do not invent one.

JSON Response:"""
                    correction_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": correction_prompt},
                    ]
                    retry_content, _ = await _call_vllm_chat(
                        endpoint_name="differential-retry",
                        messages=correction_messages,
                        max_tokens=3072,
                        temperature=0.2,
                    )
                    data = extract_json(retry_content)

                diagnoses = []
                for dx in data.get("diagnoses", []):
                    diagnoses.append(
                        Diagnosis(
                            name=dx.get("name", "Unknown"),
                            probability=dx.get("probability", "medium"),
                            supporting_evidence=dx.get("supporting_evidence", []),
                            against_evidence=dx.get("against_evidence", []),
                            suggested_tests=dx.get("suggested_tests", []),
                        ).model_dump()
                    )

                response_data = DifferentialResponse(diagnoses=[Diagnosis.model_validate(d) for d in diagnoses])
                logger.info(
                    "differential completed",
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    diagnoses_count=len(diagnoses),
                )
                return JSONResponse(response_data.model_dump(), headers=rate_limit_headers)
            except Exception as e:
                logger.error("differential failed", error=str(e))
                return JSONResponse(
                    {"error": f"Processing error: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        @fastapi_app.post("/debate-turn")
        async def debate_turn(request: dict, req: Request):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("debate-turn", req)

            try:
                request_model = DebateTurnRequest.model_validate(request)
            except ValidationError as e:
                return JSONResponse(
                    {"error": str(e.errors()[0].get("msg", "Invalid request"))},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            request_model.patient_history = sanitize_patient_history(request_model.patient_history)
            request_model.user_challenge = sanitize_challenge(request_model.user_challenge)

            if not request_model.user_challenge:
                return JSONResponse(
                    {"error": "user_challenge is required"},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            session_id = request_model.session_id or str(uuid.uuid4())

            try:
                if self.gemini_available:
                    result = await _debate_turn_orchestrated(request_model, session_id)
                else:
                    result = await _debate_turn_medgemma_only(request_model, session_id)

                logger.info(
                    "debate-turn completed",
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    orchestrated=result.get("orchestrated", False),
                    has_guidelines=result.get("has_guidelines", False),
                )
                return JSONResponse(result, headers=rate_limit_headers)
            except Exception as e:
                logger.error("debate-turn failed", error=str(e))
                return JSONResponse(
                    {"error": f"Processing error: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        @fastapi_app.post("/analyze-image")
        async def analyze_image(req: Request, file: UploadFile = File(...)):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("analyze-image", req)

            if not validate_image_type(file.content_type or ""):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported image type: {file.content_type}",
                )

            try:
                contents = await file.read()
                image = Image.open(io.BytesIO(contents)).convert("RGB")
                if max(image.size) > 1024:
                    image.thumbnail((1024, 1024))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read image: {e}")

            img_buffer = io.BytesIO()
            image.save(img_buffer, format="PNG")
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()

            triage_result = {
                "image_type": "medical image",
                "image_type_confidence": 0.0,
                "modality": "unknown",
                "findings": [],
                "triage_summary": "MedSigLIP triage pending.",
            }

            try:
                triage_response = await self.siglip_client.post(
                    "/analyze",
                    files={"file": (file.filename or "image.png", contents, file.content_type or "image/png")},
                )
                if triage_response.status_code == 200:
                    triage_result = triage_response.json()
            except Exception as e:
                logger.warning("MedSigLIP triage failed", error=str(e))

            modality = triage_result.get("modality", "unknown")
            if modality == "uncertain":
                medgemma_prompt = """Analyze this medical image in detail.

First, identify the imaging modality (e.g., chest X-ray, dermatology/skin photograph, histopathology slide, CT scan, MRI, etc.).

Then provide a thorough clinical interpretation including:
1. Image type and quality
2. Key findings
3. Clinical significance
4. Differential considerations
5. Recommended follow-up

Be specific and cite visible features in the image."""
                system_prompt = (
                    "You are a medical imaging specialist experienced in radiology, dermatology, and pathology. "
                    "Analyze medical images with precision and cite specific visual findings."
                )
            else:
                medgemma_prompt = f"""Analyze this medical image in detail.

{triage_result.get('triage_summary', '')}

Provide a thorough clinical interpretation including:
1. Image type and quality
2. Key findings
3. Clinical significance
4. Differential considerations
5. Recommended follow-up

Be specific and cite visible features in the image."""
                system_prompt = (
                    "You are a specialist radiologist and medical imaging expert. "
                    "Analyze medical images with precision and cite specific visual findings."
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                        {"type": "text", "text": medgemma_prompt},
                    ],
                },
            ]

            try:
                medgemma_analysis, used_max_tokens = await _call_vllm_chat(
                    endpoint_name="analyze-image",
                    messages=messages,
                    max_tokens=768,
                    temperature=0.1,
                )

                if is_pure_refusal(medgemma_analysis):
                    retry_prompt = (
                        "Describe the visual findings in this medical image. Focus only on what you observe: "
                        "colors, shapes, textures, borders, symmetry, and any notable features. "
                        "Do not provide a diagnosis, just describe the image."
                    )
                    retry_messages = [
                        {"role": "system", "content": "You are a clinical image analyst. Describe medical images objectively."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                                {"type": "text", "text": retry_prompt},
                            ],
                        },
                    ]
                    retry_analysis, _ = await _call_vllm_chat(
                        endpoint_name="analyze-image-retry",
                        messages=retry_messages,
                        max_tokens=512,
                        temperature=0.3,
                    )
                    if not is_pure_refusal(retry_analysis):
                        medgemma_analysis = retry_analysis

                medgemma_analysis = strip_refusal_preamble(medgemma_analysis)

                logger.info(
                    "analyze-image completed",
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    modality=triage_result.get("modality", "unknown"),
                    max_tokens_used=used_max_tokens,
                )

                return JSONResponse(
                    {
                        "image_type": triage_result.get("image_type", "medical image"),
                        "image_type_confidence": triage_result.get("image_type_confidence", 0.0),
                        "modality": triage_result.get("modality", "unknown"),
                        "triage_findings": triage_result.get("findings", []),
                        "triage_summary": triage_result.get("triage_summary", ""),
                        "medgemma_analysis": medgemma_analysis,
                    },
                    headers=rate_limit_headers,
                )
            except Exception as e:
                logger.error("analyze-image failed", error=str(e))
                return JSONResponse(
                    {"error": f"Processing error: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        @fastapi_app.post("/summary")
        async def summary(request: dict, req: Request):
            start_time = time.time()
            rate_limit_headers = check_rate_limit("summary", req)

            try:
                request_model = SummaryRequest.model_validate(request)
            except ValidationError as e:
                return JSONResponse(
                    {"error": str(e.errors()[0].get("msg", "Invalid request"))},
                    status_code=400,
                    headers=rate_limit_headers,
                )

            patient_history = sanitize_patient_history(request_model.patient_history)
            formatted_labs = format_lab_values(request_model.lab_values)
            formatted_diff = format_differential([d.model_dump() for d in request_model.final_differential])
            formatted_rounds = format_rounds(request_model.debate_rounds)

            prompt = SUMMARY_PROMPT.format(
                patient_history=patient_history,
                formatted_lab_values=formatted_labs,
                final_differential=formatted_diff,
                debate_rounds=formatted_rounds,
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                content, _ = await _call_vllm_chat(
                    endpoint_name="summary",
                    messages=messages,
                    max_tokens=3072,
                    temperature=0.3,
                )
                data = extract_json(content)

                ruled_out_raw = data.get("ruled_out", [])
                ruled_out = []
                for item in ruled_out_raw:
                    if isinstance(item, str):
                        ruled_out.append(item)
                    elif isinstance(item, dict):
                        ruled_out.append(item.get("diagnosis", item.get("name", str(item))))
                    else:
                        ruled_out.append(str(item))

                response_data = SummaryResponse(
                    final_diagnosis=data.get("final_diagnosis", "Unable to determine"),
                    confidence=data.get("confidence", "low"),
                    confidence_percent=data.get("confidence_percent"),
                    reasoning_chain=data.get("reasoning_chain", []),
                    ruled_out=ruled_out,
                    next_steps=data.get("next_steps", []),
                )

                logger.info(
                    "summary completed",
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    confidence=data.get("confidence", "low"),
                )

                return JSONResponse(response_data.model_dump(), headers=rate_limit_headers)
            except Exception as e:
                logger.error("summary failed", error=str(e))
                return JSONResponse(
                    {"error": f"Processing error: {str(e)}"},
                    status_code=500,
                    headers=rate_limit_headers,
                )

        return fastapi_app


@app.local_entrypoint()
def main():
    """Test the deployment locally."""

    print("Testing Sturgeon Modal deployment...")
    print("\nAfter deployment, your single URL will be:")
    print("https://weekijie--sturgeon-medgemma.modal.run")
    print("\nEndpoints:")
    print("  GET  /health")
    print("  GET  /rag-status")
    print("  POST /rag-evaluate")
    print("  POST /extract-labs")
    print("  POST /extract-labs-file")
    print("  POST /differential")
    print("  POST /debate-turn")
    print("  POST /analyze-image")
    print("  POST /summary")
