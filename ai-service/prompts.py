"""
Prompt templates for MedGemma
Note: All JSON example braces are doubled ({{ }}) to escape them for .format()
"""

SYSTEM_PROMPT = """You are a diagnostic team member in a clinical case discussion. Your role is to:
1. Analyze clinical evidence carefully
2. Generate and defend differential diagnoses
3. Acknowledge valid challenges and update your reasoning
4. Explain your thinking clearly

Always cite specific evidence from the case when making claims.
Use phrases like "Based on the elevated ferritin of 847..." not just "The labs suggest..."
"""

EXTRACT_LABS_PROMPT = """Extract all lab values from the following report. For each value, provide:
- Test name
- Value
- Unit
- Reference range (if available)
- Whether it is abnormal (high/low/normal)

Return as structured JSON with this format:
{{
  "lab_values": {{
    "test_name": {{"value": number, "unit": "string", "reference": "string", "status": "normal|high|low"}}
  }},
  "abnormal_values": ["list of abnormal test names"]
}}

Report:
{lab_report_text}

JSON Response:"""

DIFFERENTIAL_PROMPT = """Based on the following case, generate 3-4 differential diagnoses.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

For each diagnosis, provide:
1. Diagnosis name
2. Probability (high/medium/low)
3. Supporting evidence from this case
4. Evidence that argues against this diagnosis
5. Tests that would help confirm or rule out

Return as structured JSON with this format:
{{
  "diagnoses": [
    {{
      "name": "Diagnosis Name",
      "probability": "high|medium|low",
      "supporting_evidence": ["evidence 1", "evidence 2"],
      "against_evidence": ["counter 1"],
      "suggested_tests": ["test 1", "test 2"]
    }}
  ]
}}

JSON Response:"""

DEBATE_TURN_PROMPT = """You are in a diagnostic debate. The current case and your previous reasoning are below.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

Current Differential:
{current_differential}

Previous Reasoning:
{previous_rounds}

The clinician challenges your thinking:
"{user_challenge}"

Respond by:
1. Acknowledging the point if valid
2. Defending your reasoning with evidence, or updating it
3. Providing an updated differential if warranted
4. Suggesting a test if it would help clarify

Be conversational but precise. Return as JSON:
{{
  "ai_response": "Your conversational response",
  "updated_differential": [same format as differential],
  "suggested_test": "optional test name"
}}

JSON Response:"""

SUMMARY_PROMPT = """Generate a final diagnosis summary based on the case discussion.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

Final Differential:
{final_differential}

Debate History:
{debate_rounds}

Provide:
1. The most likely diagnosis with confidence level
2. The reasoning chain that led to this conclusion
3. What was ruled out and why
4. Recommended next steps

Return as JSON:
{{
  "final_diagnosis": "Diagnosis name",
  "confidence": "high|medium|low",
  "reasoning_chain": ["step 1", "step 2", "step 3"],
  "ruled_out": ["diagnosis: reason"],
  "next_steps": ["action 1", "action 2"]
}}

JSON Response:"""

