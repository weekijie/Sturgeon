"""Tests for JSON parsing and repair utilities."""
import pytest
import sys
import os

# Add parent directory to path so we can import the module directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from json_utils import _repair_truncated_json, _fix_newlines_in_json_strings, extract_json


class TestRepairTruncatedJson:
    """Test _repair_truncated_json."""
    
    def test_already_valid(self):
        result = _repair_truncated_json('{"name": "test"}')
        assert result == '{"name": "test"}'
    
    def test_missing_closing_brace(self):
        result = _repair_truncated_json('{"name": "test"')
        assert result.endswith('}')
        import json
        assert json.loads(result)["name"] == "test"
    
    def test_truncated_array(self):
        result = _repair_truncated_json('{"items": ["a", "b"')
        assert ']' in result and '}' in result
        import json
        parsed = json.loads(result)
        assert parsed["items"] == ["a", "b"]
    
    def test_truncated_string_value(self):
        result = _repair_truncated_json('{"name": "truncated val')
        import json
        parsed = json.loads(result)
        assert "truncated val" in parsed["name"]
    
    def test_trailing_comma_removed(self):
        result = _repair_truncated_json('{"a": 1,')
        assert not result.rstrip().endswith(',')
    
    def test_nested_objects(self):
        result = _repair_truncated_json('{"outer": {"inner": "val"')
        import json
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == "val"
    
    def test_empty_input(self):
        result = _repair_truncated_json('')
        assert result == ''


class TestFixNewlinesInJsonStrings:
    """Test _fix_newlines_in_json_strings."""
    
    def test_newline_inside_string(self):
        result = _fix_newlines_in_json_strings('{"text": "line1\nline2"}')
        assert '\n' not in result.split('"text"')[1].split('"}')[0]
        import json
        parsed = json.loads(result)
        assert parsed["text"] == "line1 line2"
    
    def test_newline_outside_string(self):
        text = '{\n  "key": "value"\n}'
        result = _fix_newlines_in_json_strings(text)
        import json
        assert json.loads(result)["key"] == "value"
    
    def test_escaped_quote_inside_string(self):
        result = _fix_newlines_in_json_strings('{"text": "say \\"hello\\""}')
        import json
        parsed = json.loads(result)
        assert 'hello' in parsed["text"]
    
    def test_no_newlines(self):
        text = '{"key": "value"}'
        result = _fix_newlines_in_json_strings(text)
        assert result == text
    
    def test_multiple_strings_with_newlines(self):
        text = '{"a": "line1\nline2", "b": "line3\nline4"}'
        result = _fix_newlines_in_json_strings(text)
        import json
        parsed = json.loads(result)
        assert parsed["a"] == "line1 line2"
        assert parsed["b"] == "line3 line4"


class TestExtractJson:
    """Test extract_json."""
    
    def test_direct_json(self):
        result = extract_json('{"name": "test"}')
        assert result["name"] == "test"
    
    def test_json_in_code_block(self):
        text = 'Here is the result:\n```json\n{"name": "test"}\n```'
        result = extract_json(text)
        assert result["name"] == "test"
    
    def test_json_with_surrounding_text(self):
        text = 'The analysis shows: {"diagnoses": []} and that is all.'
        result = extract_json(text)
        assert "diagnoses" in result
    
    def test_truncated_json(self):
        text = '{"diagnoses": [{"name": "Test", "probability": "high"'
        result = extract_json(text)
        assert result["diagnoses"][0]["name"] == "Test"
    
    def test_no_json_raises(self):
        with pytest.raises(Exception):  # HTTPException
            extract_json("This has no JSON at all")
    
    def test_json_with_trailing_comma(self):
        text = '{"diagnoses": [{"name": "A",},]}'
        # Should handle trailing commas
        result = extract_json(text)
        assert result["diagnoses"][0]["name"] == "A"
    
    def test_regex_fallback_extracts_diagnoses(self):
        # Heavily malformed but contains diagnosis objects
        text = '{"diagnoses": [{"name": "Test Dx", "probability": "high"} BROKEN'
        result = extract_json(text)
        assert any(d.get("name") == "Test Dx" for d in result.get("diagnoses", []))
