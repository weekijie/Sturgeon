"""
Tests for hallucination detection module.
"""

import pytest
from hallucination_check import (
    extract_numeric_values,
    extract_lab_mentions,
    check_hallucination,
    validate_differential_response,
    validate_debate_response,
)


class TestExtractNumericValues:
    """Tests for numeric value extraction."""

    def test_extract_hemoglobin(self):
        """Test extracting hemoglobin value."""
        text = "Low hemoglobin at 8.2 g/dL"
        values = extract_numeric_values(text)
        assert len(values) == 1
        assert values[0]["value"] == 8.2
        assert "g/dl" in values[0]["unit"].lower()

    def test_extract_ferritin(self):
        """Test extracting ferritin value."""
        text = "Ferritin at 12 ng/mL is low"
        values = extract_numeric_values(text)
        assert len(values) == 1
        assert values[0]["value"] == 12
        assert "ng" in values[0]["unit"].lower()

    def test_extract_multiple_values(self):
        """Test extracting multiple values."""
        text = "Hemoglobin 8.2 g/dL, Ferritin 12 ng/mL, MCV 72 fL"
        values = extract_numeric_values(text)
        assert len(values) == 3

    def test_no_values(self):
        """Test text with no numeric values."""
        text = "Patient presents with fatigue and pallor"
        values = extract_numeric_values(text)
        assert len(values) == 0


class TestExtractLabMentions:
    """Tests for lab mention extraction."""

    def test_extract_hemoglobin_mention(self):
        """Test extracting hemoglobin mention."""
        text = "Low hemoglobin suggests anemia"
        mentions = extract_lab_mentions(text)
        assert "hemoglobin" in mentions

    def test_extract_multiple_mentions(self):
        """Test extracting multiple lab mentions."""
        text = "Hemoglobin, ferritin, and MCV are abnormal"
        mentions = extract_lab_mentions(text)
        assert "hemoglobin" in mentions
        assert "ferritin" in mentions
        assert "mcv" in mentions

    def test_no_mentions(self):
        """Test text with no lab mentions."""
        text = "Patient reports fatigue and weakness"
        mentions = extract_lab_mentions(text)
        assert len(mentions) == 0


class TestCheckHallucination:
    """Tests for hallucination detection."""

    def test_no_hallucination_when_provided(self):
        """Test that provided lab values are not flagged."""
        text = "Low hemoglobin at 8.2 g/dL suggests anemia"
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = check_hallucination(text, provided)
        assert result["has_hallucination"] is False

    def test_hallucination_detected(self):
        """Test that fabricated lab values are detected."""
        text = "Low hemoglobin at 8.2 g/dL and low ferritin at 12 ng/mL"
        provided = {}
        result = check_hallucination(text, provided)
        assert result["has_hallucination"] is True
        assert len(result["hallucinated_values"]) >= 1

    def test_partial_hallucination(self):
        """Test when only some values are fabricated."""
        text = "Hemoglobin 8.2 g/dL and Ferritin 12 ng/mL"
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = check_hallucination(text, provided)
        assert result["has_hallucination"] is True
        ferritin_hallucinated = any(
            hv["test"] == "ferritin" for hv in result["hallucinated_values"]
        )
        assert ferritin_hallucinated

    def test_no_hallucination_in_pure_description(self):
        """Test text without numeric values doesn't trigger false positive."""
        text = "Fatigue and pallor reported, suggest checking iron studies"
        provided = {}
        result = check_hallucination(text, provided)
        assert result["has_hallucination"] is False


class TestValidateDifferentialResponse:
    """Tests for differential response validation."""

    def test_valid_differential(self):
        """Test differential with only provided values."""
        response = {
            "diagnoses": [
                {
                    "name": "Iron Deficiency Anemia",
                    "probability": "high",
                    "supporting_evidence": ["Low hemoglobin", "Fatigue reported"],
                    "against_evidence": [],
                    "suggested_tests": ["Iron studies"],
                }
            ]
        }
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = validate_differential_response(response, provided)
        assert result["has_hallucination"] is False

    def test_differential_with_hallucinated_value(self):
        """Test differential with fabricated lab value."""
        response = {
            "diagnoses": [
                {
                    "name": "Iron Deficiency Anemia",
                    "probability": "high",
                    "supporting_evidence": ["Low hemoglobin at 8.2 g/dL", "Low ferritin at 12 ng/mL"],
                    "against_evidence": [],
                    "suggested_tests": ["Iron studies"],
                }
            ]
        }
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = validate_differential_response(response, provided)
        assert result["has_hallucination"] is True


class TestValidateDebateResponse:
    """Tests for debate response validation."""

    def test_valid_debate_response(self):
        """Test debate response with only provided values."""
        response = {
            "ai_response": "Based on the low hemoglobin, I maintain my suspicion for anemia.",
            "updated_differential": [
                {
                    "name": "Iron Deficiency Anemia",
                    "probability": "high",
                    "supporting_evidence": ["Low hemoglobin"],
                    "against_evidence": [],
                }
            ],
        }
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = validate_debate_response(response, provided)
        assert result["has_hallucination"] is False

    def test_debate_with_hallucinated_value(self):
        """Test debate response with fabricated value."""
        response = {
            "ai_response": "The ferritin of 12 ng/mL strongly supports iron deficiency.",
            "updated_differential": [],
        }
        provided = {"Hemoglobin": {"value": 8.2, "unit": "g/dL", "status": "low"}}
        result = validate_debate_response(response, provided)
        assert result["has_hallucination"] is True