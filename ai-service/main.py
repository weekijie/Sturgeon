"""
Sturgeon AI Service - FastAPI Backend
Gemini-orchestrated, MedGemma-powered diagnostic reasoning

Architecture:
  - Gemini (Pro/Flash) = Orchestrator for multi-turn debate management
  - MedGemma 4B-it = Medical specialist (callable tool)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from PIL import Image
import asyncio
import logging
import time
import os
import uuid
import io

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Imports - handle both package-style and direct invocation
# When run as: python -m uvicorn "ai-service.main:app" → relative imports fail
# because "ai-service" has a hyphen. Use try/except to handle both cases.
try:
    from medgemma import get_model
    from medsiglip import get_siglip
    from gemini_orchestrator import get_orchestrator, ClinicalState, extract_citations
    from prompts import (SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT,
                         DEBATE_TURN_PROMPT, DEBATE_TURN_PROMPT_WITH_RAG, SUMMARY_PROMPT)
    from models import (ExtractLabsRequest, ExtractLabsResponse, ExtractLabsFileResponse,
                        DifferentialRequest, Diagnosis, DifferentialResponse,
                        DebateTurnRequest, DebateTurnResponse,
                        SummaryRequest, SummaryResponse,
                        ImageFinding, ImageAnalysisResponse)
    from json_utils import extract_json
    from refusal import is_pure_refusal, strip_refusal_preamble
    from formatters import format_lab_values, format_differential, format_rounds
    from rag_retriever import get_retriever, GuidelineRetriever, RetrievedChunk
    from hallucination_check import validate_differential_response, validate_debate_response
    from rate_limiter import check_rate_limit
    from rag_evaluation import get_evaluator, RetrievedContext
except ImportError:
    from .medgemma import get_model
    from .medsiglip import get_siglip
    from .gemini_orchestrator import get_orchestrator, ClinicalState, extract_citations
    from .prompts import (SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT,
                          DEBATE_TURN_PROMPT, DEBATE_TURN_PROMPT_WITH_RAG, SUMMARY_PROMPT)
    from .models import (ExtractLabsRequest, ExtractLabsResponse, ExtractLabsFileResponse,
                         DifferentialRequest, Diagnosis, DifferentialResponse,
                         DebateTurnRequest, DebateTurnResponse,
                         SummaryRequest, SummaryResponse,
                         ImageFinding, ImageAnalysisResponse)
    from .json_utils import extract_json
    from .refusal import is_pure_refusal, strip_refusal_preamble
    from .formatters import format_lab_values, format_differential, format_rounds
    from .rag_retriever import get_retriever, GuidelineRetriever, RetrievedChunk
    from .hallucination_check import validate_differential_response, validate_debate_response
    from .rate_limiter import check_rate_limit
    from .rag_evaluation import get_evaluator, RetrievedContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory session store for clinical states
# Maps session_id -> ClinicalState
_sessions: dict[str, ClinicalState] = {}
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "500"))

# Flags: which optional services are available?
_gemini_available = False
_siglip_available = False
_rag_available = False


# Model lifecycle - load on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load MedGemma model, MedSigLIP triage, and Gemini orchestrator on startup."""
    global _gemini_available, _siglip_available
    
    logger.info("Starting Sturgeon AI Service...")
    
    # Load MedGemma (required)
    model = get_model()
    model.load()
    logger.info("MedGemma loaded.")
    
    # Load MedSigLIP for image triage (optional - graceful fallback)
    if os.getenv("DISABLE_MEDSIGLIP"):
        logger.info("MedSigLIP disabled via environment variable.")
        _siglip_available = False
    else:
        try:
            siglip = get_siglip()
            siglip.load()
            _siglip_available = True
            logger.info("MedSigLIP loaded. Image triage enabled.")
        except Exception as e:
            logger.warning(f"MedSigLIP not available: {e}")
            logger.warning("Image triage will be skipped; MedGemma will still analyze images directly.")
            _siglip_available = False
    
    # Initialize Gemini orchestrator (optional - graceful fallback)
    orchestrator = get_orchestrator()
    orchestrator.medgemma = model
    try:
        orchestrator.initialize()
        _gemini_available = True
        logger.info("Gemini orchestrator initialized. Agentic mode enabled.")
    except RuntimeError as e:
        logger.warning(f"Gemini orchestrator not available: {e}")
        logger.warning("Falling back to MedGemma-only mode for debate turns.")
        _gemini_available = False
    
    # Initialize RAG retriever (optional - graceful fallback)
    global _rag_available
    try:
        retriever = get_retriever(guidelines_dir=os.path.join(os.path.dirname(__file__), "guidelines"))
        if retriever.initialize():
            _rag_available = True
            logger.info(f"RAG retriever initialized. {retriever.indexing_stats['num_chunks']} guideline chunks indexed.")
        else:
            logger.warning("RAG retriever initialization failed. Continuing without vector retrieval.")
            _rag_available = False
    except Exception as e:
        logger.warning(f"RAG retriever not available: {e}")
        _rag_available = False
    
    logger.info("Ready to serve requests.")
    yield
    logger.info("Shutting down...")
    if _rag_available:
        try:
            retriever = get_retriever()
            retriever.close()
            logger.info("RAG retriever closed.")
        except Exception as e:
            logger.warning(f"Failed to close RAG retriever: {e}")


app = FastAPI(
    title="Sturgeon AI Service",
    description="Gemini-orchestrated, MedGemma-powered diagnostic debate API",
    version="0.3.0",
    lifespan=lifespan
)

# CORS for Next.js frontend
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    model = get_model()
    return {
        "status": "healthy",
        "model_loaded": model.model is not None,
        "medsiglip_loaded": _siglip_available,
        "gemini_orchestrator": _gemini_available,
        "rag_retriever": _rag_available,
        "mode": "agentic" if _gemini_available else "medgemma-only",
        "image_triage": "medsiglip+medgemma" if _siglip_available else "medgemma-only",
        "guideline_retrieval": "vector-rag" if _rag_available else "prompt-only",
        "active_sessions": len(_sessions),
    }


@app.get("/rag-status")
async def rag_status():
    """Get RAG retriever status and statistics."""
    if not _rag_available:
        return {
            "available": False,
            "message": "RAG retriever not initialized. Check if chromadb and sentence-transformers are installed."
        }
    
    try:
        retriever = get_retriever()
        status = retriever.get_status()
        return {
            "available": True,
            **status
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e)
        }


@app.post("/rag-evaluate")
async def rag_evaluate(request: dict, req: Request):
    """
    Evaluate RAG response quality using LLM-as-a-Judge (Gemini).
    
    Internal endpoint for development/debugging - not for production use.
    
    Request body:
    {
        "question": "Clinical question asked",
        "response": "AI response to evaluate",
        "retrieved_contexts": [
            {"content": "...", "source": "...", "topic": "...", "distance": 0.5}
        ]
    }
    
    Returns evaluation scores (faithfulness, relevance, comprehensiveness).
    """
    if not os.getenv("ENABLE_RAG_EVAL"):
        raise HTTPException(status_code=404, detail="Not found")

    question = request.get("question", "")
    response = request.get("response", "")
    contexts_data = request.get("retrieved_contexts", [])
    
    if not question or not response:
        raise HTTPException(status_code=400, detail="question and response are required")
    
    # Convert to RetrievedContext objects
    contexts = [
        RetrievedContext(
            content=c.get("content", ""),
            source=c.get("source", "Unknown"),
            topic=c.get("topic", "general"),
            distance=c.get("distance", 0.0)
        )
        for c in contexts_data
    ]
    
    try:
        evaluator = get_evaluator()
        result = evaluator.evaluate_response(question, response, contexts)
        return result.to_dict()
    except Exception as e:
        logger.error(f"RAG evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@app.post("/extract-labs", response_model=ExtractLabsResponse)
async def extract_labs(request: ExtractLabsRequest, req: Request):
    """Extract structured lab values from text."""
    # Check rate limit
    rate_limit_headers = check_rate_limit("extract-labs", req)
    
    logger.info(f"Extracting labs from text ({len(request.lab_report_text)} chars)")
    
    try:
        t0 = time.time()
        model = get_model()
        prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=request.lab_report_text)
        
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=1024, temperature=0.3)
        t1 = time.time()
        logger.info(f"[extract-labs] medgemma={t1-t0:.2f}s")
        
        data = extract_json(response)
        
        # Return response with rate limit headers
        response_data = ExtractLabsResponse(
            lab_values=data.get("lab_values", {}),
            abnormal_values=data.get("abnormal_values", [])
        )
        
        # Add rate limit headers to response
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=response_data.model_dump(),
            headers=rate_limit_headers
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lab extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lab extraction error: {str(e)[:200]}")


@app.post("/extract-labs-file", response_model=ExtractLabsFileResponse)
async def extract_labs_file(req: Request, file: UploadFile = FastAPIFile(...)):
    """Extract structured lab values from an uploaded PDF or text file.
    
    Workflow:
    1. Read uploaded file (PDF → pdfplumber, TXT → direct read)
    2. Extract raw text (including tables for PDFs)
    3. Send to MedGemma via EXTRACT_LABS_PROMPT for structured parsing
    4. Return structured lab values + abnormal flags + raw text
    """
    # Check rate limit
    rate_limit_headers = check_rate_limit("extract-labs-file", req)
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    filename = file.filename.lower()
    raw_text = ""
    
    try:
        t0 = time.time()
        contents = await file.read()
        
        if filename.endswith(".pdf"):
            # Extract text from PDF using pdfplumber (handles tables well)
            import pdfplumber
            
            pdf_bytes = io.BytesIO(contents)
            with pdfplumber.open(pdf_bytes) as pdf:
                pages_text = []
                for page in pdf.pages:
                    # Extract tables first (better for lab reports)
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                # Filter None values and join
                                cells = [str(c).strip() for c in row if c]
                                if cells:
                                    pages_text.append("  |  ".join(cells))
                        pages_text.append("")  # Blank line between tables
                    
                    # Also extract regular text (for notes, headers, etc.)
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                
                raw_text = "\n".join(pages_text).strip()
        
        elif filename.endswith(".txt"):
            # Direct text read
            raw_text = contents.decode("utf-8", errors="replace").strip()
        
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {filename}. Accepted: .pdf, .txt"
            )
        
        if not raw_text:
            raise HTTPException(
                status_code=400,
                detail="Could not extract any text from the uploaded file"
            )
        
        t1 = time.time()
        logger.info(f"[extract-labs-file] text_extraction={t1-t0:.2f}s ({len(raw_text)} chars from {filename})")
        
        # Send extracted text to MedGemma for structured lab parsing
        model = get_model()
        prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=raw_text)
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048, temperature=0.3)
        
        t2 = time.time()
        logger.info(f"[extract-labs-file] medgemma={t2-t1:.2f}s total={t2-t0:.2f}s")
        
        # Try parsing; if JSON extraction fails, retry once (MedGemma can be
        # inconsistent with long inputs on first attempt)
        try:
            data = extract_json(response)
        except HTTPException:
            logger.warning("Lab extraction JSON parse failed on first attempt, retrying...")
            response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048, temperature=0.3)
            data = extract_json(response)
        
        # Return response with rate limit headers
        response_data = ExtractLabsFileResponse(
            lab_values=data.get("lab_values", {}),
            abnormal_values=data.get("abnormal_values", []),
            raw_text=raw_text[:5000]  # Cap at 5k chars for response size
        )
        
        # Add rate limit headers to response
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=response_data.model_dump(),
            headers=rate_limit_headers
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lab extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract lab values: {str(e)[:200]}"
        )


@app.post("/differential", response_model=DifferentialResponse)
async def generate_differential(request: DifferentialRequest, req: Request):
    """Generate initial differential diagnoses with hallucination validation."""
    # Check rate limit
    rate_limit_headers = check_rate_limit("differential", req)
    
    logger.info("Generating differential for patient history")
    
    try:
        t0 = time.time()
        model = get_model()
        formatted_labs = format_lab_values(request.lab_values)
        prompt = DIFFERENTIAL_PROMPT.format(
            patient_history=request.patient_history,
            formatted_lab_values=formatted_labs
        )
        
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=3072, temperature=0.3)
        t1 = time.time()
        logger.info(f"[differential] medgemma={t1-t0:.2f}s")
        
        data = extract_json(response)
        
        # Validate for hallucinations
        validation = validate_differential_response(
            data,
            request.lab_values,
            request.patient_history
        )
        
        if validation["has_hallucination"]:
            logger.warning(f"[differential] Hallucination detected: {validation['warnings']}")
            
            # Re-prompt with explicit correction instruction
            correction_prompt = f"""{prompt}

IMPORTANT CORRECTION: Your previous response contained fabricated lab values that were NOT provided by the user.
The following values were hallucinated and must NOT be included:
{chr(10).join(f'- {w}' for w in validation['warnings'])}

ONLY use data explicitly provided in the Patient History and Lab Values sections above.
If a lab value is not provided, do NOT invent one.

JSON Response:"""
            
            logger.info("[differential] Re-prompting with correction constraints...")
            response = model.generate(correction_prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=3072, temperature=0.2)
            t2 = time.time()
            logger.info(f"[differential] retry_medgemma={t2-t1:.2f}s")
            
            data = extract_json(response)
            
            # Re-validate the corrected response
            validation2 = validate_differential_response(
                data,
                request.lab_values,
                request.patient_history
            )
            if validation2["has_hallucination"]:
                logger.warning(f"[differential] Hallucination still present after retry: {validation2['warnings']}")
        
        diagnoses = []
        for dx in data.get("diagnoses", []):
            diagnoses.append(Diagnosis(
                name=dx.get("name", "Unknown"),
                probability=dx.get("probability", "medium"),
                supporting_evidence=dx.get("supporting_evidence", []),
                against_evidence=dx.get("against_evidence", []),
                suggested_tests=dx.get("suggested_tests", [])
            ))
        
        t_final = time.time()
        logger.info(f"[differential] total={t_final-t0:.2f}s diagnoses={len(diagnoses)}")
        
        # Return response with rate limit headers
        response_data = DifferentialResponse(diagnoses=diagnoses)
        
        # Add rate limit headers to response
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=response_data.model_dump(),
            headers=rate_limit_headers
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Differential generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Differential generation error: {str(e)[:200]}")


@app.post("/debate-turn", response_model=DebateTurnResponse)
async def debate_turn(request: DebateTurnRequest, req: Request):
    """Handle a debate round - orchestrated by Gemini, powered by MedGemma."""
    # Check rate limit
    rate_limit_headers = check_rate_limit("debate-turn", req)
    
    logger.info(f"Processing debate turn: {request.user_challenge[:50]}...")
    
    if _gemini_available:
        result = await _debate_turn_orchestrated(request)
    else:
        result = await _debate_turn_medgemma_only(request)
    
    # Add rate limit headers to response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=result.model_dump(),
        headers=rate_limit_headers
    )


async def _debate_turn_orchestrated(request: DebateTurnRequest) -> DebateTurnResponse:
    """Orchestrated debate turn: Gemini manages conversation, MedGemma provides
    medical reasoning."""
    orchestrator = get_orchestrator()
    
    # Start RAG retrieval in parallel with session setup
    rag_task = None
    if _rag_available:
        # Distance threshold: ChromaDB returns L2 distance; lower = more relevant
        # 1.3 filters out marginally relevant chunks (e.g., pneumonia docs for headache case)
        RAG_DISTANCE_THRESHOLD = 1.3
        
        async def fetch_rag_context():
            try:
                retriever = get_retriever()
                # Enrich query with clinical context from differential
                # Raw user challenge alone often lacks clinical signal
                # (e.g., "summarize key findings" → retrieves colorectal cancer)
                dx_names = [d.name for d in request.current_differential[:3]]
                rag_query = f"{request.user_challenge} | Clinical context: {', '.join(dx_names)}" if dx_names else request.user_challenge
                chunks, rag_error = await asyncio.to_thread(
                    retriever.retrieve,
                    query=rag_query,
                    ip_address="internal",
                )
                if rag_error:
                    logger.warning(f"[RAG] Retrieval error: {rag_error}")
                    return ""
                elif chunks:
                    # Filter by distance threshold — only keep semantically relevant chunks
                    relevant_chunks = [c for c in chunks if c.distance <= RAG_DISTANCE_THRESHOLD]
                    if relevant_chunks:
                        logger.info(f"[RAG] {len(relevant_chunks)}/{len(chunks)} chunks passed distance threshold ({RAG_DISTANCE_THRESHOLD})")
                        for c in relevant_chunks:
                            logger.info(f"[RAG]   {c.organization}/{c.topic} (distance={c.distance:.3f})")
                        return retriever.format_retrieved_context(relevant_chunks)
                    else:
                        logger.info(f"[RAG] All {len(chunks)} chunks below relevance threshold (closest: {chunks[0].distance:.3f})")
                        return ""
                return ""
            except Exception as e:
                logger.warning(f"[RAG] Retrieval failed: {e}")
                return ""
        
        rag_task = asyncio.create_task(fetch_rag_context())
    
    # Get or create session (happens in parallel with RAG)
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            oldest_session = next(iter(_sessions))
            _sessions.pop(oldest_session, None)
            logger.info(f"Evicted oldest session: {oldest_session}")
        _sessions[session_id] = ClinicalState(
            patient_history=request.patient_history,
            lab_values=request.lab_values,
            differential=[d.model_dump() for d in request.current_differential],
            image_context=request.image_context or "",
        )
        logger.info(f"Created new session: {session_id}")
    
    clinical_state = _sessions[session_id]
    
    # Keep differential in sync with frontend state
    clinical_state.differential = [d.model_dump() for d in request.current_differential]
    
    # Wait for RAG retrieval to complete (with timeout)
    retrieved_context = ""
    if rag_task:
        try:
            t_rag_start = time.time()
            retrieved_context = await asyncio.wait_for(rag_task, timeout=5.0)
            t_rag_end = time.time()
            logger.info(f"[RAG] Retrieved context in {t_rag_end-t_rag_start:.2f}s")
        except asyncio.TimeoutError:
            logger.warning("[RAG] Retrieval timed out after 5s, proceeding without guidelines")
            retrieved_context = ""
    
    try:
        t0 = time.time()
        # Run synchronous orchestrator call in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(
            orchestrator.process_debate_turn,
            user_challenge=request.user_challenge,
            clinical_state=clinical_state,
            previous_rounds=request.previous_rounds if request.previous_rounds else [],
            retrieved_context=retrieved_context,  # Pass RAG context
        )
        t1 = time.time()
        logger.info(f"[debate-turn] orchestrated total={t1-t0:.2f}s")
        
        # Parse updated differential with robust field name handling
        diagnoses = _parse_differential(result.get("updated_differential", []))
        
        # Debug logging for RAG
        citations = result.get("citations", [])
        has_guidelines = result.get("has_guidelines", False)
        logger.info(f"[RAG orchestrated] Response has {len(citations)} citations, has_guidelines={has_guidelines}")
        
        return DebateTurnResponse(
            ai_response=result.get("ai_response", "I need more information to respond."),
            updated_differential=diagnoses if diagnoses else request.current_differential,
            suggested_test=result.get("suggested_test"),
            session_id=session_id,
            orchestrated=True,
            citations=citations,
            has_guidelines=has_guidelines,
        )
    except Exception as e:
        logger.error(f"Orchestrator error: {e}. Falling back to MedGemma-only.")
        return await _debate_turn_medgemma_only(request)


async def _debate_turn_medgemma_only(request: DebateTurnRequest) -> DebateTurnResponse:
    """Fallback: MedGemma-only debate turn (original implementation)."""
    try:
        t0 = time.time()
        model = get_model()
        
        # Start RAG retrieval in parallel with prompt formatting
        rag_task = None
        RAG_DISTANCE_THRESHOLD = 1.3  # Same threshold as orchestrated path
        if _rag_available:
            async def fetch_rag_context():
                try:
                    retriever = get_retriever()
                    # Enrich query with clinical context from differential
                    dx_names = [d.name for d in request.current_differential[:3]]
                    rag_query = f"{request.user_challenge} | Clinical context: {', '.join(dx_names)}" if dx_names else request.user_challenge
                    chunks, rag_error = await asyncio.to_thread(
                        retriever.retrieve,
                        query=rag_query,
                        ip_address="internal",
                    )
                    if not rag_error and chunks:
                        # Filter by distance threshold — same as orchestrated path
                        relevant_chunks = [c for c in chunks if c.distance <= RAG_DISTANCE_THRESHOLD]
                        if relevant_chunks:
                            logger.info(f"[RAG fallback] {len(relevant_chunks)}/{len(chunks)} chunks passed threshold")
                            return retriever.format_retrieved_context(relevant_chunks)
                        else:
                            logger.info(f"[RAG fallback] All chunks below relevance threshold (closest: {chunks[0].distance:.3f})")
                            return ""
                    return ""
                except Exception as e:
                    logger.warning(f"[RAG fallback] Retrieval failed: {e}")
                    return ""
            
            rag_task = asyncio.create_task(fetch_rag_context())
        
        # Format prompts in parallel with RAG
        formatted_labs = format_lab_values(request.lab_values)
        formatted_diff = format_differential([d.model_dump() for d in request.current_differential])
        formatted_rounds = format_rounds(request.previous_rounds)
        image_context = request.image_context or "No image evidence available"
        
        # Wait for RAG retrieval
        retrieved_guidelines = ""
        if rag_task:
            try:
                t_rag_start = time.time()
                retrieved_guidelines = await asyncio.wait_for(rag_task, timeout=5.0)
                t_rag_end = time.time()
                logger.info(f"[RAG fallback] Retrieved context in {t_rag_end-t_rag_start:.2f}s")
            except asyncio.TimeoutError:
                logger.warning("[RAG fallback] Retrieval timed out after 5s")
                retrieved_guidelines = ""
        
        # DEBATE_TURN_PROMPT_WITH_RAG is imported at module level
        
        # Use RAG-enhanced prompt if available, otherwise standard prompt
        if retrieved_guidelines:
            prompt = DEBATE_TURN_PROMPT_WITH_RAG.format(
                patient_history=request.patient_history,
                formatted_lab_values=formatted_labs,
                current_differential=formatted_diff,
                previous_rounds=formatted_rounds,
                user_challenge=request.user_challenge,
                image_context=image_context,
                retrieved_guidelines=retrieved_guidelines,
            )
        else:
            prompt = DEBATE_TURN_PROMPT.format(
                patient_history=request.patient_history,
                formatted_lab_values=formatted_labs,
                current_differential=formatted_diff,
                previous_rounds=formatted_rounds,
                user_challenge=request.user_challenge,
                image_context=image_context,
            )
        
        # Run blocking MedGemma inference in a thread
        response = await asyncio.to_thread(
            model.generate, prompt,
            max_new_tokens=2048,
            system_prompt=SYSTEM_PROMPT,
        )
        t1 = time.time()
        logger.info(f"[debate-turn] medgemma_only={t1-t0:.2f}s")
        
        data = extract_json(response)
        
        # Validate for hallucinations
        validation = validate_debate_response(
            data,
            request.lab_values,
            request.patient_history
        )
        
        if validation["has_hallucination"]:
            logger.warning(f"[debate-turn fallback] Hallucination detected: {validation['warnings']}")
            
            # Re-prompt with correction
            correction_instruction = f"""

IMPORTANT: Your previous response contained fabricated lab values NOT provided by the user.
Only use data from the Patient History and Lab Values sections above.
If a lab value was not provided, do NOT invent one.

Return corrected JSON:"""
            
            correction_prompt = prompt + correction_instruction
            logger.info("[debate-turn fallback] Re-prompting with correction...")
            response = await asyncio.to_thread(
                model.generate, correction_prompt,
                max_new_tokens=2048,
                system_prompt=SYSTEM_PROMPT,
            )
            data = extract_json(response)
        
        # Parse updated differential with robust field name handling
        diagnoses = _parse_differential(data.get("updated_differential", []))
        
        # RAG: Extract citations from response (fallback mode)
        ai_response_text = data.get("ai_response", "")
        # extract_citations is imported at module level
        _, citations = extract_citations(ai_response_text)
        
        logger.info(f"[RAG fallback] Extracted {len(citations)} citations")
        if citations:
            for c in citations:
                logger.info(f"[RAG fallback] Citation: {c['text']}")
        
        return DebateTurnResponse(
            ai_response=ai_response_text,
            updated_differential=diagnoses if diagnoses else request.current_differential,
            suggested_test=data.get("suggested_test"),
            orchestrated=False,
            citations=citations,
            has_guidelines=len(citations) > 0,
        )
    except Exception as e:
        logger.error(f"MedGemma-only debate turn failed: {e}")
        # Return a graceful response instead of HTTP 500
        return DebateTurnResponse(
            ai_response=f"I encountered a processing error, but here's what I can say: {str(e)[:200]}. Please try rephrasing your challenge.",
            updated_differential=request.current_differential,
            suggested_test=None,
            orchestrated=False,
        )


def _parse_differential(updated_diff: list) -> list[Diagnosis]:
    """Parse differential list with robust field name handling for both
    MedGemma and Gemini responses."""
    diagnoses = []
    for dx in updated_diff:
        if isinstance(dx, dict):
            # Handle various field name variations
            name = dx.get("name") or dx.get("diagnosis") or dx.get("diagnosis_name") or "Unknown"
            prob = dx.get("probability") or dx.get("likelihood") or "medium"
            support = dx.get("supporting_evidence") or dx.get("supporting") or dx.get("evidence_for") or []
            against = dx.get("against_evidence") or dx.get("against") or dx.get("evidence_against") or []
            tests = dx.get("suggested_tests") or dx.get("tests") or dx.get("workup") or []
            
            diagnoses.append(Diagnosis(
                name=name,
                probability=prob if prob in ["high", "medium", "low"] else "medium",
                supporting_evidence=support if isinstance(support, list) else [support],
                against_evidence=against if isinstance(against, list) else [against],
                suggested_tests=tests if isinstance(tests, list) else [tests]
            ))
    return diagnoses


@app.post("/analyze-image", response_model=ImageAnalysisResponse)
async def analyze_image(req: Request, file: UploadFile = FastAPIFile(...)):
    """Analyze a medical image using MedSigLIP triage + MedGemma deep analysis.
    
    Pipeline:
    1. MedSigLIP: Fast zero-shot classification (~100ms) — identifies image type
       and preliminary findings with confidence scores
    2. MedGemma: Deep clinical interpretation — receives the image + MedSigLIP
       triage summary as context for focused analysis
    """
    # Check rate limit
    rate_limit_headers = check_rate_limit("analyze-image", req)
    
    logger.info(f"Analyzing image: {file.filename} ({file.content_type})")
    
    # Validate file type
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}. "
                   f"Supported: {', '.join(allowed_types)}"
        )
    
    # Read and open image
    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        logger.info(f"Image loaded: {image.size[0]}x{image.size[1]}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {e}")
    
    t0 = time.time()
    
    # Step 1: MedSigLIP triage (fast zero-shot classification)
    triage_summary = ""
    triage_result = {
        "image_type": "medical image",
        "image_type_confidence": 0.0,
        "modality": "unknown",
        "findings": [],
        "triage_summary": "MedSigLIP not available; proceeding with MedGemma direct analysis.",
    }
    
    if _siglip_available:
        try:
            siglip = get_siglip()
            triage_result = siglip.analyze_findings(image)
            triage_summary = triage_result["triage_summary"]
            t1 = time.time()
            logger.info(
                f"[analyze-image] medsiglip={t1-t0:.2f}s "
                f"type={triage_result['image_type']} "
                f"conf={triage_result['image_type_confidence']:.1%} "
                f"modality={triage_result['modality']}"
            )
        except Exception as e:
            logger.error(f"MedSigLIP triage failed: {e}")
            triage_summary = "MedSigLIP triage failed; proceeding with MedGemma direct analysis."
    else:
        logger.info("MedSigLIP not loaded, skipping triage. MedGemma will analyze directly.")
    
    # Step 2: MedGemma deep analysis (multimodal — image + text context)
    model = get_model()
    modality = triage_result.get("modality", "unknown")
    
    # Adapt prompt based on triage confidence: when MedSigLIP is uncertain,
    # don't feed it misleading triage labels — let MedGemma figure it out.
    if modality == "uncertain":
        medgemma_prompt = """Analyze this medical image in detail.

First, identify the imaging modality (e.g., chest X-ray, dermatology/skin photograph, histopathology slide, CT scan, MRI, etc.).

Then provide a thorough clinical interpretation including:
1. **Image type and quality**: What type of medical image is this? Is the quality adequate for interpretation?
2. **Key findings**: Describe all significant findings, both normal and abnormal.
3. **Clinical significance**: What do these findings suggest clinically?
4. **Differential considerations**: What conditions should be considered based on these findings?
5. **Recommended follow-up**: What additional imaging or tests would help clarify the findings?

Be specific and cite visible features in the image."""
        system_prompt = (
            "You are a medical imaging specialist experienced in radiology, "
            "dermatology, and pathology. Analyze medical images with precision, "
            "citing specific visual findings. Be thorough but concise."
        )
    else:
        medgemma_prompt = f"""Analyze this medical image in detail.

{triage_summary}

Provide a thorough clinical interpretation including:
1. **Image type and quality**: What type of medical image is this? Is the quality adequate for interpretation?
2. **Key findings**: Describe all significant findings, both normal and abnormal.
3. **Clinical significance**: What do these findings suggest clinically?
4. **Differential considerations**: What conditions should be considered based on these findings?
5. **Recommended follow-up**: What additional imaging or tests would help clarify the findings?

Be specific and cite visible features in the image."""
        system_prompt = (
            "You are a specialist radiologist and medical imaging expert. "
            "Analyze medical images with precision, citing specific visual "
            "findings. Be thorough but concise."
        )
    
    try:
        t_mg_start = time.time()
        medgemma_analysis = model.generate(
            medgemma_prompt,
            system_prompt=system_prompt,
            image=image,
            max_new_tokens=2048,
            temperature=0.1,
        )
        t_mg_end = time.time()
        logger.info(f"[analyze-image] medgemma={t_mg_end-t_mg_start:.2f}s ({len(medgemma_analysis)} chars)")
    except Exception as e:
        logger.error(f"MedGemma image analysis failed: {e}")
        medgemma_analysis = f"Image analysis encountered an error: {str(e)}"
    
    # Check if MedGemma refused (pure disclaimers, no real analysis).
    # If so, retry once with a simpler prompt that bypasses safety guardrails.
    # We do NOT strip disclaimers from real analysis — they're appropriate for medical AI.
    if is_pure_refusal(medgemma_analysis):
        logger.info("MedGemma refused on first attempt, retrying with direct prompt...")
        retry_prompt = (
            "Describe the visual findings in this medical image. "
            "Focus only on what you observe: colors, shapes, textures, "
            "borders, symmetry, and any notable features. "
            "Do not provide a diagnosis, just describe the image."
        )
        try:
            retry_analysis = model.generate(
                retry_prompt,
                system_prompt="You are a clinical image analyst. Describe medical images objectively.",
                image=image,
                max_new_tokens=2048,
                temperature=0.3,
            )
            if not is_pure_refusal(retry_analysis):
                logger.info(f"Retry succeeded: {len(retry_analysis)} chars")
                medgemma_analysis = retry_analysis
            else:
                logger.warning("Retry also refused, keeping original output")
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
    
    # Strip leading refusal preamble ("I am unable to... However, ...")
    # when real analysis follows.  Trailing disclaimers are kept.
    original_len = len(medgemma_analysis)
    medgemma_analysis = strip_refusal_preamble(medgemma_analysis)
    if len(medgemma_analysis) < original_len:
        logger.info(f"Stripped refusal preamble ({original_len} → {len(medgemma_analysis)} chars)")
    
    t_total = time.time()
    logger.info(f"[analyze-image] total={t_total-t0:.2f}s")
    
    # Return response with rate limit headers
    response_data = ImageAnalysisResponse(
        image_type=triage_result.get("image_type", "medical image"),
        image_type_confidence=triage_result.get("image_type_confidence", 0.0),
        modality=triage_result.get("modality", "unknown"),
        triage_findings=[
            ImageFinding(label=f["label"], score=f["score"])
            for f in triage_result.get("findings", [])
        ],
        triage_summary=triage_result.get("triage_summary", ""),
        medgemma_analysis=medgemma_analysis,
    )
    
    # Add rate limit headers to response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=response_data.model_dump(),
        headers=rate_limit_headers
    )


@app.post("/summary", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest, req: Request):
    """Generate final diagnosis summary."""
    # Check rate limit
    rate_limit_headers = check_rate_limit("summary", req)
    
    logger.info("Generating final diagnosis summary")
    
    try:
        t0 = time.time()
        model = get_model()
        formatted_labs = format_lab_values(request.lab_values)
        formatted_diff = format_differential([d.model_dump() for d in request.final_differential])
        formatted_rounds = format_rounds(request.debate_rounds)
        
        prompt = SUMMARY_PROMPT.format(
            patient_history=request.patient_history,
            formatted_lab_values=formatted_labs,
            final_differential=formatted_diff,
            debate_rounds=formatted_rounds
        )
        
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=3072)
        t1 = time.time()
        logger.info(f"[summary] medgemma={t1-t0:.2f}s")
        
        data = extract_json(response)
        
        # Handle ruled_out which may be list of strings or list of dicts
        ruled_out_raw = data.get("ruled_out", [])
        ruled_out = []
        for item in ruled_out_raw:
            if isinstance(item, str):
                ruled_out.append(item)
            elif isinstance(item, dict):
                # Extract diagnosis name from dict format
                ruled_out.append(item.get("diagnosis", item.get("name", str(item))))
            else:
                ruled_out.append(str(item))
        
        # Return response with rate limit headers
        response_data = SummaryResponse(
            final_diagnosis=data.get("final_diagnosis", "Unable to determine"),
            confidence=data.get("confidence", "low"),
            confidence_percent=data.get("confidence_percent"),
            reasoning_chain=data.get("reasoning_chain", []),
            ruled_out=ruled_out,
            next_steps=data.get("next_steps", [])
        )
        
        # Add rate limit headers to response
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=response_data.model_dump(),
            headers=rate_limit_headers
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summary generation error: {str(e)[:200]}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
