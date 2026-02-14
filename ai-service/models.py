"""
Pydantic request/response models for the Sturgeon AI Service API.
"""
from pydantic import BaseModel, field_validator
from typing import Optional, List


# --- Lab Extraction ---

class ExtractLabsRequest(BaseModel):
    lab_report_text: str

    @field_validator("lab_report_text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Lab report text cannot be empty")
        return v.strip()


class ExtractLabsResponse(BaseModel):
    lab_values: dict
    abnormal_values: list[str]


class ExtractLabsFileResponse(BaseModel):
    lab_values: dict
    abnormal_values: list[str]
    raw_text: str  # Extracted text from the file for transparency


# --- Differential Diagnosis ---

class DifferentialRequest(BaseModel):
    patient_history: str
    lab_values: dict

    @field_validator("patient_history")
    @classmethod
    def history_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Patient history cannot be empty")
        return v.strip()


class Diagnosis(BaseModel):
    name: str
    probability: str  # "high", "medium", "low"
    supporting_evidence: list[str]
    against_evidence: list[str]
    suggested_tests: list[str]


class DifferentialResponse(BaseModel):
    diagnoses: list[Diagnosis]


# --- Debate Turn ---

class DebateTurnRequest(BaseModel):
    patient_history: str
    lab_values: dict
    current_differential: list[Diagnosis]
    previous_rounds: list[dict]
    user_challenge: str
    session_id: Optional[str] = None  # For session state tracking
    image_context: Optional[str] = None  # MedSigLIP + MedGemma image findings

    @field_validator("user_challenge")
    @classmethod
    def challenge_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("User challenge cannot be empty")
        return v.strip()


class Citation(BaseModel):
    """A clinical guideline citation extracted from the AI response."""
    text: str  # e.g., "(IDSA Guidelines for Community-Acquired Pneumonia, 2023)"
    url: str   # Link to the guideline
    source: str  # e.g., "IDSA", "CDC", "ATS"


class DebateTurnResponse(BaseModel):
    ai_response: str
    updated_differential: list[Diagnosis]
    suggested_test: Optional[str] = None
    session_id: Optional[str] = None  # Returned for session continuity
    orchestrated: bool = False  # Whether Gemini orchestrator was used
    citations: List[Citation] = []  # RAG: Clinical guideline citations
    has_guidelines: bool = False  # RAG: Whether guidelines were referenced


# --- Summary ---

class SummaryRequest(BaseModel):
    patient_history: str
    lab_values: dict
    final_differential: list[Diagnosis]
    debate_rounds: list[dict]


class SummaryResponse(BaseModel):
    final_diagnosis: str
    confidence: str
    confidence_percent: Optional[int] = None  # 0-100 if provided by model
    reasoning_chain: list[str]
    ruled_out: list[str]
    next_steps: list[str]


# --- Image Analysis ---

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
