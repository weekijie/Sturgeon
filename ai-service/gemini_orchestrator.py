"""
Gemini Orchestrator - Manages multi-turn debate using Gemini as conversation
manager and MedGemma as a callable medical specialist tool.

Architecture:
  - Gemini (Pro/Flash) = Orchestrator. Manages conversation context, summarizes
    debate state, formulates focused questions for MedGemma.
  - MedGemma 4B-it = Medical Specialist (callable tool). Handles clinical
    reasoning, differential diagnosis, evidence analysis.

This maps to the Agentic Workflow Prize: "deploying HAI-DEF models as
intelligent agents or callable tools."
"""
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clinical State -- compact structured representation of the debate
# ---------------------------------------------------------------------------

@dataclass
class ClinicalState:
    """Structured clinical state that evolves each turn.
    
    This keeps prompt size constant regardless of how many debate rounds
    have occurred, because Gemini summarizes the state each turn rather
    than stuffing all previous rounds into the prompt.
    """
    patient_history: str = ""
    lab_values: dict = field(default_factory=dict)
    differential: list[dict] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    ruled_out: list[str] = field(default_factory=list)
    debate_round: int = 0
    image_context: str = ""  # MedSigLIP triage + MedGemma interpretation
    
    def to_summary(self) -> str:
        """Produce a compact text summary for Gemini's context."""
        lines = [
            f"=== Clinical State (Round {self.debate_round}) ===",
            f"Patient: {self.patient_history[:500]}",
        ]
        if self.lab_values:
            labs = []
            for name, data in self.lab_values.items():
                if isinstance(data, dict):
                    val = data.get("value", "N/A")
                    unit = data.get("unit", "")
                    status = data.get("status", "normal")
                    labs.append(f"  {name}: {val} {unit} ({status})")
                else:
                    labs.append(f"  {name}: {data}")
            lines.append("Labs:\n" + "\n".join(labs))
        
        if self.image_context:
            lines.append(f"Medical Image Analysis:\n{self.image_context}")
        
        if self.differential:
            diff_lines = []
            for i, dx in enumerate(self.differential, 1):
                name = dx.get("name", "Unknown")
                prob = dx.get("probability", "?")
                diff_lines.append(f"  {i}. {name} [{prob}]")
            lines.append("Current Differential:\n" + "\n".join(diff_lines))
        
        if self.key_findings:
            lines.append("Key Findings: " + "; ".join(self.key_findings[-5:]))
        
        if self.ruled_out:
            lines.append("Ruled Out: " + ", ".join(self.ruled_out))
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ClinicalState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Gemini Orchestrator
# ---------------------------------------------------------------------------

# System instruction for Gemini's orchestrator role
ORCHESTRATOR_SYSTEM_INSTRUCTION = """You are the orchestrator of a diagnostic debate AI called Sturgeon.

Your role:
1. MANAGE the multi-turn conversation with the user (a clinician challenging diagnoses)
2. ROUTE medical questions to your specialist tool (MedGemma) by formulating focused, single-turn clinical questions
3. SYNTHESIZE MedGemma's analysis into conversational, evidence-based responses
4. MAINTAIN and UPDATE the clinical state (differential diagnoses, key findings, ruled-out conditions)

You have access to a medical specialist AI (MedGemma) that excels at:
- Analyzing clinical evidence
- Generating differential diagnoses  
- Evaluating diagnostic probability based on evidence
- Suggesting confirmatory tests

When the user challenges a diagnosis:
1. Understand what they're actually asking/challenging
2. Formulate a focused medical question for MedGemma that addresses the challenge
3. Use MedGemma's response to craft your reply
4. Update the differential based on the new evidence/reasoning

IMPORTANT RULES:
- Always cite specific clinical evidence (e.g., "Based on the ferritin of 847...")
- Be conversational but precise -- you're a senior diagnostician leading a case discussion
- Acknowledge valid challenges and update your reasoning accordingly
- If the user raises a point that changes the differential, reflect that in the updated diagnoses
- When defending a diagnosis, provide specific evidence, not vague claims

You must ALWAYS respond with valid JSON in this exact format:
{
  "ai_response": "Your conversational response to the user's challenge",
  "updated_differential": [
    {
      "name": "Diagnosis Name",
      "probability": "high|medium|low",
      "supporting_evidence": ["evidence 1", "evidence 2"],
      "against_evidence": ["counter 1"],
      "suggested_tests": ["test 1"]
    }
  ],
  "suggested_test": "optional test name or null",
  "medgemma_query": "The focused question you asked MedGemma (for transparency)",
  "key_findings_update": ["any new key findings from this round"],
  "newly_ruled_out": ["any diagnoses ruled out this round"]
}"""


class GeminiOrchestrator:
    """Orchestrates the diagnostic debate using Gemini for conversation
    management and MedGemma for medical reasoning."""
    
    def __init__(self, medgemma_model=None):
        self.client = None
        self.medgemma = medgemma_model
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    
    def initialize(self, api_key: str = None):
        """Initialize the Gemini client."""
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "No Gemini API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                "environment variable, or pass api_key to initialize()."
            )
        
        self.client = genai.Client(api_key=key, http_options={"timeout": 60000})
        logger.info(f"Gemini orchestrator initialized with model: {self._model_name}")
    
    def _query_medgemma(self, question: str, clinical_context: str) -> str:
        """Send a focused, single-turn question to MedGemma.
        
        This is the core "tool call" pattern -- Gemini formulates the question,
        MedGemma provides the medical analysis.
        """
        if self.medgemma is None:
            raise RuntimeError("MedGemma model not attached to orchestrator")
        
        system_prompt = (
            "You are a medical specialist AI. Answer the following clinical "
            "question precisely and concisely. Cite specific evidence from the "
            "case when making claims. Return structured analysis."
        )
        
        full_prompt = f"""Clinical Context:
{clinical_context}

Question:
{question}

Provide a focused, evidence-based analysis. Be specific about which findings support or argue against each possibility."""
        
        logger.info(f"MedGemma query: {question[:100]}...")
        response = self.medgemma.generate(
            full_prompt,
            system_prompt=system_prompt,
            max_new_tokens=2048,
            temperature=0.4,
        )
        logger.info(f"MedGemma response: {len(response)} chars")
        return response
    
    def process_debate_turn(
        self,
        user_challenge: str,
        clinical_state: ClinicalState,
        previous_rounds: list[dict] = None,
    ) -> dict:
        """Process a single debate turn through the Gemini orchestrator.
        
        Flow:
        1. Gemini receives: user challenge + clinical state summary
        2. Gemini formulates a focused question for MedGemma
        3. MedGemma answers the focused question
        4. Gemini synthesizes everything into a response + updated differential
        
        Args:
            user_challenge: The user's challenge/question
            clinical_state: Current structured clinical state
            previous_rounds: Last few rounds for immediate context (max 3)
            
        Returns:
            dict with ai_response, updated_differential, suggested_test, etc.
        """
        if self.client is None:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")
        
        clinical_state.debate_round += 1
        state_summary = clinical_state.to_summary()
        
        # --- Step 1: Ask Gemini to formulate a MedGemma query ---
        query_prompt = self._build_query_formulation_prompt(
            user_challenge, state_summary, previous_rounds
        )
        
        query_response = self.client.models.generate_content(
            model=self._model_name,
            contents=query_prompt,
            config=types.GenerateContentConfig(
                system_instruction=ORCHESTRATOR_SYSTEM_INSTRUCTION,
                temperature=0.3,
                max_output_tokens=512,
            ),
        )
        
        medgemma_question = query_response.text.strip()
        logger.info(f"Gemini formulated MedGemma question: {medgemma_question[:150]}...")
        
        # --- Step 2: Query MedGemma with the focused question ---
        medgemma_analysis = self._query_medgemma(medgemma_question, state_summary)
        
        # --- Step 3: Ask Gemini to synthesize the final response ---
        synthesis_prompt = self._build_synthesis_prompt(
            user_challenge, state_summary, medgemma_question,
            medgemma_analysis, previous_rounds
        )
        
        synthesis_response = self.client.models.generate_content(
            model=self._model_name,
            contents=synthesis_prompt,
            config=types.GenerateContentConfig(
                system_instruction=ORCHESTRATOR_SYSTEM_INSTRUCTION,
                temperature=0.5,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        
        # Parse the structured response
        result = self._parse_orchestrator_response(synthesis_response.text)
        
        # Update clinical state with new findings
        if result.get("key_findings_update"):
            clinical_state.key_findings.extend(result["key_findings_update"])
        if result.get("newly_ruled_out"):
            clinical_state.ruled_out.extend(result["newly_ruled_out"])
        if result.get("updated_differential"):
            clinical_state.differential = result["updated_differential"]
        
        return result
    
    def _build_query_formulation_prompt(
        self,
        user_challenge: str,
        state_summary: str,
        previous_rounds: list[dict] = None,
    ) -> str:
        """Build the prompt that asks Gemini to formulate a focused question
        for MedGemma."""
        
        recent_context = ""
        if previous_rounds:
            # Only include last 2 rounds for immediate context
            recent = previous_rounds[-2:]
            parts = []
            for r in recent:
                challenge = r.get("user_challenge", r.get("challenge", ""))
                response = r.get("ai_response", r.get("response", ""))
                parts.append(f"User: {challenge}\nAI: {response[:200]}...")
            recent_context = f"\nRecent conversation:\n" + "\n".join(parts)
        
        return f"""You are formulating a question for your medical specialist AI (MedGemma).

{state_summary}
{recent_context}

The clinician just said: "{user_challenge}"

Based on this challenge, formulate a SINGLE, FOCUSED medical question for MedGemma to analyze.
The question should:
- Address the specific clinical concern raised by the user
- Reference relevant evidence from the case
- Be answerable from the clinical data available
- Help you determine whether to update the differential

Respond with ONLY the question, nothing else."""
    
    def _build_synthesis_prompt(
        self,
        user_challenge: str,
        state_summary: str,
        medgemma_question: str,
        medgemma_analysis: str,
        previous_rounds: list[dict] = None,
    ) -> str:
        """Build the prompt that asks Gemini to synthesize MedGemma's analysis
        into a conversational response."""
        
        recent_context = ""
        if previous_rounds:
            recent = previous_rounds[-2:]
            parts = []
            for r in recent:
                challenge = r.get("user_challenge", r.get("challenge", ""))
                response = r.get("ai_response", r.get("response", ""))
                parts.append(f"User: {challenge}\nAI: {response[:300]}")
            recent_context = f"\nRecent conversation:\n" + "\n".join(parts)
        
        return f"""{state_summary}
{recent_context}

The clinician challenged: "{user_challenge}"

You asked your medical specialist: "{medgemma_question}"

MedGemma's analysis:
{medgemma_analysis}

Now synthesize this into your response. You must:
1. Address the user's challenge directly and conversationally
2. Incorporate MedGemma's analysis with specific evidence citations
3. Update the differential if warranted by the analysis
4. Suggest a test if it would help clarify

CRITICAL: The "ai_response" field must be a plain conversational text string, NOT a JSON object or nested JSON. Write it as you would speak to a colleague."""
    
    def _parse_orchestrator_response(self, text: str) -> dict:
        """Parse Gemini's JSON response with fallback handling.
        
        Handles a known issue where Gemini sometimes double-wraps JSON:
        the ai_response field contains a JSON string instead of plain text.
        """
        import re
        
        # Try to find JSON in code blocks first
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            text = json_match.group(1)
        
        # Find the first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end + 1]
        
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            # Attempt to repair common JSON errors (e.g., missing commas between fields)
            try:
                import re
                # Insert missing commas between quote-key pairs
                fixed_text = re.sub(r'"\s*\n\s*"', '",\n"', text)
                data = json.loads(fixed_text)
                logger.info("Successfully repaired malformed JSON (missing commas)")
            except json.JSONDecodeError:
                logger.error(f"Failed to parse Gemini response: {e}\nText: {text[:500]}")
                # Return a safe fallback
                data = {
                    "ai_response": text[:500] if text else "I need to reconsider this case.",
                    "updated_differential": [],
                    "suggested_test": None,
                }
        
        # Fix double-wrapped JSON: if ai_response is itself a JSON string
        # containing the expected fields, unwrap it
        ai_response = data.get("ai_response", "")
        if isinstance(ai_response, str) and ai_response.strip().startswith("{"):
            try:
                inner = json.loads(ai_response)
                if isinstance(inner, dict) and "ai_response" in inner:
                    logger.warning("Detected double-wrapped JSON in Gemini response, unwrapping")
                    # Merge inner data into outer, preferring inner values
                    data.update(inner)
            except (json.JSONDecodeError, TypeError):
                # Partial JSON string -- strip the { "ai_response": " prefix
                stripped = re.sub(
                    r'^\s*\{\s*"ai_response"\s*:\s*"?',
                    '',
                    ai_response
                )
                # Also strip trailing incomplete JSON
                stripped = re.sub(r'"\s*,?\s*"(updated_differential|suggested_test|medgemma_query).*$', '', stripped)
                stripped = stripped.rstrip('"}{ \n')
                if stripped:
                    data["ai_response"] = stripped
        
        # Ensure ai_response is always a plain string, not a dict
        if isinstance(data.get("ai_response"), dict):
            logger.warning("ai_response is a dict, extracting text")
            inner = data["ai_response"]
            data["ai_response"] = inner.get("ai_response", json.dumps(inner))
        
        # Final cleanup: strip any remaining JSON key prefix from ai_response
        final = data.get("ai_response", "")
        if isinstance(final, str):
            prefix_match = re.match(r'^\s*\{\s*"ai_response"\s*:\s*"?(.*)$', final, re.DOTALL)
            if prefix_match:
                data["ai_response"] = prefix_match.group(1).rstrip('"}')
        
        return data


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_orchestrator_instance: Optional[GeminiOrchestrator] = None


def get_orchestrator() -> GeminiOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = GeminiOrchestrator()
    return _orchestrator_instance
