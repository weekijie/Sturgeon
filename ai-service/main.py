"""
Sturgeon AI Service - FastAPI Backend
Gemini-orchestrated, MedGemma-powered diagnostic reasoning

Architecture:
  - Gemini (Pro/Flash) = Orchestrator for multi-turn debate management
  - MedGemma 4B-it = Medical specialist (callable tool)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile
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
    from gemini_orchestrator import get_orchestrator, ClinicalState
    from prompts import (SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT,
                         DEBATE_TURN_PROMPT, SUMMARY_PROMPT)
    from models import (ExtractLabsRequest, ExtractLabsResponse, ExtractLabsFileResponse,
                        DifferentialRequest, Diagnosis, DifferentialResponse,
                        DebateTurnRequest, DebateTurnResponse,
                        SummaryRequest, SummaryResponse,
                        ImageFinding, ImageAnalysisResponse)
    from json_utils import extract_json
    from refusal import is_pure_refusal, strip_refusal_preamble
    from formatters import format_lab_values, format_differential, format_rounds
except ImportError:
    from .medgemma import get_model
    from .medsiglip import get_siglip
    from .gemini_orchestrator import get_orchestrator, ClinicalState
    from .prompts import (SYSTEM_PROMPT, EXTRACT_LABS_PROMPT, DIFFERENTIAL_PROMPT,
                          DEBATE_TURN_PROMPT, SUMMARY_PROMPT)
    from .models import (ExtractLabsRequest, ExtractLabsResponse, ExtractLabsFileResponse,
                         DifferentialRequest, Diagnosis, DifferentialResponse,
                         DebateTurnRequest, DebateTurnResponse,
                         SummaryRequest, SummaryResponse,
                         ImageFinding, ImageAnalysisResponse)
    from .json_utils import extract_json
    from .refusal import is_pure_refusal, strip_refusal_preamble
    from .formatters import format_lab_values, format_differential, format_rounds

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory session store for clinical states
# Maps session_id -> ClinicalState
_sessions: dict[str, ClinicalState] = {}

# Flags: which optional services are available?
_gemini_available = False
_siglip_available = False


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
    
    logger.info("Ready to serve requests.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Sturgeon AI Service",
    description="Gemini-orchestrated, MedGemma-powered diagnostic debate API",
    version="0.3.0",
    lifespan=lifespan
)

# CORS for Next.js frontend
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
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
        "mode": "agentic" if _gemini_available else "medgemma-only",
        "image_triage": "medsiglip+medgemma" if _siglip_available else "medgemma-only",
        "active_sessions": len(_sessions),
    }


@app.post("/extract-labs", response_model=ExtractLabsResponse)
async def extract_labs(request: ExtractLabsRequest):
    """Extract structured lab values from text."""
    logger.info(f"Extracting labs from text ({len(request.lab_report_text)} chars)")
    
    try:
        t0 = time.time()
        model = get_model()
        prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=request.lab_report_text)
        
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=1024, temperature=0.3)
        t1 = time.time()
        logger.info(f"[extract-labs] medgemma={t1-t0:.2f}s")
        
        data = extract_json(response)
        
        return ExtractLabsResponse(
            lab_values=data.get("lab_values", {}),
            abnormal_values=data.get("abnormal_values", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lab extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lab extraction error: {str(e)[:200]}")


@app.post("/extract-labs-file", response_model=ExtractLabsFileResponse)
async def extract_labs_file(file: UploadFile = FastAPIFile(...)):
    """Extract structured lab values from an uploaded PDF or text file.
    
    Workflow:
    1. Read uploaded file (PDF → pdfplumber, TXT → direct read)
    2. Extract raw text (including tables for PDFs)
    3. Send to MedGemma via EXTRACT_LABS_PROMPT for structured parsing
    4. Return structured lab values + abnormal flags + raw text
    """
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
        
        return ExtractLabsFileResponse(
            lab_values=data.get("lab_values", {}),
            abnormal_values=data.get("abnormal_values", []),
            raw_text=raw_text[:5000]  # Cap at 5k chars for response size
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
async def generate_differential(request: DifferentialRequest):
    """Generate initial differential diagnoses."""
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
        
        diagnoses = []
        for dx in data.get("diagnoses", []):
            diagnoses.append(Diagnosis(
                name=dx.get("name", "Unknown"),
                probability=dx.get("probability", "medium"),
                supporting_evidence=dx.get("supporting_evidence", []),
                against_evidence=dx.get("against_evidence", []),
                suggested_tests=dx.get("suggested_tests", [])
            ))
        
        t2 = time.time()
        logger.info(f"[differential] total={t2-t0:.2f}s diagnoses={len(diagnoses)}")
        return DifferentialResponse(diagnoses=diagnoses)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Differential generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Differential generation error: {str(e)[:200]}")


@app.post("/debate-turn", response_model=DebateTurnResponse)
async def debate_turn(request: DebateTurnRequest):
    """Handle a debate round - orchestrated by Gemini, powered by MedGemma."""
    logger.info(f"Processing debate turn: {request.user_challenge[:50]}...")
    
    if _gemini_available:
        return await _debate_turn_orchestrated(request)
    else:
        return await _debate_turn_medgemma_only(request)


async def _debate_turn_orchestrated(request: DebateTurnRequest) -> DebateTurnResponse:
    """Orchestrated debate turn: Gemini manages conversation, MedGemma provides
    medical reasoning."""
    orchestrator = get_orchestrator()
    
    # Get or create session
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in _sessions:
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
    
    try:
        t0 = time.time()
        # Run synchronous orchestrator call in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(
            orchestrator.process_debate_turn,
            user_challenge=request.user_challenge,
            clinical_state=clinical_state,
            previous_rounds=request.previous_rounds[-3:] if request.previous_rounds else None,
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
        formatted_labs = format_lab_values(request.lab_values)
        formatted_diff = format_differential([d.model_dump() for d in request.current_differential])
        formatted_rounds = format_rounds(request.previous_rounds)
        
        # Include image context if available
        image_context = request.image_context or "No image evidence available"
        
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
        
        # Parse updated differential with robust field name handling
        diagnoses = _parse_differential(data.get("updated_differential", []))
        
        # RAG: Extract citations from response (fallback mode)
        ai_response_text = data.get("ai_response", "")
        from gemini_orchestrator import extract_citations
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
async def analyze_image(file: UploadFile = FastAPIFile(...)):
    """Analyze a medical image using MedSigLIP triage + MedGemma deep analysis.
    
    Pipeline:
    1. MedSigLIP: Fast zero-shot classification (~100ms) — identifies image type
       and preliminary findings with confidence scores
    2. MedGemma: Deep clinical interpretation — receives the image + MedSigLIP
       triage summary as context for focused analysis
    """
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
    
    return ImageAnalysisResponse(
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


@app.post("/summary", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    """Generate final diagnosis summary."""
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
        
        return SummaryResponse(
            final_diagnosis=data.get("final_diagnosis", "Unable to determine"),
            confidence=data.get("confidence", "low"),
            confidence_percent=data.get("confidence_percent"),
            reasoning_chain=data.get("reasoning_chain", []),
            ruled_out=ruled_out,
            next_steps=data.get("next_steps", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summary generation error: {str(e)[:200]}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
