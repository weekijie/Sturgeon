"""
MedGemma refusal detection and preamble stripping utilities.

MedGemma sometimes refuses to provide analysis (pure disclaimers)
or prefixes valid analysis with refusal boilerplate.  These utilities
detect and handle both cases.
"""
import re


def is_pure_refusal(text: str) -> bool:
    """Detect if MedGemma's output is a pure refusal with no real analysis.
    
    Returns True if the output is entirely disclaimers/refusal boilerplate
    (e.g. "I am an AI and cannot provide medical advice.") with no
    substantive clinical content.  Returns False if there IS useful
    analysis — even if it starts with a disclaimer prefix.
    
    This is used to trigger a retry with a simpler prompt, NOT to
    strip disclaimers from otherwise good output.  Medical AI
    disclaimers are appropriate and should be shown to users.
    """
    disclaimer_patterns = [
        r"(?:^|\n)\s*(?:I am|I'm) (?:a |an )?(?:large )?(?:language model|AI|artificial intelligence)[^.]*\.\s*",
        r"(?:^|\n)\s*As an AI(?:\s+language model)?[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I'm not|I am not) a (?:medical |healthcare )?(?:professional|doctor|physician)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I cannot|I can't) provide (?:a )?(?:clinical |medical )?(?:interpretation|diagnosis|analysis)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:This|The following) is not (?:intended as )?medical advice[^.]*\.\s*",
        r"(?:^|\n)\s*(?:It is (?:essential|important) to |Please |Always )?consult (?:with )?(?:a |your )?(?:qualified )?(?:healthcare|medical) (?:professional|provider|doctor)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I cannot|I can't) (?:provide|give|offer) medical (?:advice|diagnosis|treatment)[^.]*\.\s*",
        r"(?:^|\n)\s*(?:I am unable|I'm unable) to provide (?:a )?(?:medical )?(?:diagnosis|interpretation|clinical interpretation)[^.]*\.\s*",
        r"(?:^|\n)\s*This is because I (?:am|'m) an AI[^.]*\.\s*",
        r"(?:^|\n)\s*Analyzing medical images requires[^.]*\.\s*",
        r"(?:^|\n)\s*If you have a medical image[^.]*\.\s*",
        r"(?:^|\n)\s*They can properly[^.]*\.\s*",
        r"(?:^|\n)\s*\*{0,2}Disclaimer\*{0,2}:?\s*.*",
        r"(?:^|\n)\s*(?:Important|Note):?\s*(?:I am|I'm|This is) (?:not |an )?(?:AI|a substitute)[^.]*\.\s*",
    ]
    
    cleaned = text
    for pattern in disclaimer_patterns:
        flags = re.IGNORECASE | re.DOTALL if 'Disclaimer' in pattern else re.IGNORECASE
        cleaned = re.sub(pattern, '\n', cleaned, flags=flags)
    
    # Clean up excess whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    
    # If less than 50 chars remain after removing all disclaimers,
    # the model produced no real analysis — it's a pure refusal.
    return len(cleaned) < 50


def strip_refusal_preamble(text: str) -> str:
    """Strip leading refusal boilerplate when real analysis follows.
    
    Handles the 'refusal sandwich' pattern where MedGemma outputs:
      "I am unable to provide a clinical interpretation... However,
       I can provide a general description: [actual analysis]"
    
    Only strips the LEADING refusal prefix.  Trailing disclaimers
    (e.g. "Disclaimer: This is not medical advice") are kept as-is — 
    they are appropriate for a medical AI.
    
    Returns the original text unchanged if no preamble pattern is found.
    """
    # Pattern: refusal text ending with a "However" / "That said" transition
    # that introduces the real analysis.
    preamble_pattern = re.compile(
        r'^.*?'                                  # refusal text (non-greedy)
        r'(?:However|That said|Nevertheless|With that (?:said|in mind)),?\s*'  # transition
        r'(?:I can |I am able to |here is |below is )?',  # optional lead-in
        re.IGNORECASE | re.DOTALL
    )
    
    match = preamble_pattern.match(text)
    if match:
        remaining = text[match.end():]
        # Only strip if there's substantial content after the preamble
        if len(remaining.strip()) > 100:
            # Capitalize the first letter of the remaining text
            cleaned = remaining.strip()
            if cleaned:
                cleaned = cleaned[0].upper() + cleaned[1:]
            return cleaned
    
    return text
