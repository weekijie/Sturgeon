"""
MedSigLIP Server - Standalone FastAPI server for medical image triage.

Runs as a separate process on Modal, providing fast zero-shot classification
via HTTP API. This allows the main FastAPI app to call it for image analysis
while vLLM handles the main MedGemma inference.
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import io
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedSigLIP Image Triage Server",
    description="Zero-shot medical image classification",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGE_TYPE_CONFIDENCE_THRESHOLD = 0.25

MEDICAL_IMAGE_LABELS = {
    "image_type": [
        "a chest x-ray radiograph showing lungs and heart",
        "a close-up photograph of a skin lesion or rash on a human body",
        "a histopathology microscopy image of stained tissue on a glass slide",
        "a CT scan cross-section of the body",
        "an MRI scan slice of the brain or body",
        "a retinal fundus photograph of the eye",
        "a clinical photograph of a patient",
        "a scanned document or printed medical report with text",
    ],
    "chest_xray_findings": [
        "normal chest X-ray with no abnormalities",
        "pleural effusion",
        "cardiomegaly with enlarged heart",
        "lung opacity or infiltrate",
        "pneumothorax",
        "consolidation consistent with pneumonia",
        "pulmonary edema",
        "atelectasis",
        "lung lesion or mass",
        "fracture",
        "support devices such as tubes or lines",
    ],
    "dermatology_findings": [
        "normal skin with no lesion",
        "melanoma or suspicious pigmented lesion",
        "basal cell carcinoma",
        "squamous cell carcinoma",
        "dermatitis or eczema",
        "psoriasis",
        "fungal infection",
        "benign mole or nevus",
        "acne",
        "rash or urticaria",
    ],
    "pathology_findings": [
        "normal tissue with no malignancy",
        "invasive carcinoma",
        "dysplasia or pre-cancerous changes",
        "inflammation",
        "necrosis",
        "benign proliferative changes",
    ],
}


class Finding(BaseModel):
    label: str
    score: float


class TriageResponse(BaseModel):
    image_type: str
    image_type_confidence: float
    modality: str
    findings: List[Finding]
    triage_summary: str


_model = None
_processor = None
_device = None


def get_model():
    """Lazy load MedSigLIP model."""
    global _model, _processor, _device
    
    if _model is None:
        import torch
        from transformers import AutoModel, AutoProcessor
        
        model_id = "google/medsiglip-448"
        logger.info(f"Loading MedSigLIP: {model_id}")
        
        if torch.cuda.is_available():
            _device = "cuda"
        else:
            _device = "cpu"
        
        _model = AutoModel.from_pretrained(model_id).to(_device)
        _model.eval()
        _processor = AutoProcessor.from_pretrained(model_id)
        logger.info(f"MedSigLIP loaded on {_device}")
    
    return _model, _processor, _device


def classify(image: Image.Image, labels: List[str], top_k: int = 5) -> List[dict]:
    """Classify an image against a set of text labels."""
    import torch
    
    model, processor, device = get_model()
    
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    inputs = processor(
        text=labels,
        images=[image],
        padding="max_length",
        return_tensors="pt",
    ).to(device)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    probs = torch.softmax(outputs.logits_per_image[0], dim=0)
    
    results = []
    for i, label in enumerate(labels):
        results.append({"label": label, "score": float(probs[i])})
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def analyze_findings(image: Image.Image) -> dict:
    """Run finding-specific classification based on image type."""
    type_results = classify(image, MEDICAL_IMAGE_LABELS["image_type"])
    image_type = type_results[0]["label"]
    type_confidence = type_results[0]["score"]
    
    if type_confidence < IMAGE_TYPE_CONFIDENCE_THRESHOLD:
        logger.info(
            f"Low confidence ({type_confidence:.1%}) for image type "
            f"'{image_type}'. Falling back to uncertain."
        )
        return {
            "image_type": image_type,
            "image_type_confidence": type_confidence,
            "modality": "uncertain",
            "findings": [],
            "triage_summary": (
                "MedSigLIP confidence is low for this image. "
                "MedGemma will determine the imaging modality and "
                "provide direct clinical interpretation."
            ),
        }
    
    type_lower = image_type.lower()
    if "chest" in type_lower or "x-ray" in type_lower or "radiograph" in type_lower:
        finding_labels = MEDICAL_IMAGE_LABELS["chest_xray_findings"]
        modality = "chest_xray"
    elif "skin" in type_lower or "lesion" in type_lower or "rash" in type_lower:
        finding_labels = MEDICAL_IMAGE_LABELS["dermatology_findings"]
        modality = "dermatology"
    elif "pathol" in type_lower or "histopathol" in type_lower or "microscop" in type_lower or "stained" in type_lower:
        finding_labels = MEDICAL_IMAGE_LABELS["pathology_findings"]
        modality = "pathology"
    else:
        finding_labels = None
        modality = "general"
    
    if finding_labels:
        findings = classify(image, finding_labels, top_k=5)
        top_findings = [f for f in findings if f["score"] > 0.05]
    else:
        findings = []
        top_findings = []
    
    summary_lines = [
        f"MedSigLIP Image Triage (modality: {modality}):",
        f"  Image type: {image_type} (confidence: {type_confidence:.1%})",
    ]
    if top_findings:
        summary_lines.append("  Top findings:")
        for f in top_findings[:5]:
            summary_lines.append(f"    - {f['label']}: {f['score']:.1%}")
    else:
        summary_lines.append("  No finding-specific labels applied for this modality.")
    
    return {
        "image_type": image_type,
        "image_type_confidence": type_confidence,
        "modality": modality,
        "findings": findings,
        "triage_summary": "\n".join(summary_lines),
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    model_loaded = _model is not None
    return {
        "status": "healthy",
        "model_loaded": model_loaded,
        "device": _device or "not_loaded"
    }


@app.post("/analyze", response_model=TriageResponse)
async def analyze_image(file: UploadFile = File(...)):
    """Analyze a medical image and return triage information."""
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}"
        )
    
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        logger.info(f"Image loaded: {image.size[0]}x{image.size[1]}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {e}")
    
    result = analyze_findings(image)
    
    return TriageResponse(
        image_type=result["image_type"],
        image_type_confidence=result["image_type_confidence"],
        modality=result["modality"],
        findings=[Finding(label=f["label"], score=f["score"]) for f in result["findings"]],
        triage_summary=result["triage_summary"],
    )


@app.on_event("startup")
async def startup():
    """Pre-load model on startup."""
    logger.info("Pre-loading MedSigLIP model...")
    get_model()
    logger.info("MedSigLIP ready")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 6502)))
