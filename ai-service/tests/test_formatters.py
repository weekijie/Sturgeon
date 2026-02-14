"""Tests for clinical data formatting utilities."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from formatters import format_lab_values, format_differential, format_rounds


class TestFormatLabValues:
    """Test format_lab_values."""
    
    def test_dict_format(self):
        labs = {
            "WBC": {"value": 11.2, "unit": "x10^9/L", "status": "high"},
            "CRP": {"value": 45, "unit": "mg/L", "status": "high"},
        }
        result = format_lab_values(labs)
        assert "WBC" in result
        assert "11.2" in result
        assert "high" in result
    
    def test_plain_values(self):
        labs = {"WBC": "11.2 x10^9/L", "CRP": "45 mg/L"}
        result = format_lab_values(labs)
        assert "WBC" in result
        assert "11.2 x10^9/L" in result
    
    def test_empty_dict(self):
        result = format_lab_values({})
        assert "No lab values" in result
    
    def test_mixed_formats(self):
        labs = {
            "WBC": {"value": 11.2, "unit": "x10^9/L", "status": "high"},
            "Notes": "Patient fasting",
        }
        result = format_lab_values(labs)
        assert "WBC" in result
        assert "Notes" in result


class TestFormatDifferential:
    """Test format_differential."""
    
    def test_dict_format(self):
        diffs = [
            {"name": "Pneumonia", "probability": "high"},
            {"name": "COPD", "probability": "medium"},
        ]
        result = format_differential(diffs)
        assert "Pneumonia" in result
        assert "high" in result
        assert "COPD" in result
    
    def test_empty_list(self):
        result = format_differential([])
        assert "No differential" in result
    
    def test_numbering(self):
        diffs = [
            {"name": "A", "probability": "high"},
            {"name": "B", "probability": "low"},
        ]
        result = format_differential(diffs)
        assert "1." in result
        assert "2." in result


class TestFormatRounds:
    """Test format_rounds."""
    
    def test_normal_rounds(self):
        rounds = [
            {"user_challenge": "What about CRP?", "ai_response": "Good point."},
            {"user_challenge": "Consider autoimmune?", "ai_response": "Yes."},
        ]
        result = format_rounds(rounds)
        assert "Round 1" in result
        assert "Round 2" in result
        assert "What about CRP?" in result
    
    def test_alternative_keys(self):
        rounds = [
            {"challenge": "What about CRP?", "response": "Good point."},
        ]
        result = format_rounds(rounds)
        assert "What about CRP?" in result
    
    def test_empty_list(self):
        result = format_rounds([])
        assert "No previous rounds" in result
