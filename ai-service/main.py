"""
Sturgeon AI Service - FastAPI Backend
MedGemma-powered diagnostic reasoning
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import logging
import json
import re

from .medgemma import get_model
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


# Model lifecycle - load on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load MedGemma model on startup."""
    logger.info("Starting Sturgeon AI Service...")
    model = get_model()
    model.load()
    logger.info("MedGemma loaded. Ready to serve requests.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Sturgeon AI Service",
    description="MedGemma-powered diagnostic debate API",
    version="0.1.0",
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

class DebateTurnResponse(BaseModel):
    ai_response: str
    updated_differential: list[Diagnosis]
    suggested_test: Optional[str] = None

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


def extract_json(text: str) -> dict:
    """Extract JSON from model response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        text = json_match.group(1)
    
    # Find the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end + 1]
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nText: {text[:500]}")
        raise HTTPException(status_code=500, detail=f"Failed to parse model response as JSON")


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
    return {"status": "healthy", "model_loaded": model.model is not None}


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
    
    response = model.generate(prompt, system_prompt=SYSTEM_PROMPT, max_new_tokens=2048)
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
    """Handle a debate round - respond to user challenge."""
    logger.info(f"Processing debate turn: {request.user_challenge[:50]}...")
    
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
    diagnoses = []
    updated_diff = data.get("updated_differential", [])
    
    for dx in updated_diff:
        if isinstance(dx, dict):
            # Handle various field name variations from MedGemma
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
    
    return DebateTurnResponse(
        ai_response=data.get("ai_response", "I need more information to respond."),
        updated_differential=diagnoses if diagnoses else request.current_differential,
        suggested_test=data.get("suggested_test")
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

