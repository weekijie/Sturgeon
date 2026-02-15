"""
Prompt templates for MedGemma
Note: All JSON example braces are doubled ({{ }}) to escape them for .format()
"""

# --- RAG: Guideline Elicitation ---

GUIDELINE_ELICITATION_PROMPT = """You are a diagnostic AI assistant with access to clinical guidelines.

Before answering this medical question, recall relevant guidelines from:
- IDSA (Infectious Disease Society of America)
- CDC (Centers for Disease Control)
- American Thoracic Society

When citing guidelines in your response, use this EXACT format:
"(IDSA Guidelines for Community-Acquired Pneumonia, 2023)" or
"(CDC Legionella Guidelines, 2024)" or
"(ATS/IDSA Guidelines for Severe CAP, 2022)"

Always cite the specific guideline when making clinical recommendations.

Question: {question}
Clinical Context: {context}

Provide your analysis with inline citations:"""

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

Example input/output:
Input: "WBC 11.2 x10^9/L (4.0-11.0), Hemoglobin 14.5 g/dL (13.5-17.5), CRP 45 mg/L (0-5)"
Output:
{{
  "lab_values": {{
    "WBC": {{"value": 11.2, "unit": "x10^9/L", "reference": "4.0-11.0", "status": "high"}},
    "Hemoglobin": {{"value": 14.5, "unit": "g/dL", "reference": "13.5-17.5", "status": "normal"}},
    "CRP": {{"value": 45, "unit": "mg/L", "reference": "0-5", "status": "high"}}
  }},
  "abnormal_values": ["WBC", "CRP"]
}}

Report:
{lab_report_text}

JSON Response:"""

DIFFERENTIAL_PROMPT = """Based on the following case, generate 3-4 differential diagnoses.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

Before generating diagnoses, think step by step:
1. What are the key abnormal findings?
2. What conditions could explain ALL of these findings together?
3. What conditions explain only SOME findings (and which findings argue against them)?

Then provide your differential in this EXACT JSON format. Keep evidence phrases SHORT (under 15 words each).
Return ONLY valid JSON, no extra text.

Example:
{{
  "diagnoses": [
    {{
      "name": "Iron Deficiency Anemia",
      "probability": "high",
      "supporting_evidence": ["Low hemoglobin at 8.2 g/dL", "Low ferritin at 12 ng/mL", "Fatigue and pallor reported"],
      "against_evidence": ["Normal MCV could suggest other type"],
      "suggested_tests": ["Iron studies", "Reticulocyte count"]
    }},
    {{
      "name": "Chronic Disease Anemia",
      "probability": "medium",
      "supporting_evidence": ["Low hemoglobin with elevated CRP", "History of chronic inflammation"],
      "against_evidence": ["Ferritin typically normal or elevated in ACD"],
      "suggested_tests": ["TIBC", "Serum iron"]
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

Image Analysis (if available):
{image_context}

The clinician challenges your thinking:
"{user_challenge}"

Respond by:
1. Acknowledging the point if valid
2. Defending your reasoning with evidence, or updating it
3. Providing an updated differential if warranted
4. Suggesting a test if it would help clarify

When making clinical recommendations, cite relevant guidelines using this format:
"(IDSA Guidelines for Community-Acquired Pneumonia, 2023)" or
"(CDC Legionella Guidelines, 2024)" or
"(ATS/IDSA Guidelines for Severe CAP, 2022)"

Be conversational but precise. Return as JSON with this EXACT format:
{{
  "ai_response": "Your conversational response to the challenge",
  "updated_differential": [
    {{
      "name": "Diagnosis Name",
      "probability": "high|medium|low",
      "supporting_evidence": ["evidence 1", "evidence 2"],
      "against_evidence": ["counter 1"],
      "suggested_tests": ["test 1"]
    }}
  ],
  "suggested_test": "optional test name or null"
}}

JSON Response:"""


DEBATE_TURN_PROMPT_WITH_RAG = """You are in a diagnostic debate. The current case and your previous reasoning are below.

Patient History:
{patient_history}

Lab Values:
{formatted_lab_values}

Current Differential:
{current_differential}

Previous Reasoning:
{previous_rounds}

Image Analysis (if available):
{image_context}

{retrieved_guidelines}

The clinician challenges your thinking:
"{user_challenge}"

Respond by:
1. Acknowledging the point if valid
2. Defending your reasoning with evidence from the case AND the retrieved guidelines above
3. Citing specific guideline recommendations when making clinical points
4. Providing an updated differential if warranted
5. Suggesting a test if it would help clarify

CRITICAL: You MUST cite the retrieved guidelines above when making clinical recommendations. Do not hallucinate citations - only use the guidelines provided in the [RETRIEVED CLINICAL GUIDELINES] section.

When citing, use this format:
"(IDSA Guidelines for Community-Acquired Pneumonia, 2019)" or
"(CDC Legionella Clinical Guidance, 2025)" or
"(BTS CAP Guidelines, 2009)" or
"(Surviving Sepsis Campaign, 2021)"

Be conversational but precise. Return as JSON with this EXACT format:
{{
  "ai_response": "Your conversational response to the challenge with inline guideline citations",
  "updated_differential": [
    {{
      "name": "Diagnosis Name",
      "probability": "high|medium|low",
      "supporting_evidence": ["evidence 1", "evidence 2"],
      "against_evidence": ["counter 1"],
      "suggested_tests": ["test 1"]
    }}
  ],
  "suggested_test": "optional test name or null"
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

Rate confidence as "high" (>85% certainty), "medium" (50-85%), or "low" (<50%).
Also provide a confidence_percent (integer 0-100) based on:
- Strength of supporting evidence
- Number of alternative diagnoses remaining
- Whether confirmatory testing has been done

Return as JSON:
{{
  "final_diagnosis": "Diagnosis name",
  "confidence": "high|medium|low",
  "confidence_percent": 75,
  "reasoning_chain": ["step 1", "step 2", "step 3"],
  "ruled_out": ["diagnosis: reason"],
  "next_steps": ["action 1", "action 2"]
}}

JSON Response:"""
"""
"""
