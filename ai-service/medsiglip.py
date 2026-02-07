"""
MedSigLIP - Medical image triage via zero-shot classification.
Based on: https://huggingface.co/google/medsiglip-448

MedSigLIP is a 800M param (400M vision + 400M text) SigLIP variant
trained on de-identified medical images. It classifies images into
medical categories via text-image similarity without any fine-tuning.

Pipeline: MedSigLIP (fast triage) -> MedGemma (deep reasoning) -> Gemini (orchestration)
"""
from transformers import AutoProcessor, AutoModel
from PIL import Image
from typing import Optional
import torch
import logging

logger = logging.getLogger(__name__)

# Predefined label sets for common medical image types
MEDICAL_IMAGE_LABELS = {
    "image_type": [
        "a chest X-ray radiograph",
        "a dermatology photograph of skin",
        "a histopathology microscopy slide",
        "a CT scan slice",
        "an MRI scan slice",
        "an ophthalmology fundus photograph",
        "a clinical photograph",
        "a lab report document",
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


class MedSigLIPModel:
    """Zero-shot medical image classifier using MedSigLIP."""

    def __init__(self):
        self.model = None
        self.processor = None
        self.device = None

    def load(self, model_id: str = "google/medsiglip-448"):
        """Load MedSigLIP model."""
        logger.info(f"Loading MedSigLIP: {model_id}...")

        if torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"

        self.model = AutoModel.from_pretrained(model_id).to(self.device)
        self.processor = AutoProcessor.from_pretrained(model_id)

        logger.info(f"MedSigLIP loaded on {self.device}")
        return self

    def classify(
        self,
        image: Image.Image,
        labels: list[str],
        top_k: int = 5,
    ) -> list[dict]:
        """Classify an image against a set of text labels.

        Args:
            image: PIL Image to classify
            labels: List of text descriptions to score against
            top_k: Number of top results to return

        Returns:
            List of dicts with 'label' and 'score' keys, sorted by score descending
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        inputs = self.processor(
            text=labels,
            images=[image],
            padding="max_length",
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        # Softmax over labels for this single image
        probs = torch.softmax(outputs.logits_per_image[0], dim=0)

        results = []
        for i, label in enumerate(labels):
            results.append({"label": label, "score": float(probs[i])})

        # Sort by score descending, return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def identify_image_type(self, image: Image.Image) -> dict:
        """Identify what type of medical image this is.

        Returns:
            Dict with 'image_type' (best match) and 'all_scores' (full ranking)
        """
        results = self.classify(image, MEDICAL_IMAGE_LABELS["image_type"])
        return {
            "image_type": results[0]["label"],
            "confidence": results[0]["score"],
            "all_scores": results,
        }

    def analyze_findings(
        self,
        image: Image.Image,
        image_type: Optional[str] = None,
    ) -> dict:
        """Run finding-specific classification based on image type.

        If image_type is not provided, auto-detects it first.

        Returns:
            Dict with 'image_type', 'findings' (top scored labels),
            and 'triage_summary' (text summary for MedGemma context)
        """
        # Step 1: Identify image type if not provided
        if image_type is None:
            type_result = self.identify_image_type(image)
            image_type = type_result["image_type"]
            type_confidence = type_result["confidence"]
        else:
            type_confidence = 1.0

        # Step 2: Pick the right label set
        if "chest" in image_type.lower() or "x-ray" in image_type.lower() or "radiograph" in image_type.lower():
            finding_labels = MEDICAL_IMAGE_LABELS["chest_xray_findings"]
            modality = "chest_xray"
        elif "dermatol" in image_type.lower() or "skin" in image_type.lower():
            finding_labels = MEDICAL_IMAGE_LABELS["dermatology_findings"]
            modality = "dermatology"
        elif "pathol" in image_type.lower() or "histopathol" in image_type.lower() or "microscop" in image_type.lower():
            finding_labels = MEDICAL_IMAGE_LABELS["pathology_findings"]
            modality = "pathology"
        else:
            # For CT, MRI, fundus, clinical photos, etc. -- use chest X-ray labels
            # as a reasonable default, but flag it
            finding_labels = MEDICAL_IMAGE_LABELS["chest_xray_findings"]
            modality = "general"

        # Step 3: Classify findings
        findings = self.classify(image, finding_labels, top_k=5)

        # Step 4: Build triage summary for MedGemma context
        top_findings = [f for f in findings if f["score"] > 0.05]
        summary_lines = [
            f"MedSigLIP Image Triage (modality: {modality}):",
            f"  Image type: {image_type} (confidence: {type_confidence:.1%})",
            "  Top findings:",
        ]
        for f in top_findings[:5]:
            summary_lines.append(f"    - {f['label']}: {f['score']:.1%}")

        return {
            "image_type": image_type,
            "image_type_confidence": type_confidence,
            "modality": modality,
            "findings": findings,
            "triage_summary": "\n".join(summary_lines),
        }


# Singleton
_siglip_instance: Optional[MedSigLIPModel] = None


def get_siglip() -> MedSigLIPModel:
    """Get or create the MedSigLIP model instance."""
    global _siglip_instance
    if _siglip_instance is None:
        _siglip_instance = MedSigLIPModel()
    return _siglip_instance
