"""
Sturgeon AI Service - FastAPI Backend
Gemini-orchestrated, MedGemma-powered diagnostic reasoning

Architecture:
  - Gemini (Pro/Flash) = Orchestrator for multi-turn debate management
  - MedGemma 4B-it = Medical specialist (callable tool)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
from PIL import Image
import asyncio
import logging
import json
import re
import os
import uuid
import io

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from .medgemma import get_model
from .medsiglip import get_siglip
from .gemini_orchestrator import (
    get_orchestrator,
    ClinicalState,
)
from .prompts import (
    SYSTEM_PROMPT,
    EXTRACT_LABS_PROMPT,
    DIFFERENTIAL_PROMPT,
    DEBATE_TURN_PROMPT,
    SUMMARY_PROMPT
)

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
    version="0.2.0",
    lifespan=lifespan
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class ExtractLabsRequest(BaseModel):
    lab_report_text: str

class ExtractLabsResponse(BaseModel):
    lab_values: dict
    abnormal_values: list[str]

class ExtractLabsFileResponse(BaseModel):
    lab_values: dict
    abnormal_values: list[str]
    raw_text: str  # Extracted text from the file for transparency

class DifferentialRequest(BaseModel):
    patient_history: str
    lab_values: dict

class Diagnosis(BaseModel):
    name: str
    probability: str  # "high", "medium", "low"
    supporting_evidence: list[str]
    against_evidence: list[str]
    suggested_tests: list[str]

class DifferentialResponse(BaseModel):
    diagnoses: list[Diagnosis]

class DebateTurnRequest(BaseModel):
    patient_history: str
    lab_values: dict
    current_differential: list[Diagnosis]
    previous_rounds: list[dict]
    user_challenge: str
    session_id: Optional[str] = None  # For session state tracking
    image_context: Optional[str] = None  # MedSigLIP + MedGemma image findings

class DebateTurnResponse(BaseModel):
    ai_response: str
    updated_differential: list[Diagnosis]
    suggested_test: Optional[str] = None
    session_id: Optional[str] = None  # Returned for session continuity
    orchestrated: bool = False  # Whether Gemini orchestrator was used

class SummaryRequest(BaseModel):
    patient_history: str
    lab_values: dict
    final_differential: list[Diagnosis]
    debate_rounds: list[dict]

class SummaryResponse(BaseModel):
    final_diagnosis: str
    confidence: str
    reasoning_chain: list[str]
    ruled_out: list[str]
    next_steps: list[str]


class ImageFinding(BaseModel):
    label: str
    score: float

class ImageAnalysisResponse(BaseModel):
    image_type: str
    image_type_confidence: float
    modality: str
    triage_findings: list[ImageFinding]
    triage_summary: str
    medgemma_analysis: str


def _repair_truncated_json(text: str) -> str:
    """Repair JSON that was truncated mid-generation by closing open structures.
    
    Strategy: walk the string tracking open brackets/braces/strings,
    then append the necessary closing tokens.
    """
    # Strip trailing whitespace and incomplete tokens
    text = text.rstrip()
    # Remove trailing comma (common before truncation)
    text = re.sub(r',\s*$', '', text)
    
    # If we're inside a string value that was truncated, close it
    # Count unescaped quotes to determine if we're inside a string
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_string:
            i += 2  # skip escaped char
            continue
        if c == '"':
            in_string = not in_string
        i += 1
    
    if in_string:
        text += '"'
    
    # Now close any open brackets/braces
    stack = []
    in_str = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_str:
            i += 2
            continue
        if c == '"':
            in_str = not in_str
        elif not in_str:
            if c in ('{', '['):
                stack.append(c)
            elif c == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif c == ']' and stack and stack[-1] == '[':
                stack.pop()
        i += 1
    
    # Close in reverse order
    for opener in reversed(stack):
        text += ']' if opener == '[' else '}'
    
    return text


def _fix_newlines_in_json_strings(text: str) -> str:
    """Replace literal newlines inside JSON string values with spaces.
    
    Walks the text character-by-character, tracking whether we're inside
    a quoted string.  Any \\n found inside a string is replaced with a space.
    This is more robust than regex which can't reliably detect string boundaries
    (e.g. newlines after punctuation like '),' were missed by the old approach).
    """
    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_string and i + 1 < len(text):
            # Escaped character inside string — keep both chars as-is
            result.append(c)
            result.append(text[i + 1])
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        if c == '\n' and in_string:
            result.append(' ')
        else:
            result.append(c)
        i += 1
    return ''.join(result)


def extract_json(text: str) -> dict:
    """Extract JSON from model response with robust repair for truncated output.
    
    Handles: markdown code blocks, truncated JSON, missing commas,
    trailing commas, and unbalanced braces.
    """
    # Try to find JSON in code blocks first
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        text = json_match.group(1)
    
    # Find the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end + 1]
    elif start != -1:
        # No closing brace — truncated output
        text = text[start:]
    else:
        logger.error(f"No JSON object found in response: {text[:200]}...")
        raise HTTPException(status_code=500, detail="Model response contained no JSON")
    
    # Pre-process: fix literal newlines inside JSON string values.
    # MedGemma wraps long strings across lines (e.g. reasoning_chain entries),
    # which is invalid JSON.  Walk the text tracking quote boundaries and
    # replace any \n found inside a string with a space.
    text = _fix_newlines_in_json_strings(text)
    
    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error (attempt 1 - direct): {e}")
    
    # Attempt 2: fix missing commas between key-value pairs
    try:
        fixed = re.sub(r'"\s*\n\s*"', '",\n"', text)
        # Also fix trailing commas before closing brackets
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error (attempt 2 - comma fix): {e}")
    
    # Attempt 3: repair truncated JSON by closing open structures
    try:
        repaired = _repair_truncated_json(text)
        # Clean trailing commas that appear before closing brackets
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
        result = json.loads(repaired)
        logger.info("JSON successfully repaired from truncated output")
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error (attempt 3 - truncation repair): {e}")
    
    # Attempt 4: aggressive — extract whatever valid diagnoses we can
    # Look for complete diagnosis objects within the text
    try:
        diagnoses = []
        # Find all complete JSON objects that look like diagnoses
        pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+?"[^{}]*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                dx = json.loads(match)
                diagnoses.append(dx)
            except json.JSONDecodeError:
                continue
        if diagnoses:
            logger.info(f"Extracted {len(diagnoses)} diagnoses via regex fallback")
            return {"diagnoses": diagnoses}
    except Exception:
        pass
    
    logger.error(f"All JSON repair attempts failed.\nRaw text: {text[:500]}...")
    raise HTTPException(status_code=500, detail="Failed to parse model response as JSON")


def _is_pure_refusal(text: str) -> bool:
    """Detect if MedGemma's output is a pure refusal with no real analysis.
    
    Returns True if the output is entirely disclaimers/refusal boilerplate
    (e.g. "I am an AI and cannot provide medical advice.") with no
    substantive clinical content.  Returns False if there IS useful
    analysis — even if it starts with a disclaimer prefix.
    
    This is used to trigger a retry with a simpler prompt, NOT to
    strip disclaimers from otherwise good output.  Medical AI
    disclaimers are appropriate and should be shown to users.
    """
    disclaimer_patterns = [
        r"(?:^|\n)\s*(?:I am|I'm) (?:a |an )?(?:large )?(?:language model|AI|artificial intelligence)[^.]*\.\s*",
        r"(?:^|\n)\s*As an AI(?:\s+language model)?[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I'm not|I am not) a (?:medical |healthcare )?(?:professional|doctor|physician)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:This|The following) is not (?:intended as )?medical advice[^.]*\.\s*",
        r"(?:^|\n)\s*(?:It is (?:essential|important) to |Please |Always )?consult (?:with )?(?:a |your )?(?:qualified )?(?:healthcare|medical) (?:professional|provider|doctor)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I cannot|I can't) (?:provide|give|offer) medical (?:advice|diagnosis|treatment)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I am unable|I'm unable) to provide (?:a )?(?:medical )?(?:diagnosis|interpretation|clinical interpretation)[^.]*\.\s*",
        r"(?:^|\n)\s*This is because I (?:am|'m) an AI[^.]*\.\s*",
        r"(?:^|\n)\s*Analyzing medical images requires[^.]*\.\s*",
        r"(?:^|\n)\s*If you have a medical image[^.]*\.\s*",
        r"(?:^|\n)\s*They can properly[^.]*\.\s*",
        r"(?:^|\n)\s*\*{0,2}Disclaimer\*{0,2}:?\s*.*",
        r"(?:^|\n)\s*(?:Important|Note):?\s*(?:I am|I'm|This is) (?:not |an )?(?:AI|a substitute)[^.]*\.\s*",
    ]
    
    cleaned = text
    for pattern in disclaimer_patterns:
        flags = re.IGNORECASE | re.DOTALL if 'Disclaimer' in pattern else re.IGNORECASE
        cleaned = re.sub(pattern, '\n', cleaned, flags=flags)
    
    # Clean up excess whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    
    # If less than 50 chars remain after removing all disclaimers,
    # the model produced no real analysis — it's a pure refusal.
    return len(cleaned) < 50


def format_lab_values(lab_values: dict) -> str:
    """Format lab values dict into readable text."""
    lines = []
    for name, data in lab_values.items():
        if isinstance(data, dict):
            value = data.get('value', 'N/A')
            unit = data.get('unit', '')
            status = data.get('status', 'normal')
            lines.append(f"- {name}: {value} {unit} ({status})")
        else:
            lines.append(f"- {name}: {data}")
    return "\n".join(lines) if lines else "No lab values provided"


def format_differential(diagnoses: list) -> str:
    """Format differential list into readable text."""
    lines = []
    for i, dx in enumerate(diagnoses, 1):
        if isinstance(dx, dict):
            name = dx.get('name', 'Unknown')
            prob = dx.get('probability', 'unknown')
            lines.append(f"{i}. {name} (probability: {prob})")
        elif hasattr(dx, 'name'):
            lines.append(f"{i}. {dx.name} (probability: {dx.probability})")
    return "\n".join(lines) if lines else "No differential yet"


def format_rounds(rounds: list) -> str:
    """Format debate rounds into readable text."""
    lines = []
    for i, r in enumerate(rounds, 1):
        challenge = r.get('user_challenge', r.get('challenge', ''))
        response = r.get('ai_response', r.get('response', ''))
        lines.append(f"Round {i}:\nUser: {challenge}\nAI: {response}")
    return "\n\n".join(lines) if lines else "No previous rounds"


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
    
    model = get_model()
    prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=request.lab_report_text)
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=1024, temperature=0.3)
    data = extract_json(response)
    
    return ExtractLabsResponse(
        lab_values=data.get("lab_values", {}),
        abnormal_values=data.get("abnormal_values", [])
    )


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
        
        logger.info(f"Extracted {len(raw_text)} chars from {filename}")
        
        # Send extracted text to MedGemma for structured lab parsing
        model = get_model()
        prompt = EXTRACT_LABS_PROMPT.format(lab_report_text=raw_text)
        response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048, temperature=0.3)
        
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
            detail=f"Failed to extract lab values: {str(e)}"
        )


@app.post("/differential", response_model=DifferentialResponse)
async def generate_differential(request: DifferentialRequest):
    """Generate initial differential diagnoses."""
    logger.info("Generating differential for patient history")
    
    model = get_model()
    formatted_labs = format_lab_values(request.lab_values)
    prompt = DIFFERENTIAL_PROMPT.format(
        patient_history=request.patient_history,
        formatted_lab_values=formatted_labs
    )
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=3072, temperature=0.3)
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
    
    return DifferentialResponse(diagnoses=diagnoses)


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
        # Run synchronous orchestrator call in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(
            orchestrator.process_debate_turn,
            user_challenge=request.user_challenge,
            clinical_state=clinical_state,
            previous_rounds=request.previous_rounds[-3:] if request.previous_rounds else None,
        )
        
        # Parse updated differential with robust field name handling
        diagnoses = _parse_differential(result.get("updated_differential", []))
        
        return DebateTurnResponse(
            ai_response=result.get("ai_response", "I need more information to respond."),
            updated_differential=diagnoses if diagnoses else request.current_differential,
            suggested_test=result.get("suggested_test"),
            session_id=session_id,
            orchestrated=True,
        )
    except Exception as e:
        logger.error(f"Orchestrator error: {e}. Falling back to MedGemma-only.")
        return await _debate_turn_medgemma_only(request)


async def _debate_turn_medgemma_only(request: DebateTurnRequest) -> DebateTurnResponse:
    """Fallback: MedGemma-only debate turn (original implementation)."""
    try:
        model = get_model()
        formatted_labs = format_lab_values(request.lab_values)
        formatted_diff = format_differential([d.model_dump() for d in request.current_differential])
        formatted_rounds = format_rounds(request.previous_rounds)
        
        prompt = DEBATE_TURN_PROMPT.format(
            patient_history=request.patient_history,
            formatted_lab_values=formatted_labs,
            current_differential=formatted_diff,
            previous_rounds=formatted_rounds,
            user_challenge=request.user_challenge
        )
        
        # Run blocking MedGemma inference in a thread
        response = await asyncio.to_thread(
            model.generate, prompt,
            max_new_tokens=2048,
            system_prompt=SYSTEM_PROMPT,
        )
        data = extract_json(response)
        
        # Parse updated differential with robust field name handling
        diagnoses = _parse_differential(data.get("updated_differential", []))
        
        return DebateTurnResponse(
            ai_response=data.get("ai_response", "I need more information to respond."),
            updated_differential=diagnoses if diagnoses else request.current_differential,
            suggested_test=data.get("suggested_test"),
            orchestrated=False,
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
            logger.info(
                f"MedSigLIP triage: {triage_result['image_type']} "
                f"({triage_result['image_type_confidence']:.1%}), "
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
        medgemma_analysis = model.generate(
            medgemma_prompt,
            system_prompt=system_prompt,
            image=image,
            max_new_tokens=2048,
            temperature=0.1,
        )
        logger.info(f"MedGemma analysis: {len(medgemma_analysis)} chars")
    except Exception as e:
        logger.error(f"MedGemma image analysis failed: {e}")
        medgemma_analysis = f"Image analysis encountered an error: {str(e)}"
    
    # Check if MedGemma refused (pure disclaimers, no real analysis).
    # If so, retry once with a simpler prompt that bypasses safety guardrails.
    # We do NOT strip disclaimers from real analysis — they're appropriate for medical AI.
    if _is_pure_refusal(medgemma_analysis):
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
            if not _is_pure_refusal(retry_analysis):
                logger.info(f"Retry succeeded: {len(retry_analysis)} chars")
                medgemma_analysis = retry_analysis
            else:
                logger.warning("Retry also refused, keeping original output")
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
    
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
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048)
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
        reasoning_chain=data.get("reasoning_chain", []),
        ruled_out=ruled_out,
        next_steps=data.get("next_steps", [])
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

