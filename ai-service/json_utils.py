"""
Robust JSON extraction and repair utilities for MedGemma/Gemini model output.

Handles: markdown code blocks, truncated JSON, missing commas,
trailing commas, unbalanced braces, and literal newlines in strings.
"""
import json
import re
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)


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


def _fix_newlines_in_json_strings(text: str) -> str:
    """Replace literal newlines inside JSON string values with spaces.
    
    Walks the text character-by-character, tracking whether we're inside
    a quoted string.  Any \\n found inside a string is replaced with a space.
    This is more robust than regex which can't reliably detect string boundaries
    (e.g. newlines after punctuation like '),' were missed by the old approach).
    """
    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_string and i + 1 < len(text):
            # Escaped character inside string — keep both chars as-is
            result.append(c)
            result.append(text[i + 1])
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        if c == '\n' and in_string:
            result.append(' ')
        else:
            result.append(c)
        i += 1
    return ''.join(result)


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
    
    # Pre-process: fix literal newlines inside JSON string values.
    # MedGemma wraps long strings across lines (e.g. reasoning_chain entries),
    # which is invalid JSON.  Walk the text tracking quote boundaries and
    # replace any \n found inside a string with a space.
    text = _fix_newlines_in_json_strings(text)
    
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
