"""
Text formatting utilities for clinical data display.

Converts structured data (lab values, differentials, debate rounds)
into human-readable text for MedGemma prompts.
"""


def format_lab_values(lab_values: dict) -> str:
    """Format lab values dict into readable text."""
    lines = []
    for name, data in lab_values.items():
        if isinstance(data, dict):
            value = data.get('value', 'N/A')
            unit = data.get('unit', '')
            status = data.get('status', 'normal')
            lines.append(f"- {name}: {value} {unit} ({status})")
        else:
            lines.append(f"- {name}: {data}")
    return "\n".join(lines) if lines else "No lab values provided"


def format_differential(diagnoses: list) -> str:
    """Format differential list into readable text."""
    lines = []
    for i, dx in enumerate(diagnoses, 1):
        if isinstance(dx, dict):
            name = dx.get('name', 'Unknown')
            prob = dx.get('probability', 'unknown')
            lines.append(f"{i}. {name} (probability: {prob})")
        elif hasattr(dx, 'name'):
            lines.append(f"{i}. {dx.name} (probability: {dx.probability})")
    return "\n".join(lines) if lines else "No differential yet"


def format_rounds(rounds: list) -> str:
    """Format debate rounds into readable text."""
    lines = []
    for i, r in enumerate(rounds, 1):
        challenge = r.get('user_challenge', r.get('challenge', ''))
        response = r.get('ai_response', r.get('response', ''))
        lines.append(f"Round {i}:\nUser: {challenge}\nAI: {response}")
    return "\n\n".join(lines) if lines else "No previous rounds"
