"""
Hallucination detection for MedGemma outputs.
Validates that generated content only references data explicitly provided by the user.
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

COMMON_LAB_TESTS = [
    "hemoglobin", "hgb", "hb",
    "hematocrit", "hct",
    "wbc", "white blood cell", "leukocyte",
    "platelet", "plt",
    "ferritin",
    "iron", "serum iron",
    "tibc", "total iron binding capacity",
    "transferrin",
    "mcv", "mean corpuscular volume",
    "mch", "mean corpuscular hemoglobin",
    "mchc",
    "rdw",
    "rbc", "red blood cell", "erythrocyte",
    "crp", "c-reactive protein",
    "esr", "erythrocyte sedimentation rate",
    "creatinine", "cr",
    "bun", "blood urea nitrogen",
    "egfr", "gfr",
    "sodium", "na",
    "potassium", "k",
    "chloride", "cl",
    "bicarbonate", "co2",
    "glucose", "blood sugar",
    "hba1c", "a1c",
    "alt", "sgpt",
    "ast", "sgot",
    "alp", "alkaline phosphatase",
    "bilirubin",
    "albumin",
    "total protein",
    "tsh",
    "t3", "t4",
    "troponin",
    "bnP", "bnp",
    "d-dimer",
    "pt", "inr",
    "ptt",
    "lh", "fsh",
    "testosterone",
    "vitamin d", "25-oh vitamin d",
    "b12", "cobalamin",
    "folate",
    "tropinin",
]

NUMERIC_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:g\/dl|mg\/dl|mg\/l|ng\/ml|pg\/ml|mmol\/l|meq\/l|iu\/l|u\/l|×10\^?9\/l|×10\^?3\/μl|x10\^9\/l|%|k\/μl|k\/mm3|fl|pg)\b",
    re.IGNORECASE
)

LAB_MENTION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(lab) for lab in COMMON_LAB_TESTS) + r")\b",
    re.IGNORECASE
)


def extract_numeric_values(text: str) -> list[dict[str, Any]]:
    """
    Extract all numeric lab values mentioned in text.
    Returns list of dicts with 'value', 'unit', 'context'.
    """
    values = []
    for match in NUMERIC_PATTERN.finditer(text):
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        values.append({
            "value": float(match.group(1)),
            "unit": match.group(0).replace(match.group(1), "").strip(),
            "context": context.strip(),
            "full_match": match.group(0),
            "position": match.start(),
        })
    return values


def extract_lab_mentions(text: str) -> list[str]:
    """
    Extract all lab test names mentioned in text.
    Returns list of lowercase lab test names.
    """
    mentions = LAB_MENTION_PATTERN.findall(text.lower())
    return list(set(mentions))


def normalize_lab_name(name: str) -> str:
    """Normalize lab test name for comparison."""
    name = name.lower().strip()
    aliases = {
        "hgb": "hemoglobin",
        "hb": "hemoglobin",
        "hct": "hematocrit",
        "plt": "platelet",
        "wbc": "wbc",
        "crp": "crp",
        "mcv": "mcv",
    }
    return aliases.get(name, name)


def normalize_unit(unit: str) -> str:
    """Normalize lab units for comparison."""
    return (
        unit.lower()
        .replace(" ", "")
        .replace("×", "x")
        .replace("μ", "u")
        .replace("µ", "u")
    )


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_closest_lab(text: str, value_position: int) -> str | None:
    """
    Find the lab test name closest to a numeric value position.
    Returns the normalized lab name or None.
    """
    text_lower = text.lower()
    closest_lab = None
    closest_distance = float('inf')
    
    for lab in COMMON_LAB_TESTS:
        pattern = re.compile(rf"\b{re.escape(lab)}\b", re.IGNORECASE)
        for match in pattern.finditer(text_lower):
            pos = match.start()
            distance = abs(pos - value_position)
            if distance < closest_distance:
                closest_distance = distance
                closest_lab = lab
    
    return normalize_lab_name(closest_lab) if closest_lab else None


def check_hallucination(
    generated_text: str,
    provided_lab_values: dict[str, Any] | None = None,
    provided_patient_history: str | None = None,
) -> dict[str, Any]:
    """
    Check if generated text contains fabricated lab values.
    
    Args:
        generated_text: The AI-generated response to validate
        provided_lab_values: Dict of lab values actually provided by user
        provided_patient_history: Patient history text provided by user
    
    Returns:
        Dict with 'has_hallucination', 'hallucinated_values', 'warnings'
    """
    if provided_lab_values is None:
        provided_lab_values = {}
    
    result = {
        "has_hallucination": False,
        "hallucinated_values": [],
        "warnings": [],
    }
    
    extracted_values = extract_numeric_values(generated_text)
    provided_labs_normalized = {normalize_lab_name(k): k for k in provided_lab_values.keys()}

    allowed_values: list[tuple[float, str]] = []
    for lab_name, details in provided_lab_values.items():
        if isinstance(details, dict):
            value = _coerce_float(details.get("value"))
            unit = details.get("unit")
            if value is not None and unit:
                allowed_values.append((value, normalize_unit(str(unit))))

    if provided_patient_history:
        for item in extract_numeric_values(provided_patient_history):
            allowed_values.append((item["value"], normalize_unit(item["unit"])))
    
    for extracted in extracted_values:
        value_position = extracted["position"]
        extracted_unit = normalize_unit(extracted["unit"])

        is_allowed_value = any(
            abs(allowed_value - extracted["value"]) < 1e-3 and allowed_unit == extracted_unit
            for allowed_value, allowed_unit in allowed_values
        )
        if is_allowed_value:
            continue
        
        closest_lab = find_closest_lab(generated_text, value_position)
        
        if closest_lab and closest_lab not in provided_labs_normalized:
            result["has_hallucination"] = True
            result["hallucinated_values"].append({
                "test": closest_lab,
                "value": extracted["value"],
                "unit": extracted["unit"],
                "context": extracted["context"],
            })
            warning = f"Potential hallucination: '{extracted['full_match']}' for {closest_lab} not in provided data"
            result["warnings"].append(warning)
            logger.warning(f"Hallucination detected: {warning}")
    
    return result


def validate_differential_response(
    response: dict[str, Any],
    provided_lab_values: dict[str, Any] | None = None,
    provided_patient_history: str | None = None,
) -> dict[str, Any]:
    """
    Validate a differential diagnosis response for hallucinations.
    
    Args:
        response: The parsed JSON response from MedGemma
        provided_lab_values: Lab values actually provided by user
        provided_patient_history: Patient history provided by user
    
    Returns:
        Validation result with hallucination details
    """
    all_text_parts = []
    
    if "diagnoses" in response:
        for diag in response.get("diagnoses", []):
            for evidence in diag.get("supporting_evidence", []):
                all_text_parts.append(evidence)
            for evidence in diag.get("against_evidence", []):
                all_text_parts.append(evidence)
    
    combined_text = " ".join(all_text_parts)
    
    return check_hallucination(
        combined_text,
        provided_lab_values,
        provided_patient_history
    )


def validate_debate_response(
    response: dict[str, Any],
    provided_lab_values: dict[str, Any] | None = None,
    provided_patient_history: str | None = None,
) -> dict[str, Any]:
    """
    Validate a debate turn response for hallucinations.
    
    Args:
        response: The parsed JSON response from MedGemma
        provided_lab_values: Lab values actually provided by user
        provided_patient_history: Patient history provided by user
    
    Returns:
        Validation result with hallucination details
    """
    all_text_parts = []
    
    if "ai_response" in response:
        all_text_parts.append(response["ai_response"])
    
    if "updated_differential" in response:
        for diag in response.get("updated_differential", []):
            for evidence in diag.get("supporting_evidence", []):
                all_text_parts.append(evidence)
            for evidence in diag.get("against_evidence", []):
                all_text_parts.append(evidence)
    
    combined_text = " ".join(all_text_parts)
    
    return check_hallucination(
        combined_text,
        provided_lab_values,
        provided_patient_history
    )
