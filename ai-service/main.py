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


def strip_disclaimers(text: str) -> str:
    """Strip common AI safety disclaimers from model output.
    
    MedGemma sometimes prepends/appends standard disclaimers like:
    - "I am a large language model..."
    - "As an AI language model..."
    - "I'm not a medical professional..."
    - "This is not medical advice..."
    """
    # Patterns to remove (case-insensitive, match full sentences)
    disclaimer_patterns = [
        r"(?:^|\n)\s*(?:I am|I'm) (?:a |an )?(?:large )?(?:language model|AI|artificial intelligence)[^.]*\.\s*",
        r"(?:^|\n)\s*As an AI(?:\s+language model)?[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I'm not|I am not) a (?:medical |healthcare )?(?:professional|doctor|physician)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:This|The following) is not (?:intended as )?medical advice[^.]*\.\s*",
        r"(?:^|\n)\s*(?:It is (?:essential|important) to |Please |Always )?consult (?:with )?(?:a |your )?(?:qualified )?(?:healthcare|medical) (?:professional|provider|doctor)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I cannot|I can't) (?:provide|give|offer) medical (?:advice|diagnosis|treatment)[^.]*\.\s*",
        # Match **Disclaimer** or Disclaimer blocks (may span multiple sentences to end of text)
        r"(?:^|\n)\s*\*{0,2}Disclaimer\*{0,2}:?\s*.*",
        r"(?:^|\n)\s*(?:Important|Note):?\s*(?:I am|I'm|This is) (?:not |an )?(?:AI|a substitute)[^.]*\.\s*",
    ]
    
    cleaned = text
    for pattern in disclaimer_patterns:
        # Use DOTALL for the Disclaimer pattern so .* matches across newlines
        flags = re.IGNORECASE | re.DOTALL if 'Disclaimer' in pattern else re.IGNORECASE
        cleaned = re.sub(pattern, '\n', cleaned, flags=flags)
    
    # Clean up excess whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


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
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=1024)
    data = extract_json(response)
    
    return ExtractLabsResponse(
        lab_values=data.get("lab_values", {}),
        abnormal_values=data.get("abnormal_values", [])
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
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=3072)
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
        result = orchestrator.process_debate_turn(
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
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048)
    data = extract_json(response)
    
    # Parse updated differential with robust field name handling
    diagnoses = _parse_differential(data.get("updated_differential", []))
    
    return DebateTurnResponse(
        ai_response=data.get("ai_response", "I need more information to respond."),
        updated_differential=diagnoses if diagnoses else request.current_differential,
        suggested_test=data.get("suggested_test"),
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
    
    medgemma_prompt = f"""Analyze this medical image in detail.

{triage_summary}

Provide a thorough clinical interpretation including:
1. **Image type and quality**: What type of medical image is this? Is the quality adequate for interpretation?
2. **Key findings**: Describe all significant findings, both normal and abnormal.
3. **Clinical significance**: What do these findings suggest clinically?
4. **Differential considerations**: What conditions should be considered based on these findings?
5. **Recommended follow-up**: What additional imaging or tests would help clarify the findings?

Be specific and cite visible features in the image."""
    
    try:
        medgemma_analysis = model.generate(
            medgemma_prompt,
            system_prompt=(
                "You are a specialist radiologist and medical imaging expert. "
                "Analyze medical images with precision, citing specific visual "
                "findings. Be thorough but concise."
            ),
            image=image,
            max_new_tokens=2048,
        )
        logger.info(f"MedGemma analysis: {len(medgemma_analysis)} chars")
    except Exception as e:
        logger.error(f"MedGemma image analysis failed: {e}")
        medgemma_analysis = f"Image analysis encountered an error: {str(e)}"
    
    # Strip AI disclaimers from output for clean UI presentation
    medgemma_analysis = strip_disclaimers(medgemma_analysis)
    
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

