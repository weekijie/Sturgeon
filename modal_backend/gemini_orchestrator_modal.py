"""
Gemini Orchestrator for Modal - Manages multi-turn debate using Gemini as conversation
manager and vLLM-hosted MedGemma as a callable medical specialist tool.

This version uses HTTP calls to vLLM instead of direct model access.
"""
import os
import json
import logging
import re
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple

import httpx
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 180.0

GUIDELINE_URLS: Dict[str, str] = {
    "WHO_MENINGITIS": "https://www.who.int/publications/i/item/9789240108042",
    "WHO_TB": "https://www.ncbi.nlm.nih.gov/books/NBK607290/",
    "WHO_HEPATITIS_B": "https://www.who.int/publications/i/item/9789240090903",
    "WHO": "https://www.who.int/publications/i/",
    "CDC_SEPSIS": "https://www.cdc.gov/sepsis/hcp/core-elements/index.html",
    "CDC_LEGIONELLA": "https://www.cdc.gov/legionella/hcp/clinical-guidance/index.html",
    "CDC_RESPIRATORY": "https://www.cdc.gov/respiratory-viruses/guidance/index.html",
    "CDC": "https://www.cdc.gov/",
    "USPSTF_BREAST": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/breast-cancer-screening",
    "USPSTF_COLORECTAL": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/colorectal-cancer-screening",
    "USPSTF_DIABETES": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/screening-for-prediabetes-and-type-2-diabetes",
    "USPSTF_CARDIO": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/statin-use-in-adults-preventive-medication",
    "USPSTF": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics",
    "PMC": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7112285/",
    "PubMed": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7112285/",
    "IDSA": "https://www.idsociety.org/practice-guideline/community-acquired-pneumonia-cap-in-adults/",
    "ATS": "https://www.thoracic.org/practice-guidelines/",
    "ATS/IDSA": "https://www.idsociety.org/practice-guideline/community-acquired-pneumonia-cap-in-adults/",
    "BTS": "https://www.brit-thoracic.org.uk/document-library/guidelines/pneumonia-adults/",
    "SCCM": "https://www.sccm.org/survivingsepsiscampaign/guidelines-and-resources/",
    "ESICM": "https://www.esicm.org/guidelines/",
    "SSC": "https://www.sccm.org/survivingsepsiscampaign/guidelines-and-resources/",
    "NCCN": "https://www.nccn.org/guidelines/",
    "ASCO": "https://www.asco.org/practice-patients/guidelines",
    "ESMO": "https://www.esmo.org/guidelines",
    "AAD_MELANOMA": "https://www.guidelinecentral.com/guideline/21823/",
    "AAD": "https://www.aad.org/clinical-guidelines",
    "ACR": "https://www.acr.org/Clinical-Resources/ACR-Appropriateness-Criteria",
    "ADA": "https://professional.diabetes.org/guidelines-recommendations",
    "AHA": "https://professional.heart.org/guidelines-and-statements",
    "ACC": "https://www.acc.org/guidelines",
    "CHEST": "https://www.chestnet.org/guidelines-and-research",
    "NICE": "https://www.nice.org.uk/guidance",
}


def extract_citations(text: str) -> Tuple[str, List[Dict]]:
    """Extract clinical guideline citations from AI response text."""
    citations = []
    seen_spans = set()
    
    ORGS = r'WHO_MENINGITIS|WHO_HEPATITIS_B|WHO_TB|CDC_LEGIONELLA|CDC_RESPIRATORY|CDC_SEPSIS|USPSTF_COLORECTAL|USPSTF_DIABETES|USPSTF_CARDIO|USPSTF_BREAST|AAD_MELANOMA|USPSTF|SCCM|ESICM|CHEST|NCCN|ASCO|ESMO|AAD|ACR|ADA|AHA|ACC|IDSA|CDC|ATS|WHO|NICE|BTS|PMC|PubMed|SSC'
    COMBO_ORGS = r'ATS/IDSA|ACC/AHA|Surviving Sepsis Campaign'
    
    ORG_ALIASES = {
        "WORLD HEALTH ORGANIZATION MENINGITIS": "WHO_MENINGITIS",
        "WHO MENINGITIS": "WHO_MENINGITIS",
        "WORLD HEALTH ORGANIZATION TB": "WHO_TB",
        "WORLD HEALTH ORGANIZATION TUBERCULOSIS": "WHO_TB",
        "WHO TB": "WHO_TB",
        "WORLD HEALTH ORGANIZATION HEPATITIS B": "WHO_HEPATITIS_B",
        "WHO HEPATITIS B": "WHO_HEPATITIS_B",
        "CDC SEPSIS": "CDC_SEPSIS",
        "CDC HOSPITAL SEPSIS": "CDC_SEPSIS",
        "CDC LEGIONELLA": "CDC_LEGIONELLA",
        "CDC RESPIRATORY": "CDC_RESPIRATORY",
        "CDC RESPIRATORY VIRUS": "CDC_RESPIRATORY",
        "US PREVENTIVE SERVICES TASK FORCE BREAST": "USPSTF_BREAST",
        "USPSTF BREAST": "USPSTF_BREAST",
        "USPSTF COLORECTAL": "USPSTF_COLORECTAL",
        "USPSTF DIABETES": "USPSTF_DIABETES",
        "USPSTF STATIN": "USPSTF_CARDIO",
        "USPSTF CARDIOVASCULAR": "USPSTF_CARDIO",
        "AAD MELANOMA": "AAD_MELANOMA",
        "AAD MELANOMA GUIDELINES": "AAD_MELANOMA",
        "AMERICAN ACADEMY OF DERMATOLOGY MELANOMA": "AAD_MELANOMA",
        "PRIMARY CARE CLINICS": "PMC",
        "PUBMED CENTRAL": "PMC",
        "BRITISH THORACIC SOCIETY": "BTS",
        "INFECTIOUS DISEASES SOCIETY OF AMERICA": "IDSA",
        "AMERICAN THORACIC SOCIETY": "ATS",
        "CENTERS FOR DISEASE CONTROL": "CDC",
        "CENTER FOR DISEASE CONTROL": "CDC",
        "SURVIVING SEPSIS CAMPAIGN": "SSC",
        "SOCIETY OF CRITICAL CARE MEDICINE": "SCCM",
        "EUROPEAN SOCIETY OF INTENSIVE CARE MEDICINE": "ESICM",
        "US PREVENTIVE SERVICES TASK FORCE": "USPSTF",
        "WORLD HEALTH ORGANIZATION": "WHO",
    }
    
    citation_pattern1 = rf'\((?:the\s+)?({COMBO_ORGS}|{ORGS})\b[^)]{{0,150}}?(?:Guidelines?|Consensus\s+Guidelines|Standards?|Appropriateness\s+Criteria|recommendations?|guidance|Criteria|Statements?)\b[^)]{{0,100}}?\d{{4}}[^)]{{0,10}}?\)'
    attribution_pattern = rf'(?:According to|Per|Based on|Following)\s+(?:the\s+)?({COMBO_ORGS}|{ORGS})\b[^,.]{{0,100}}?(?:Guidelines?|Standards?|recommendations?|guidance|criteria)[^,.]{{0,60}}?\d{{4}}'
    simple_pattern = rf'\(({COMBO_ORGS}|{ORGS})[/,\s]+\d{{4}}\)'
    alias_names = "|".join(re.escape(alias) for alias in ORG_ALIASES.keys())
    alias_pattern = rf'\((?:the\s+)?({alias_names})[^)]*?\d{{4}}[^)]*?\)'
    attribution_alias_pattern = rf'(?:According to|Per|Based on|Following)\s+(?:the\s+)?({alias_names})[^,.]{{0,100}}?\d{{4}}'
    
    all_matches = []
    
    for pattern in [citation_pattern1, attribution_pattern, simple_pattern, alias_pattern, attribution_alias_pattern]:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            span = (match.start(), match.end())
            overlap = False
            for existing_span in seen_spans:
                if not (span[1] <= existing_span[0] or span[0] >= existing_span[1]):
                    overlap = True
                    break
            
            if not overlap:
                all_matches.append((span, match.group(0)))
                seen_spans.add(span)
    
    for span, citation_text in all_matches:
        citation_upper = citation_text.upper()
        source = "Unknown"
        url = ""
        
        for alias, canonical in ORG_ALIASES.items():
            if alias in citation_upper:
                source = canonical
                url = GUIDELINE_URLS.get(canonical, "")
                break
        
        if source == "Unknown":
            if "ATS/IDSA" in citation_upper or ("ATS" in citation_upper and "IDSA" in citation_upper):
                source = "ATS/IDSA"
                url = GUIDELINE_URLS.get("ATS/IDSA", GUIDELINE_URLS.get("ATS", ""))
            elif "CDC" in citation_upper:
                source = "CDC"
                url = GUIDELINE_URLS.get("CDC", "")
            elif "WHO" in citation_upper:
                source = "WHO"
                url = GUIDELINE_URLS.get("WHO", "")
            elif "USPSTF" in citation_upper:
                source = "USPSTF"
                url = GUIDELINE_URLS.get("USPSTF", "")
        
        citations.append({
            "text": citation_text,
            "url": url,
            "source": source
        })
    
    def _normalize_citation_key(c: dict) -> str:
        text = c["text"]
        text = re.sub(r"^\(?\s*(?:According to the|Per the|Based on the)\s+", "", text, flags=re.IGNORECASE)
        year_match = re.search(r"\d{4}", text)
        year = year_match.group(0) if year_match else ""
        return f"{c['source']}:{year}"
    
    seen = set()
    unique_citations = []
    for c in citations:
        key = _normalize_citation_key(c)
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)
    
    return text, unique_citations


@dataclass
class ClinicalState:
    """Structured clinical state that evolves each turn."""
    patient_history: str = ""
    lab_values: dict = field(default_factory=dict)
    differential: list[dict] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    ruled_out: list[str] = field(default_factory=list)
    debate_round: int = 0
    image_context: str = ""
    episode_summaries: list[str] = field(default_factory=list)
    last_episode_round: int = 0
    
    def to_summary(self) -> str:
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
        
        return "\n".join(lines)


ORCHESTRATOR_SYSTEM_INSTRUCTION = """You are the orchestrator of a diagnostic debate AI called Sturgeon.

Your role:
1. MANAGE the multi-turn conversation with the user (a clinician challenging diagnoses)
2. ROUTE medical questions to your specialist tool (MedGemma) by formulating focused questions
3. SYNTHESIZE MedGemma's analysis into conversational, evidence-based responses
4. MAINTAIN and UPDATE the clinical state (differential diagnoses, key findings)

You must ALWAYS respond with valid JSON in this exact format:
{
  "ai_response": "Your conversational response to the user's challenge",
  "updated_differential": [
    {
      "name": "Diagnosis Name",
      "probability": "high|medium|low",
      "supporting_evidence": ["evidence 1"],
      "against_evidence": ["counter 1"],
      "suggested_tests": ["test 1"]
    }
  ],
  "suggested_test": "optional test name or null",
  "medgemma_query": "The focused question you asked MedGemma",
  "key_findings_update": ["any new key findings"],
  "newly_ruled_out": ["any diagnoses ruled out"]
}"""


class GeminiOrchestrator:
    """Orchestrates diagnostic debate using Gemini + vLLM-hosted MedGemma."""
    
    def __init__(self):
        self.client = None
        self.vllm_base_url = "http://localhost:6501"
        self.http_client = httpx.AsyncClient(timeout=120.0)
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    
    def initialize(self, api_key: str = None):
        """Initialize Gemini client."""
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("No Gemini API key found.")
        
        timeout_ms = int(DEFAULT_TIMEOUT_SECONDS * 1000)
        self.client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=timeout_ms)
        )
        logger.info(f"Gemini orchestrator initialized: {self._model_name}")
    
    async def query_medgemma(self, question: str, clinical_context: str) -> str:
        """Send question to MedGemma via vLLM."""
        system_prompt = (
            "You are a medical specialist AI. Answer the following clinical "
            "question precisely and concisely. Cite specific evidence."
        )
        
        full_prompt = f"""Clinical Context:
{clinical_context}

Question:
{question}

Provide a focused, evidence-based analysis."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ]
        
        response = await self.http_client.post(
            f"{self.vllm_base_url}/v1/chat/completions",
            json={
                "model": "google/medgemma-1.5-4b-it",
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.4,
            }
        )
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    def process_debate_turn(
        self,
        user_challenge: str,
        clinical_state: ClinicalState,
        previous_rounds: list[dict] = None,
        retrieved_context: str = "",
    ) -> dict:
        """Process debate turn via Gemini orchestration."""
        if self.client is None:
            raise RuntimeError("Orchestrator not initialized.")
        
        clinical_state.debate_round += 1
        state_summary = clinical_state.to_summary()
        
        query_prompt = f"""You are formulating a question for your medical specialist AI (MedGemma).

{state_summary}

The clinician just said: "{user_challenge}"

Based on this, formulate a SINGLE, FOCUSED medical question for MedGemma.
Respond with ONLY the question, nothing else."""
        
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
        logger.info(f"MedGemma question: {medgemma_question[:100]}...")
        
        medgemma_analysis = asyncio.run(
            self.query_medgemma(medgemma_question, state_summary)
        )
        
        synthesis_prompt = f"""{state_summary}

The clinician challenged: "{user_challenge}"

You asked your medical specialist: "{medgemma_question}"

MedGemma's analysis:
{medgemma_analysis}

Now synthesize this into your response. Return valid JSON."""
        
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
        
        result = self._parse_response(synthesis_response.text)
        
        _, citations = extract_citations(result.get("ai_response", ""))
        result["citations"] = citations
        result["has_guidelines"] = len(citations) > 0
        
        if result.get("updated_differential"):
            clinical_state.differential = result["updated_differential"]
        
        return result
    
    def _parse_response(self, text: str) -> dict:
        """Parse Gemini JSON response."""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            text = json_match.group(1)
        
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end + 1]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "ai_response": text[:500],
                "updated_differential": [],
                "suggested_test": None,
            }


_orchestrator_instance: Optional[GeminiOrchestrator] = None


def get_orchestrator() -> GeminiOrchestrator:
    """Get or create orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = GeminiOrchestrator()
    return _orchestrator_instance
