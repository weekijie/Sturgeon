"""Tests for MedGemma refusal detection and preamble stripping."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from refusal import is_pure_refusal, strip_refusal_preamble


class TestIsPureRefusal:
    """Test is_pure_refusal."""
    
    def test_pure_refusal(self):
        text = (
            "I am an AI language model and cannot provide medical advice. "
            "Please consult with a qualified healthcare professional."
        )
        assert is_pure_refusal(text) is True
    
    def test_refusal_with_analysis(self):
        text = (
            "I am an AI and this is not medical advice. "
            "However, the image shows a 4mm asymmetric pigmented lesion "
            "with irregular borders on the upper back. The lesion exhibits "
            "color variegation with shades of brown and black. "
            "ABCDE criteria suggest further evaluation is warranted."
        )
        assert is_pure_refusal(text) is False
    
    def test_normal_analysis(self):
        text = (
            "The lab values indicate elevated CRP at 45 mg/L with normal WBC, "
            "suggesting a non-bacterial inflammatory process. Combined with "
            "the joint symptoms, this pattern is consistent with autoimmune etiology."
        )
        assert is_pure_refusal(text) is False
    
    def test_only_disclaimers(self):
        text = (
            "As an AI language model, I'm not a medical professional. "
            "I cannot provide clinical interpretation. "
            "This is not intended as medical advice. "
            "It is important to consult with your healthcare provider."
        )
        assert is_pure_refusal(text) is True
    
    def test_short_text(self):
        assert is_pure_refusal("I cannot help.") is True
    
    def test_empty_text(self):
        assert is_pure_refusal("") is True
    
    def test_disclaimer_plus_minimal_content(self):
        text = (
            "I am an AI and cannot provide medical diagnosis. "
            "Please see a doctor. OK."
        )
        assert is_pure_refusal(text) is True


class TestStripRefusalPreamble:
    """Test strip_refusal_preamble."""
    
    def test_however_transition(self):
        text = (
            "I am unable to provide a clinical interpretation of medical images. "
            "However, I can describe what I observe. The image shows a "
            "pigmented lesion approximately 5mm in diameter with irregular "
            "borders and color variegation. The lesion sits on the upper back "
            "and exhibits features that warrant further dermatological evaluation."
        )
        result = strip_refusal_preamble(text)
        assert not result.startswith("I am unable")
        assert "pigmented lesion" in result or "describe" in result.lower()
    
    def test_that_said_transition(self):
        text = (
            "I'm not a medical professional and cannot diagnose conditions. "
            "That said, the chest X-ray reveals bilateral infiltrates in the "
            "lower lobes with air bronchograms visible. There is blunting of "
            "the right costophrenic angle suggesting possible pleural effusion."
        )
        result = strip_refusal_preamble(text)
        assert "chest X-ray" in result or "bilateral infiltrates" in result
    
    def test_no_preamble(self):
        text = (
            "The lab values show elevated CRP at 45 with normal WBC. "
            "This suggests a non-bacterial inflammatory process. "
            "Consider autoimmune workup."
        )
        result = strip_refusal_preamble(text)
        assert result == text
    
    def test_short_remaining_text(self):
        # If remaining text after preamble strip is too short, keep original
        text = (
            "I am unable to provide medical advice. However, see a doctor."
        )
        result = strip_refusal_preamble(text)
        assert result == text  # Too short remaining → keep original
    
    def test_nevertheless_transition(self):
        text = (
            "I cannot offer a definitive diagnosis as I am an AI. "
            "Nevertheless, the presented findings of elevated ferritin at 847 ng/mL "
            "combined with elevated transferrin saturation at 62% and liver enzyme "
            "abnormalities strongly suggest hereditary hemochromatosis."
        )
        result = strip_refusal_preamble(text)
        assert "ferritin" in result
