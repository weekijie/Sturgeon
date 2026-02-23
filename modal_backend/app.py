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
import os

MODEL_CACHE_DIR = "/root/.cache/huggingface"
VLLM_CACHE_DIR = "/root/.cache/vllm"
CHROMA_DB_DIR = "/root/chroma_db"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_MEMORY_SNAPSHOT = _env_bool("ENABLE_MEMORY_SNAPSHOT", True)
ENABLE_GPU_SNAPSHOT = _env_bool("ENABLE_GPU_SNAPSHOT", False)
GPU_SNAPSHOT_OPTIONS = {"enable_gpu_snapshot": True} if ENABLE_GPU_SNAPSHOT else {}
MODAL_MAX_CONTAINERS = max(1, int(os.getenv("MODAL_MAX_CONTAINERS", "1")))
MODAL_MAX_INPUTS = max(1, int(os.getenv("MODAL_MAX_INPUTS", "8")))
MODAL_TARGET_INPUTS = min(
    MODAL_MAX_INPUTS,
    max(1, int(os.getenv("MODAL_TARGET_INPUTS", "4"))),
)

base_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .uv_pip_install(
        "vllm>=0.13.0",
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "python-multipart>=0.0.12",
        "google-genai>=1.0.0",
        "huggingface-hub>=0.36.0",
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
        "HF_XET_HIGH_PERFORMANCE": "1",
        "HF_HOME": MODEL_CACHE_DIR,
    })
    .add_local_dir(".", "/root")
)

model_cache = modal.Volume.from_name("medgemma-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)
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
        VLLM_CACHE_DIR: vllm_cache,
        CHROMA_DB_DIR: chroma_db,
    },
    secrets=[gemini_secret, hf_secret],
    timeout=600,
    scaledown_window=300,
    memory=16384,
    cpu=4,
    max_containers=MODAL_MAX_CONTAINERS,
    enable_memory_snapshot=ENABLE_MEMORY_SNAPSHOT,
    experimental_options=GPU_SNAPSHOT_OPTIONS,
)
@modal.concurrent(max_inputs=MODAL_MAX_INPUTS, target_inputs=MODAL_TARGET_INPUTS)
class SturgeonService:
    """Modal class hosting vLLM, MedSigLIP, and FastAPI ASGI app."""
    
    def _init_runtime_state(self):
        """Initialize logging and process-local state."""
        import sys
        from collections import OrderedDict

        sys.path.insert(0, "/root")

        from structured_logging import setup_logging, StructuredLogger, set_request_id
        setup_logging()
        self.logger = StructuredLogger(__name__)

        self.set_request_id = set_request_id
        self.sessions = {}
        self.max_sessions = int(os.getenv("MAX_SESSIONS", "500"))
        self.rag_query_cache = OrderedDict()
        self.rag_cache_ttl_seconds = int(os.getenv("RAG_CACHE_TTL_SECONDS", "900"))
        self.rag_cache_max_entries = int(os.getenv("RAG_CACHE_MAX_ENTRIES", "256"))
        self.rag_cache_hits = 0
        self.rag_cache_misses = 0
        self.differential_concise_retry_count = 0
        self.summary_concise_retry_count = 0
        self.rag_query_blocked_count = 0
        self.extract_labs_fast_path_count = 0
        self.extract_labs_llm_fallback_count = 0
        self._servers_started = False

    def _start_servers_if_needed(self):
        """Start vLLM and MedSigLIP servers if not already running."""
        import subprocess
        import time
        import httpx
        import sys

        if getattr(self, "_servers_started", False):
            vllm_running = hasattr(self, "vllm_proc") and self.vllm_proc.poll() is None
            medsiglip_running = hasattr(self, "medsiglip_proc") and self.medsiglip_proc.poll() is None
            if vllm_running and medsiglip_running:
                self.logger.info("Inference servers already running")
                return
            self.logger.warning("Server marker set but process exited; restarting servers")

        sys.path.insert(0, "/root")
        
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
        self._servers_started = True

    def _refresh_after_snapshot_restore(self):
        """Refresh network clients and dependencies after snapshot restore."""
        vllm_running = hasattr(self, "vllm_proc") and self.vllm_proc.poll() is None
        medsiglip_running = hasattr(self, "medsiglip_proc") and self.medsiglip_proc.poll() is None

        if not (vllm_running and medsiglip_running):
            self.logger.warning("Snapshot restore without healthy child processes; restarting")
            self._start_servers_if_needed()
            return

        self._init_clients()
        self._init_rag()
        self._init_gemini()

    @modal.enter(snap=True)
    def snapshot_init(self):
        """Pre-snapshot init. In GPU snapshot mode, also pre-start inference stack."""
        self._init_runtime_state()
        self.logger.info(
            "Snapshot init",
            enable_memory_snapshot=ENABLE_MEMORY_SNAPSHOT,
            enable_gpu_snapshot=ENABLE_GPU_SNAPSHOT,
            max_containers=MODAL_MAX_CONTAINERS,
            max_inputs=MODAL_MAX_INPUTS,
            target_inputs=MODAL_TARGET_INPUTS,
        )
        if ENABLE_GPU_SNAPSHOT:
            self.logger.info("GPU snapshot mode enabled: pre-starting inference stack")
            self._start_servers_if_needed()

    @modal.enter(snap=False)
    def start_servers(self):
        """Post-restore init. Start servers for CPU snapshots, refresh for GPU snapshots."""
        self._init_runtime_state()
        if ENABLE_GPU_SNAPSHOT:
            self._refresh_after_snapshot_restore()
        else:
            self._start_servers_if_needed()
    
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
        import hashlib
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
        rag_query_max_chars = 480
        model_max_context = 4096

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

        def _estimate_input_tokens(messages: list[dict]) -> int:
            chars = 0
            for message in messages:
                chars += 24
                content = message.get("content")
                if isinstance(content, str):
                    chars += len(content)
                elif isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            chars += len(str(part))
                            continue
                        if part.get("type") == "text":
                            chars += len(str(part.get("text", "")))
                        elif part.get("type") == "image_url":
                            # Approximate multimodal token cost to avoid overflow.
                            chars += 4200
            # Conservative estimate for safety.
            return max(1, int(chars / 3.4))

        def _preclamp_output_tokens(
            *,
            endpoint_name: str,
            messages: list[dict],
            requested_max_tokens: int,
            safety_margin: int = 96,
        ) -> int:
            estimated_input_tokens = _estimate_input_tokens(messages)
            available_tokens = model_max_context - estimated_input_tokens - safety_margin
            effective_max_tokens = max(128, min(requested_max_tokens, available_tokens))
            if effective_max_tokens < requested_max_tokens:
                logger.info(
                    "Pre-clamped max tokens based on estimated input size",
                    endpoint=endpoint_name,
                    requested_max_tokens=requested_max_tokens,
                    effective_max_tokens=effective_max_tokens,
                    estimated_input_tokens=estimated_input_tokens,
                )
            return effective_max_tokens

        def _truncate_text(text: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            head = int(max_chars * 0.7)
            tail = max_chars - head - 32
            return text[:head] + "\n...[truncated for token budget]...\n" + text[-tail:]

        def _is_likely_truncated_json_response(text: str) -> bool:
            trimmed = text.strip()
            if not trimmed:
                return True
            if trimmed.count("{") > trimmed.count("}"):
                return True
            if trimmed.count("[") > trimmed.count("]"):
                return True
            return not trimmed.endswith("}")

        def _compact_triage_summary(summary: str, max_lines: int = 6, max_chars: int = 520) -> str:
            if not summary:
                return ""
            lines = [line.strip() for line in summary.splitlines() if line.strip()]
            compact = "\n".join(lines[:max_lines])
            return _truncate_text(compact, max_chars)

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
        ) -> tuple[str, int, str | None]:
            requested_max_tokens = _preclamp_output_tokens(
                endpoint_name=endpoint_name,
                messages=messages,
                requested_max_tokens=max_tokens,
            )
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
                        first_choice = choices[0]
                        message = first_choice.get("message", {})
                        content = message.get("content")
                        if isinstance(content, str):
                            finish_reason = first_choice.get("finish_reason")
                            return content, requested_max_tokens, finish_reason

                    last_error = "vLLM returned 200 without choices/message content"
                    break

                error_message = _extract_vllm_error_message(payload, raw_text)
                last_error = f"{response.status_code}: {error_message}"

                retry_max_tokens = _infer_retry_max_tokens(error_message, requested_max_tokens)
                if retry_max_tokens and attempt == 0:
                    preclamped_retry = _preclamp_output_tokens(
                        endpoint_name=endpoint_name,
                        messages=messages_to_send,
                        requested_max_tokens=retry_max_tokens,
                    )
                    logger.warning(
                        "vLLM max token overflow; retrying with reduced output budget",
                        endpoint=endpoint_name,
                        requested_max_tokens=requested_max_tokens,
                        retry_max_tokens=preclamped_retry,
                    )
                    requested_max_tokens = preclamped_retry
                    continue

                if _is_input_overflow_error(error_message) and attempt == 0 and not compacted_for_input_overflow:
                    logger.warning(
                        "vLLM input token overflow; retrying with compacted prompt",
                        endpoint=endpoint_name,
                    )
                    messages_to_send = _compact_messages_for_retry(messages_to_send)
                    requested_max_tokens = _preclamp_output_tokens(
                        endpoint_name=endpoint_name,
                        messages=messages_to_send,
                        requested_max_tokens=min(requested_max_tokens, 1024),
                    )
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

        def _compact_rounds_for_summary(
            rounds: list[dict],
            max_rounds: int = 4,
            challenge_chars: int = 220,
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

        def _compact_lab_report_text(raw_text: str, max_chars: int = 2200, max_lines: int = 120) -> str:
            if not raw_text:
                return ""

            seen = set()
            normalized_lines = []
            for line in str(raw_text).splitlines():
                compact = " ".join(line.split())
                if not compact:
                    continue
                key = compact.lower()
                if key in seen:
                    continue
                seen.add(key)
                normalized_lines.append(compact)

            if not normalized_lines:
                return ""

            anchor_terms = {
                "laboratory report",
                "complete blood count",
                "blood chemistry",
                "metabolic panel",
                "biochemistry",
                "inflammatory markers",
                "lipid profile",
                "thyroid function",
                "notes",
            }
            lab_keywords = (
                "wbc",
                "rbc",
                "hemoglobin",
                "hematocrit",
                "platelets",
                "ldh",
                "alkaline phosphatase",
                "alt",
                "ast",
                "albumin",
                "crp",
                "esr",
                "creatinine",
                "bun",
                "lactate",
                "procalcitonin",
                "glucose",
                "cholesterol",
                "triglyceride",
                "hba1c",
                "test",
                "result",
                "reference",
                "interpretation",
            )

            filtered = []
            for line in normalized_lines:
                lower = line.lower()
                if any(term in lower for term in anchor_terms):
                    filtered.append(line)
                    continue

                has_numeric = bool(re.search(r"\d", line))
                if has_numeric and ("|" in line or ":" in line or any(k in lower for k in lab_keywords)):
                    filtered.append(line)

            final_lines = filtered if filtered else normalized_lines
            if len(final_lines) > max_lines:
                final_lines = final_lines[:max_lines]

            compact_text = "\n".join(final_lines)
            if len(compact_text) > max_chars:
                compact_text = compact_text[:max_chars].rstrip()
            return compact_text

        def _normalize_lab_status(status_text: str) -> str:
            status = (status_text or "").strip().lower()
            if status in {"high", "h", "elevated", "abnormal high", "above range", "positive"}:
                return "high"
            if status in {"low", "l", "decreased", "abnormal low", "below range"}:
                return "low"
            return "normal"

        def _extract_status_hint(text: str) -> str:
            compact = " ".join((text or "").split()).lower()
            if not compact:
                return ""

            if "high" in compact or "elevated" in compact or "above" in compact:
                return "high"
            if "low" in compact or "decreased" in compact or "below" in compact:
                return "low"
            if "normal" in compact or "non reactive" in compact:
                return "normal"
            if re.search(r"(^|[\s(])h([\s):]|$)", compact) or re.search(r"[a-z]h\s+[<>]?\s*\d", compact):
                return "high"
            if re.search(r"(^|[\s(])l([\s):]|$)", compact) or re.search(r"[a-z]l\s+[<>]?\s*\d", compact):
                return "low"
            return ""

        def _parse_value_and_unit(value_text: str) -> tuple[float | None, str]:
            compact = " ".join((value_text or "").split())
            if not compact:
                return None, ""

            match = re.search(r"[<>]?\s*[-+]?\d[\d,]*(?:\.\d+)?", compact)
            if not match:
                return None, ""

            numeric_token = re.sub(r"[^0-9+\-.]", "", match.group(0)).replace(",", "")
            if not numeric_token:
                return None, ""

            try:
                value = float(numeric_token)
            except ValueError:
                return None, ""

            unit = compact[match.end():].strip().lstrip(":=-")
            return value, unit

        def _parse_reference_bounds(reference_text: str) -> tuple[float | None, float | None]:
            compact = " ".join((reference_text or "").split()).replace(",", "")
            if not compact:
                return None, None

            range_match = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)", compact, re.IGNORECASE)
            if range_match:
                try:
                    return float(range_match.group(1)), float(range_match.group(2))
                except ValueError:
                    return None, None

            lt_match = re.search(r"<=?\s*(-?\d+(?:\.\d+)?)", compact)
            if lt_match:
                try:
                    return None, float(lt_match.group(1))
                except ValueError:
                    return None, None

            gt_match = re.search(r">=?\s*(-?\d+(?:\.\d+)?)", compact)
            if gt_match:
                try:
                    return float(gt_match.group(1)), None
                except ValueError:
                    return None, None

            return None, None

        def _infer_status_from_reference(value: float, reference_text: str, fallback_status: str) -> str:
            if fallback_status in {"high", "low"}:
                return fallback_status

            low_bound, high_bound = _parse_reference_bounds(reference_text)
            if low_bound is not None and value < low_bound:
                return "low"
            if high_bound is not None and value > high_bound:
                return "high"
            return fallback_status

        def _clean_lab_test_name(test_name: str) -> str:
            compact = " ".join((test_name or "").split()).strip().strip("|:-")
            compact = re.sub(r"^[\-_.]+", "", compact)
            return compact

        def _is_likely_lab_test_name(test_name: str) -> bool:
            if not test_name:
                return False

            lowered = test_name.lower().strip()
            if not lowered:
                return False

            skip_exact = {
                "test",
                "result",
                "reference range",
                "interpretation",
                "laboratory report",
                "complete blood count (cbc)",
                "complete blood count",
                "metabolic panel",
                "chemistry and inflammatory markers",
                "chemistry and sepsis markers",
                "inflammatory markers",
                "blood chemistry panel",
                "notes",
                "category",
            }
            if lowered in skip_exact:
                return False

            metadata_hints = (
                "patient",
                "requesting doctor",
                "number",
                "age",
                "gender",
                "collection date",
                "received date",
                "report date",
                "location",
                "sample type",
                "status",
                "page",
                "passport",
                "clinic",
                "ref.",
                "lab id",
                "registration",
                "approved on",
                "printed on",
                "scan qr code",
                "laboratory test report",
            )
            if any(hint in lowered for hint in metadata_hints):
                return False

            short_allowed = {
                "ph",
                "t3",
                "t4",
                "tsh",
                "ldh",
                "ast",
                "alt",
                "bun",
                "esr",
                "crp",
                "hba1c",
                "hba1",
            }
            if len(lowered) <= 2 and lowered not in short_allowed:
                return False

            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", lowered):
                return False

            return True

        def _looks_like_unit(unit_text: str) -> bool:
            compact = " ".join((unit_text or "").split()).strip()
            if not compact:
                return False
            if len(compact) > 24:
                return False
            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", compact):
                return False
            return bool(re.search(r"[A-Za-z%/\u00b5]", compact))

        def _looks_like_reference(reference_text: str) -> bool:
            compact = " ".join((reference_text or "").split())
            if not compact:
                return False
            lower = compact.lower()
            if "normal" in lower and "range" in lower:
                return True
            if re.search(r"\d", compact) and re.search(r"-|<|>|≤|≥|to", compact):
                return True
            if "xxx" in lower and "-" in compact:
                return True
            return False

        def _lab_signal_score(test_name: str, unit: str, reference: str, status_hint_present: bool) -> int:
            score = 0
            lowered = test_name.lower()
            if _looks_like_unit(unit):
                score += 1
            if _looks_like_reference(reference):
                score += 1
            if status_hint_present:
                score += 1

            analyte_hints = (
                "wbc",
                "white blood",
                "rbc",
                "red blood",
                "hemoglobin",
                "hematocrit",
                "platelet",
                "creatinine",
                "bun",
                "lactate",
                "crp",
                "esr",
                "procalcitonin",
                "glucose",
                "cholesterol",
                "triglyceride",
                "hba1c",
                "sodium",
                "potassium",
                "chloride",
                "ast",
                "alt",
                "ldh",
                "albumin",
                "bilirubin",
            )
            if any(hint in lowered for hint in analyte_hints):
                score += 1
            return score

        def _select_best_deterministic_parse(candidates: list[dict | None]) -> dict | None:
            valid = [candidate for candidate in candidates if candidate]
            if not valid:
                return None

            valid.sort(
                key=lambda candidate: (
                    candidate.get("score_total", 0),
                    len(candidate.get("abnormal_values", [])),
                    len(candidate.get("lab_values", {})),
                ),
                reverse=True,
            )
            return valid[0]

        def _parse_labs_from_table_text(raw_text: str, mode: str, min_labs: int = 3) -> dict | None:
            if not raw_text or "|" not in raw_text:
                return None

            lab_values = {}
            abnormal_values = []
            score_by_test = {}
            explicit_status_by_test = {}

            for line in str(raw_text).splitlines():
                compact = " ".join(line.split())
                if not compact or "|" not in compact:
                    continue

                columns = [c.strip() for c in compact.split("|") if c.strip()]
                if len(columns) < 3:
                    continue

                test_name = _clean_lab_test_name(columns[0])
                if not _is_likely_lab_test_name(test_name):
                    continue
                if test_name.lower().startswith("clinical note"):
                    continue

                result_text = columns[1]
                value, unit = _parse_value_and_unit(result_text)
                if value is None and len(columns) >= 3:
                    value, unit = _parse_value_and_unit(f"{columns[1]} {columns[2]}")
                if value is None:
                    continue

                if len(columns) >= 4:
                    reference = columns[2]
                    status_source = " ".join(columns[3:])
                else:
                    reference = columns[2]
                    status_source = ""

                status_hint = _extract_status_hint(f"{status_source} {result_text}")
                status = _normalize_lab_status(status_hint)
                if not status_hint:
                    status = _infer_status_from_reference(value, reference, status)

                signal_score = _lab_signal_score(
                    test_name=test_name,
                    unit=unit,
                    reference=reference,
                    status_hint_present=bool(status_hint),
                )
                if signal_score < 2:
                    continue

                dedupe_key = test_name.lower()
                previous_score = score_by_test.get(dedupe_key, -1)
                if signal_score < previous_score:
                    continue

                lab_values[test_name] = {
                    "value": value,
                    "unit": unit,
                    "reference": reference,
                    "status": status,
                }
                score_by_test[dedupe_key] = signal_score
                explicit_status_by_test[test_name] = bool(status_hint)

            if len(lab_values) < min_labs:
                return None

            score_total = 0
            for test_name, payload in lab_values.items():
                if payload["status"] in {"high", "low"}:
                    abnormal_values.append(test_name)
                score_total += _lab_signal_score(
                    test_name=test_name,
                    unit=str(payload.get("unit", "")),
                    reference=str(payload.get("reference", "")),
                    status_hint_present=explicit_status_by_test.get(test_name, False),
                )

            return {
                "lab_values": lab_values,
                "abnormal_values": abnormal_values,
                "score_total": score_total,
                "mode": mode,
            }

        def _parse_labs_from_flat_text(raw_text: str, mode: str, min_labs: int = 3) -> dict | None:
            if not raw_text:
                return None

            method_tokens = {
                "colorimetric",
                "calculated",
                "derived",
                "microscopic",
                "electrical",
                "impedance",
                "method",
                "direct",
                "analysis",
                "analysish",
                "cube",
                "cell",
                "sf",
                "chemiluminescence",
                "immunoassay",
                "clia",
                "hplc",
                "ifcc",
            }

            flat_pattern = re.compile(
                r"([<>]?\s*[-+]?\d[\d,]*(?:\.\d+)?)\s+(\S{1,18})\s+((?:[<>]=?\s*)?-?\d[\d,]*(?:\.\d+)?(?:\s*(?:-|to)\s*-?\d[\d,]*(?:\.\d+)?)?)\s*$",
                re.IGNORECASE,
            )

            lab_values = {}
            abnormal_values = []
            score_by_test = {}

            for line in str(raw_text).splitlines():
                compact = " ".join(line.split())
                if not compact or "|" in compact:
                    continue
                if len(compact) < 12 or len(compact) > 160:
                    continue
                if not re.search(r"\d", compact):
                    continue

                match = flat_pattern.search(compact)
                if not match:
                    continue

                value_text = match.group(1)
                unit = match.group(2)
                reference = match.group(3)
                prefix = compact[:match.start()].strip(" :-")
                if not prefix:
                    continue

                prefix_tokens = prefix.split()
                while prefix_tokens:
                    token = prefix_tokens[-1].strip(",.()").lower()
                    if token in method_tokens or token in {"h", "l"}:
                        prefix_tokens.pop()
                        continue
                    break

                test_name = _clean_lab_test_name(" ".join(prefix_tokens))
                if not _is_likely_lab_test_name(test_name):
                    continue

                value, _ = _parse_value_and_unit(value_text)
                if value is None:
                    continue

                status_hint = _extract_status_hint(prefix)
                status = _normalize_lab_status(status_hint)
                if not status_hint:
                    status = _infer_status_from_reference(value, reference, status)

                signal_score = _lab_signal_score(
                    test_name=test_name,
                    unit=unit,
                    reference=reference,
                    status_hint_present=bool(status_hint),
                )
                if signal_score < 3:
                    continue

                dedupe_key = test_name.lower()
                previous_score = score_by_test.get(dedupe_key, -1)
                if signal_score < previous_score:
                    continue

                lab_values[test_name] = {
                    "value": value,
                    "unit": unit,
                    "reference": reference,
                    "status": status,
                }
                score_by_test[dedupe_key] = signal_score

            if len(lab_values) < min_labs:
                return None

            score_total = 0
            for test_name, payload in lab_values.items():
                if payload["status"] in {"high", "low"}:
                    abnormal_values.append(test_name)
                score_total += _lab_signal_score(
                    test_name=test_name,
                    unit=str(payload.get("unit", "")),
                    reference=str(payload.get("reference", "")),
                    status_hint_present=payload["status"] in {"high", "low"},
                )

            return {
                "lab_values": lab_values,
                "abnormal_values": abnormal_values,
                "score_total": score_total,
                "mode": mode,
            }

        def _clamp_rag_query(query: str, max_chars: int = 480) -> str:
            if max_chars <= 0:
                return ""

            compact = " ".join(str(query).split())
            if len(compact) <= max_chars:
                return compact

            cutoff = compact.rfind(" ", 0, max_chars + 1)
            if cutoff < int(max_chars * 0.6):
                cutoff = max_chars
            return compact[:cutoff].rstrip()

        def _rag_cache_key(user_challenge: str, current_differential: list) -> str:
            dx_names = []
            for diagnosis in current_differential[:4]:
                if hasattr(diagnosis, "name"):
                    dx_names.append(str(diagnosis.name).strip().lower())
                elif isinstance(diagnosis, dict):
                    dx_names.append(str(diagnosis.get("name", "")).strip().lower())
            payload = f"{user_challenge.strip().lower()}|{','.join(dx_names)}"
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

        def _rag_cache_get(cache_key: str) -> str:
            if self.rag_cache_ttl_seconds <= 0:
                return ""

            entry = self.rag_query_cache.get(cache_key)
            if not entry:
                self.rag_cache_misses += 1
                return ""

            now = time.time()
            age_seconds = now - float(entry.get("ts", 0))
            if age_seconds > self.rag_cache_ttl_seconds:
                self.rag_query_cache.pop(cache_key, None)
                self.rag_cache_misses += 1
                return ""

            self.rag_cache_hits += 1
            return str(entry.get("context", ""))

        def _rag_cache_set(cache_key: str, context: str) -> None:
            if self.rag_cache_ttl_seconds <= 0 or not context:
                return

            self.rag_query_cache[cache_key] = {
                "context": context,
                "ts": time.time(),
            }

            while len(self.rag_query_cache) > self.rag_cache_max_entries:
                self.rag_query_cache.popitem(last=False)

        def _infer_topic_hints(user_challenge: str, current_differential: list) -> set[str]:
            combined = user_challenge.lower()
            for dx in current_differential[:4]:
                if hasattr(dx, "name"):
                    combined += " " + str(dx.name).lower()
                elif isinstance(dx, dict):
                    combined += " " + str(dx.get("name", "")).lower()

            hints: set[str] = set()
            topic_map = {
                "melanoma": ["melanoma", "pigmented", "nevus", "lesion", "skin", "dermat"],
                "melanoma_diagnosis": ["melanoma", "pigmented", "nevus", "lesion", "skin", "dermat"],
                "pneumonia_treatment": ["pneumonia", "cap", "respiratory", "chest", "lung", "legionella"],
                "pneumonia_severity": ["pneumonia", "cap", "respiratory", "chest", "lung", "legionella"],
                "sepsis": ["sepsis", "sofa", "qsofa", "sirs", "shock", "lactate"],
                "sepsis_diagnosis": ["sepsis", "sofa", "qsofa", "sirs", "shock", "lactate"],
            }

            for topic, keywords in topic_map.items():
                if any(keyword in combined for keyword in keywords):
                    hints.add(topic)

            return hints

        def _select_diverse_chunks(chunks: list, max_chunks: int = 4) -> list:
            selected = []
            topic_counts: dict[str, int] = {}
            source_counts: dict[str, int] = {}

            sorted_chunks = sorted(chunks, key=lambda c: c.distance)
            for chunk in sorted_chunks:
                topic = str(getattr(chunk, "topic", "general") or "general")
                source = str(getattr(chunk, "organization", "Unknown") or "Unknown")

                if topic_counts.get(topic, 0) >= 2:
                    continue
                if source_counts.get(source, 0) >= 2:
                    continue

                selected.append(chunk)
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
                source_counts[source] = source_counts.get(source, 0) + 1

                if len(selected) >= max_chunks:
                    break

            if len(selected) < min(2, len(sorted_chunks)):
                selected = sorted_chunks[:max_chunks]

            return selected

        async def _retrieve_rag_context(user_challenge: str, current_differential: list, timeout_seconds: float = 5.0) -> str:
            if not self.rag_available:
                return ""

            cache_key = _rag_cache_key(user_challenge, current_differential)
            cached_context = _rag_cache_get(cache_key)
            if cached_context:
                logger.info("RAG cache hit", cache_hits=self.rag_cache_hits, cache_misses=self.rag_cache_misses)
                return cached_context

            dx_names = []
            for diagnosis in current_differential[:3]:
                if hasattr(diagnosis, "name"):
                    dx_names.append(str(diagnosis.name))
                elif isinstance(diagnosis, dict):
                    dx_names.append(str(diagnosis.get("name", "")))

            challenge_text = " ".join(user_challenge.split())
            context_suffix = f" | Clinical context: {', '.join(dx_names)}" if dx_names else ""
            challenge_budget = rag_query_max_chars - len(context_suffix)

            if challenge_budget < 48:
                context_suffix = ""
                challenge_budget = rag_query_max_chars

            rag_query = _clamp_rag_query(challenge_text, max_chars=challenge_budget)
            if context_suffix:
                rag_query = f"{rag_query}{context_suffix}"
            rag_query = _clamp_rag_query(rag_query, max_chars=rag_query_max_chars)

            try:
                chunks, rag_error = await asyncio.to_thread(
                    self.retriever.retrieve,
                    query=rag_query,
                    ip_address="internal",
                    top_k=8,
                )
                if rag_error:
                    if "maximum length" in rag_error.lower():
                        self.rag_query_blocked_count += 1
                        logger.warning(
                            "RAG query blocked by length guard",
                            rag_query_chars=len(rag_query),
                            blocked_count=self.rag_query_blocked_count,
                        )
                    return ""

                if not chunks:
                    return ""

                relevant_chunks = [c for c in chunks if c.distance <= rag_distance_threshold]
                if not relevant_chunks:
                    return ""

                topic_hints = _infer_topic_hints(user_challenge, current_differential)
                if topic_hints:
                    hinted = []
                    for chunk in relevant_chunks:
                        topic = str(getattr(chunk, "topic", "") or "").lower()
                        if any(hint in topic for hint in topic_hints):
                            hinted.append(chunk)
                    if hinted:
                        relevant_chunks = hinted

                compact_chunks = _select_diverse_chunks(relevant_chunks, max_chunks=4)
                final_context = _trim_retrieved_context(self.retriever.format_retrieved_context(compact_chunks), max_chars=1800)
                _rag_cache_set(cache_key, final_context)
                return final_context
            except asyncio.TimeoutError:
                logger.warning("RAG retrieval timed out", timeout_seconds=timeout_seconds)
                return ""
            except Exception as e:
                if "maximum length" in str(e).lower():
                    self.rag_query_blocked_count += 1
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
                raw_citations = result.get("citations", [])
                citations = _normalize_citations(raw_citations)
                if raw_citations and not citations:
                    logger.warning(
                        "All orchestrator citations dropped after URL normalization",
                        raw_citations_count=len(raw_citations),
                    )
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
                content, _, _ = await _call_vllm_chat(
                    endpoint_name="debate-turn-fallback",
                    messages=messages,
                    max_tokens=1200,
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
                    retry_content, _, _ = await _call_vllm_chat(
                        endpoint_name="debate-turn-fallback-retry",
                        messages=correction_messages,
                        max_tokens=1024,
                        temperature=0.2,
                    )
                    data = extract_json(retry_content)

                diagnoses = _parse_differential(data.get("updated_differential", []))
                ai_response_text = data.get("ai_response", "")
                _, citations_raw = extract_citations(ai_response_text)
                citations = _normalize_citations(citations_raw)
                if citations_raw and not citations:
                    logger.warning(
                        "All fallback citations dropped after URL normalization",
                        raw_citations_count=len(citations_raw),
                    )

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
                "snapshot": {
                    "memory_enabled": ENABLE_MEMORY_SNAPSHOT,
                    "gpu_enabled": ENABLE_GPU_SNAPSHOT,
                },
                "rag_cache": {
                    "enabled": self.rag_cache_ttl_seconds > 0,
                    "ttl_seconds": self.rag_cache_ttl_seconds,
                    "max_entries": self.rag_cache_max_entries,
                    "entries": len(self.rag_query_cache),
                    "hits": self.rag_cache_hits,
                    "misses": self.rag_cache_misses,
                },
                "counters": {
                    "differential_concise_retry_count": self.differential_concise_retry_count,
                    "summary_concise_retry_count": self.summary_concise_retry_count,
                    "rag_query_blocked_count": self.rag_query_blocked_count,
                    "extract_labs_fast_path_count": self.extract_labs_fast_path_count,
                    "extract_labs_llm_fallback_count": self.extract_labs_llm_fallback_count,
                },
                "concurrency": {
                    "max_containers": MODAL_MAX_CONTAINERS,
                    "max_inputs": MODAL_MAX_INPUTS,
                    "target_inputs": MODAL_TARGET_INPUTS,
                },
            }

        @fastapi_app.get("/vllm-metrics")
        async def vllm_metrics():
            """Expose selected vLLM metrics for queue/latency debugging."""
            try:
                response = await self.vllm_client.get("/metrics")
                response.raise_for_status()
                metrics_text = response.text
                key_lines = []
                for line in metrics_text.splitlines():
                    if not line or line.startswith("#"):
                        continue
                    if (
                        "num_requests_waiting" in line
                        or "num_requests_running" in line
                        or "queue_time" in line
                        or "time_to_first_token" in line
                    ):
                        key_lines.append(line)

                return {
                    "status": "ok",
                    "key_metrics": key_lines[:40],
                    "metrics_excerpt_available": len(key_lines) > 0,
                }
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "detail": f"Failed to read vLLM metrics: {e}"},
                )

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
                    "query_cache": {
                        "enabled": self.rag_cache_ttl_seconds > 0,
                        "ttl_seconds": self.rag_cache_ttl_seconds,
                        "max_entries": self.rag_cache_max_entries,
                        "entries": len(self.rag_query_cache),
                        "hits": self.rag_cache_hits,
                        "misses": self.rag_cache_misses,
                    },
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
                content, _, _ = await _call_vllm_chat(
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
            raw_text_full = ""
            try:
                contents = await file.read()
                parse_start = time.time()
                if safe_filename.lower().endswith(".pdf"):
                    pdf_bytes = io.BytesIO(contents)
                    with pdfplumber.open(pdf_bytes) as pdf:
                        pages_text = []
                        pages_text_full = []
                        for page in pdf.pages:
                            tables = page.extract_tables()
                            if tables:
                                for table in tables:
                                    for row in table:
                                        cells = [str(cell).strip() for cell in row if cell]
                                        if cells:
                                            pages_text.append("  |  ".join(cells))
                                            pages_text_full.append("  |  ".join(cells))
                                pages_text.append("")
                                pages_text_full.append("")

                            page_text = page.extract_text()
                            if page_text:
                                pages_text_full.append(page_text)
                                if not tables:
                                    pages_text.append(page_text)
                        raw_text = "\n".join(pages_text).strip()
                        raw_text_full = "\n".join(pages_text_full).strip()
                else:
                    raw_text = contents.decode("utf-8", errors="replace").strip()
                    raw_text_full = raw_text

                raw_text = sanitize_lab_text(raw_text)
                raw_text_full = sanitize_lab_text(raw_text_full)

                if not raw_text and raw_text_full:
                    raw_text = raw_text_full

                if not raw_text:
                    return JSONResponse(
                        {"error": "Could not extract any text from the uploaded file"},
                        status_code=400,
                        headers=rate_limit_headers,
                    )

                compact_text = _compact_lab_report_text(raw_text)
                if not compact_text:
                    compact_text = raw_text[:2200]

                full_compact_text = _compact_lab_report_text(raw_text_full or raw_text, max_chars=9000, max_lines=320)
                if not full_compact_text:
                    full_compact_text = (raw_text_full or raw_text)[:9000]

                parse_duration_ms = round((time.time() - parse_start) * 1000, 2)
                logger.info(
                    "extract-labs-file text prepared",
                    parse_duration_ms=parse_duration_ms,
                    raw_chars=len(raw_text),
                    raw_full_chars=len(raw_text_full or raw_text),
                    compact_chars=len(compact_text),
                    full_compact_chars=len(full_compact_text),
                    filename=safe_filename,
                )

                deterministic_parsed = _select_best_deterministic_parse(
                    [
                        _parse_labs_from_table_text(compact_text, mode="table-fast"),
                        _parse_labs_from_table_text(raw_text_full or raw_text, mode="table-full"),
                        _parse_labs_from_flat_text(raw_text_full or raw_text, mode="flat-full"),
                    ]
                )
                if deterministic_parsed:
                    self.extract_labs_fast_path_count += 1
                    logger.info(
                        "extract-labs-file parsed via deterministic path",
                        parse_mode=deterministic_parsed.get("mode"),
                        parsed_count=len(deterministic_parsed["lab_values"]),
                        score_total=deterministic_parsed.get("score_total", 0),
                    )
                    response_data = ExtractLabsFileResponse(
                        lab_values=deterministic_parsed["lab_values"],
                        abnormal_values=deterministic_parsed["abnormal_values"],
                        raw_text=(raw_text_full or raw_text)[:5000],
                    )
                    logger.info(
                        "extract-labs-file completed",
                        duration_ms=round((time.time() - start_time) * 1000, 2),
                    )
                    return JSONResponse(response_data.model_dump(), headers=rate_limit_headers)

                self.extract_labs_llm_fallback_count += 1
                prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=full_compact_text)
                prompt += (
                    "\n\nIMPORTANT: Keep output compact. Include only labs explicitly present in the report. "
                    "Return JSON only."
                )
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]

                llm_start = time.time()
                content, _, _ = await _call_vllm_chat(
                    endpoint_name="extract-labs-file",
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.2,
                )

                try:
                    data = extract_json(content)
                except Exception:
                    logger.warning("extract-labs-file JSON parse failed on first attempt, retrying")
                    retry_content, _, _ = await _call_vllm_chat(
                        endpoint_name="extract-labs-file-retry",
                        messages=messages,
                        max_tokens=768,
                        temperature=0.2,
                    )
                    data = extract_json(retry_content)

                llm_duration_ms = round((time.time() - llm_start) * 1000, 2)
                logger.info(
                    "extract-labs-file model completed",
                    llm_duration_ms=llm_duration_ms,
                )

                response_data = ExtractLabsFileResponse(
                    lab_values=data.get("lab_values", {}),
                    abnormal_values=data.get("abnormal_values", []),
                    raw_text=(raw_text_full or raw_text)[:5000],
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

            compact_history = _truncate_text(patient_history, 2400)
            formatted_labs = _truncate_text(format_lab_values(request_model.lab_values), 1100)
            prompt = DIFFERENTIAL_PROMPT.format(
                patient_history=compact_history,
                formatted_lab_values=formatted_labs,
            )
            prompt += (
                "\n\nIMPORTANT: Keep output concise and structured. "
                "Return exactly 3 diagnoses. "
                "Max 2 supporting_evidence items per diagnosis. "
                "Max 1 against_evidence item per diagnosis. "
                "Max 2 suggested_tests per diagnosis. "
                "Each bullet under 16 words. Return JSON only."
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                content, _, finish_reason = await _call_vllm_chat(
                    endpoint_name="differential",
                    messages=messages,
                    max_tokens=1152,
                    temperature=0.25,
                )

                if finish_reason == "length" or _is_likely_truncated_json_response(content):
                    logger.warning("Differential output likely truncated; retrying with concise JSON constraints")
                    self.differential_concise_retry_count += 1
                    concise_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Keep output concise to fit token budget. "
                        + "Return exactly 3 diagnoses. Max 3 supporting_evidence items per diagnosis. "
                        + "Max 2 against_evidence items per diagnosis. Max 2 suggested_tests per diagnosis. "
                        + "Return JSON only."
                    )
                    concise_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": concise_prompt},
                    ]
                    content, _, _ = await _call_vllm_chat(
                        endpoint_name="differential-concise-retry",
                        messages=concise_messages,
                        max_tokens=896,
                        temperature=0.2,
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
                    retry_content, _, _ = await _call_vllm_chat(
                        endpoint_name="differential-retry",
                        messages=correction_messages,
                        max_tokens=896,
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
                if max(image.size) > 960:
                    image.thumbnail((960, 960))
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
            compact_triage = _compact_triage_summary(str(triage_result.get("triage_summary", "")))
            if modality == "uncertain":
                medgemma_prompt = """Analyze this medical image.

First identify the likely modality, then provide concise findings.

Output format:
1) Modality and image quality
2) Key visible findings (max 6 bullets)
3) Most likely clinical interpretation
4) Main differential considerations
5) Recommended follow-up

Keep each bullet under 18 words and avoid long prose."""
                system_prompt = (
                    "You are a medical imaging specialist experienced in radiology, dermatology, and pathology. "
                    "Analyze medical images with precision and concise, evidence-based findings."
                )
            else:
                medgemma_prompt = f"""Analyze this medical image.

Triage context:
{compact_triage}

Provide concise clinical interpretation:
1) Confirm modality and quality
2) Key findings (max 6 bullets)
3) Clinical significance
4) Differential considerations
5) Recommended follow-up

Keep each bullet under 18 words and avoid long prose."""
                system_prompt = (
                    "You are a specialist radiologist and medical imaging expert. "
                    "Analyze medical images with precision and concise, evidence-based findings."
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
                medgemma_analysis, used_max_tokens, _ = await _call_vllm_chat(
                    endpoint_name="analyze-image",
                    messages=messages,
                    max_tokens=512,
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
                    retry_analysis, _, _ = await _call_vllm_chat(
                        endpoint_name="analyze-image-retry",
                        messages=retry_messages,
                        max_tokens=320,
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

            patient_history = _truncate_text(sanitize_patient_history(request_model.patient_history), 2200)
            formatted_labs = _truncate_text(format_lab_values(request_model.lab_values), 1100)
            formatted_diff = _truncate_text(
                format_differential([d.model_dump() for d in request_model.final_differential]),
                1200,
            )
            compact_rounds = _compact_rounds_for_summary(request_model.debate_rounds)
            formatted_rounds = _truncate_text(format_rounds(compact_rounds), 2000)

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
                content, _, finish_reason = await _call_vllm_chat(
                    endpoint_name="summary",
                    messages=messages,
                    max_tokens=1664,
                    temperature=0.3,
                )

                if finish_reason == "length" or _is_likely_truncated_json_response(content):
                    logger.warning("Summary output likely truncated; retrying with concise JSON constraints")
                    self.summary_concise_retry_count += 1
                    concise_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Keep output compact. reasoning_chain max 5 items, "
                        + "ruled_out max 3 items, next_steps max 4 items. "
                        + "Each list item under 20 words. Return JSON only."
                    )
                    concise_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": concise_prompt},
                    ]
                    content, _, _ = await _call_vllm_chat(
                        endpoint_name="summary-concise-retry",
                        messages=concise_messages,
                        max_tokens=1280,
                        temperature=0.2,
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
