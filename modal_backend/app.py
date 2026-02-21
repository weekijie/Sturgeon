"""
Sturgeon AI Service - Modal Deployment (ASGI App)

Architecture:
- vLLM server (port 6501): OpenAI-compatible API for MedGemma
- MedSigLIP server (port 6502): Image triage (separate process)
- FastAPI app: Single ASGI app with all endpoints

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
    scaledown_window=300,
    memory=16384,
    cpu=4,
)
class SturgeonService:
    """Modal class hosting vLLM, MedSigLIP, and FastAPI ASGI app."""
    
    @modal.enter()
    def start_servers(self):
        """Start vLLM and MedSigLIP servers on container startup."""
        import subprocess
        import time
        import httpx
        import logging
        import os
        import sys
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
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
        from fastapi import FastAPI, HTTPException, UploadFile, File
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        import sys
        import uuid
        import base64
        import io
        from PIL import Image
        
        sys.path.insert(0, "/root")
        from prompts import SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT
        from prompts import DEBATE_TURN_PROMPT, DEBATE_TURN_PROMPT_WITH_RAG, SUMMARY_PROMPT
        from json_utils import extract_json
        from formatters import format_lab_values, format_differential, format_rounds
        from hallucination_check import validate_differential_response, validate_debate_response
        
        fastapi_app = FastAPI(
            title="Sturgeon AI Service",
            description="Medical diagnostic debate API",
            version="0.4.0",
        )
        
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @fastapi_app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "vllm": "running",
                "medsiglip": "running",
                "gemini_orchestrator": self.gemini_available,
                "rag_retriever": self.rag_available,
            }
        
        @fastapi_app.post("/extract-labs")
        async def extract_labs(request: dict):
            lab_report_text = request.get("lab_report_text", "")
            if not lab_report_text.strip():
                return {"error": "lab_report_text is required"}
            
            prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=lab_report_text)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.vllm_client.post(
                "/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.3,
                }
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            try:
                data = extract_json(content)
                return {
                    "lab_values": data.get("lab_values", {}),
                    "abnormal_values": data.get("abnormal_values", [])
                }
            except Exception as e:
                return {"error": f"JSON parse error: {str(e)}", "raw": content}
        
        @fastapi_app.post("/differential")
        async def differential(request: dict):
            patient_history = request.get("patient_history", "")
            lab_values = request.get("lab_values", {})
            
            if not patient_history.strip():
                return {"error": "patient_history is required"}
            
            formatted_labs = format_lab_values(lab_values)
            prompt = DIFFERENTIAL_PROMPT.format(
                patient_history=patient_history,
                formatted_lab_values=formatted_labs
            )
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.vllm_client.post(
                "/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.3,
                }
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            try:
                data = extract_json(content)
                
                validation = validate_differential_response(data, lab_values, patient_history)
                if validation["has_hallucination"]:
                    self.logger.warning(f"Hallucination detected: {validation['warnings']}")
                
                diagnoses = []
                for dx in data.get("diagnoses", []):
                    diagnoses.append({
                        "name": dx.get("name", "Unknown"),
                        "probability": dx.get("probability", "medium"),
                        "supporting_evidence": dx.get("supporting_evidence", []),
                        "against_evidence": dx.get("against_evidence", []),
                        "suggested_tests": dx.get("suggested_tests", [])
                    })
                
                return {"diagnoses": diagnoses}
            except Exception as e:
                return {"error": f"Processing error: {str(e)}", "raw": content[:500]}
        
        @fastapi_app.post("/debate-turn")
        async def debate_turn(request: dict):
            patient_history = request.get("patient_history", "")
            lab_values = request.get("lab_values", {})
            current_differential = request.get("current_differential", [])
            previous_rounds = request.get("previous_rounds", [])
            user_challenge = request.get("user_challenge", "")
            session_id = request.get("session_id")
            image_context = request.get("image_context", "")
            
            if not user_challenge.strip():
                return {"error": "user_challenge is required"}
            
            retrieved_context = ""
            if self.rag_available:
                try:
                    dx_names = [d.get("name", "") for d in current_differential[:3]]
                    rag_query = f"{user_challenge} | Context: {', '.join(dx_names)}" if dx_names else user_challenge
                    chunks, _ = self.retriever.retrieve(rag_query, ip_address="internal")
                    if chunks:
                        retrieved_context = self.retriever.format_retrieved_context(chunks)
                except Exception as e:
                    self.logger.warning(f"RAG retrieval failed: {e}")
            
            formatted_labs = format_lab_values(lab_values)
            formatted_diff = format_differential(current_differential)
            formatted_rounds = format_rounds(previous_rounds)
            
            if retrieved_context:
                prompt = DEBATE_TURN_PROMPT_WITH_RAG.format(
                    patient_history=patient_history,
                    formatted_lab_values=formatted_labs,
                    current_differential=formatted_diff,
                    previous_rounds=formatted_rounds,
                    user_challenge=user_challenge,
                    image_context=image_context or "No image evidence available",
                    retrieved_guidelines=retrieved_context,
                )
            else:
                prompt = DEBATE_TURN_PROMPT.format(
                    patient_history=patient_history,
                    formatted_lab_values=formatted_labs,
                    current_differential=formatted_diff,
                    previous_rounds=formatted_rounds,
                    user_challenge=user_challenge,
                    image_context=image_context or "No image evidence available",
                )
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.vllm_client.post(
                "/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.7,
                }
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            try:
                data = extract_json(content)
                
                validation = validate_debate_response(data, lab_values, patient_history)
                if validation["has_hallucination"]:
                    self.logger.warning(f"Hallucination detected: {validation['warnings']}")
                
                diagnoses = []
                for dx in data.get("updated_differential", []):
                    diagnoses.append({
                        "name": dx.get("name") or dx.get("diagnosis", "Unknown"),
                        "probability": dx.get("probability", "medium"),
                        "supporting_evidence": dx.get("supporting_evidence", []),
                        "against_evidence": dx.get("against_evidence", []),
                        "suggested_tests": dx.get("suggested_tests", [])
                    })
                
                return {
                    "ai_response": data.get("ai_response", ""),
                    "updated_differential": diagnoses if diagnoses else current_differential,
                    "suggested_test": data.get("suggested_test"),
                    "session_id": session_id or str(uuid.uuid4()),
                    "orchestrated": False,
                    "citations": [],
                    "has_guidelines": bool(retrieved_context),
                }
            except Exception as e:
                return {"error": f"Processing error: {str(e)}", "raw": content[:500]}
        
        @fastapi_app.post("/analyze-image")
        async def analyze_image(file: UploadFile = File(...)):
            allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp"}
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported image type: {file.content_type}"
                )
            
            try:
                contents = await file.read()
                image = Image.open(io.BytesIO(contents)).convert("RGB")
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
                    files={"file": (file.filename or "image.png", contents, file.content_type or "image/png")}
                )
                if triage_response.status_code == 200:
                    triage_result = triage_response.json()
            except Exception as e:
                self.logger.warning(f"MedSigLIP triage failed: {e}")
            
            medgemma_prompt = f"""Analyze this medical image in detail.

{triage_result.get('triage_summary', '')}

Provide a thorough clinical interpretation including:
1. **Image type and quality**: What type of medical image is this?
2. **Key findings**: Describe all significant findings.
3. **Clinical significance**: What do these findings suggest?
4. **Differential considerations**: What conditions should be considered?
5. **Recommended follow-up**: What additional tests would help?"""
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                        {"type": "text", "text": medgemma_prompt}
                    ]
                }
            ]
            
            response = await self.vllm_client.post(
                "/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.1,
                }
            )
            
            result = response.json()
            medgemma_analysis = result["choices"][0]["message"]["content"]
            
            return {
                "image_type": triage_result.get("image_type", "medical image"),
                "image_type_confidence": triage_result.get("image_type_confidence", 0.0),
                "modality": triage_result.get("modality", "unknown"),
                "triage_findings": triage_result.get("findings", []),
                "triage_summary": triage_result.get("triage_summary", ""),
                "medgemma_analysis": medgemma_analysis,
            }
        
        @fastapi_app.post("/summary")
        async def summary(request: dict):
            patient_history = request.get("patient_history", "")
            lab_values = request.get("lab_values", {})
            final_differential = request.get("final_differential", [])
            debate_rounds = request.get("debate_rounds", [])
            
            formatted_labs = format_lab_values(lab_values)
            formatted_diff = format_differential(final_differential)
            formatted_rounds = format_rounds(debate_rounds)
            
            prompt = SUMMARY_PROMPT.format(
                patient_history=patient_history,
                formatted_lab_values=formatted_labs,
                final_differential=formatted_diff,
                debate_rounds=formatted_rounds
            )
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.vllm_client.post(
                "/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.3,
                }
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            try:
                data = extract_json(content)
                
                ruled_out_raw = data.get("ruled_out", [])
                ruled_out = []
                for item in ruled_out_raw:
                    if isinstance(item, str):
                        ruled_out.append(item)
                    elif isinstance(item, dict):
                        ruled_out.append(item.get("diagnosis", item.get("name", str(item))))
                
                return {
                    "final_diagnosis": data.get("final_diagnosis", "Unable to determine"),
                    "confidence": data.get("confidence", "low"),
                    "confidence_percent": data.get("confidence_percent"),
                    "reasoning_chain": data.get("reasoning_chain", []),
                    "ruled_out": ruled_out,
                    "next_steps": data.get("next_steps", [])
                }
            except Exception as e:
                return {"error": f"Processing error: {str(e)}", "raw": content[:500]}
        
        return fastapi_app


@app.local_entrypoint()
def main():
    """Test the deployment locally."""
    import httpx
    
    print("Testing Sturgeon Modal deployment...")
    print("\nAfter deployment, your single URL will be:")
    print("https://weekijie--sturgeon-medgemma.modal.run")
    print("\nEndpoints:")
    print("  GET  /health")
    print("  POST /extract-labs")
    print("  POST /differential")
    print("  POST /debate-turn")
    print("  POST /analyze-image")
    print("  POST /summary")
