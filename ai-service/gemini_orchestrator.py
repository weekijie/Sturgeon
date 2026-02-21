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
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Timeout configuration for API calls
DEFAULT_TIMEOUT_SECONDS = 180.0


# ---------------------------------------------------------------------------
# RAG: Citation Parser
# ---------------------------------------------------------------------------

# Mapping of guideline citations to their URLs
# Sub-entries for multi-guideline orgs point to specific pages
# Generic fallback entries point to search/topics pages
# NOTE: IDSA, BTS, SSC, SCCM removed from corpus (copyrighted) but URLs kept for external citations
GUIDELINE_URLS: Dict[str, str] = {
    # WHO - Specific guidelines (check these FIRST in elif chain)
    "WHO_MENINGITIS": "https://www.who.int/publications/i/item/9789240108042",
    "WHO_TB": "https://www.ncbi.nlm.nih.gov/books/NBK607290/",
    "WHO_HEPATITIS_B": "https://www.who.int/publications/i/item/9789240090903",
    "WHO": "https://www.who.int/publications/i/",  # Fallback: search page
    # CDC - Specific guidelines
    "CDC_SEPSIS": "https://www.cdc.gov/sepsis/hcp/core-elements/index.html",
    "CDC_LEGIONELLA": "https://www.cdc.gov/legionella/hcp/clinical-guidance/index.html",
    "CDC_RESPIRATORY": "https://www.cdc.gov/respiratory-viruses/guidance/index.html",
    "CDC": "https://www.cdc.gov/",  # Fallback: homepage with search
    # USPSTF - Specific guidelines
    "USPSTF_BREAST": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/breast-cancer-screening",
    "USPSTF_COLORECTAL": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/colorectal-cancer-screening",
    "USPSTF_DIABETES": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/screening-for-prediabetes-and-type-2-diabetes",
    "USPSTF_CARDIO": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/statin-use-in-adults-preventive-medication",
    "USPSTF": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics",  # Fallback
    # PMC / PubMed
    "PMC": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7112285/",
    "PubMed": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7112285/",
    # Copyrighted - NOT in RAG corpus (external reference only)
    "IDSA": "https://www.idsociety.org/practice-guideline/community-acquired-pneumonia-cap-in-adults/",
    "ATS": "https://www.thoracic.org/practice-guidelines/",
    "ATS/IDSA": "https://www.idsociety.org/practice-guideline/community-acquired-pneumonia-cap-in-adults/",
    "BTS": "https://www.brit-thoracic.org.uk/document-library/guidelines/pneumonia-adults/",
    "SCCM": "https://www.sccm.org/survivingsepsiscampaign/guidelines-and-resources/",
    "ESICM": "https://www.esicm.org/guidelines/",
    "SSC": "https://www.sccm.org/survivingsepsiscampaign/guidelines-and-resources/",
    # Cancer / Oncology
    "NCCN": "https://www.nccn.org/guidelines/",
    "ASCO": "https://www.asco.org/practice-patients/guidelines",
    "ESMO": "https://www.esmo.org/guidelines",
    # Dermatology - Specific guidelines
    "AAD_MELANOMA": "https://www.guidelinecentral.com/guideline/21823/",
    "AAD": "https://www.aad.org/clinical-guidelines",
    "AADA": "https://www.aad.org/clinical-guidelines",
    # Radiology
    "ACR": "https://www.acr.org/Clinical-Resources/ACR-Appropriateness-Criteria",
    # Diabetes
    "ADA": "https://professional.diabetes.org/guidelines-recommendations",
    "ADAD": "https://professional.diabetes.org/guidelines-recommendations",
    # Cardiology
    "AHA": "https://professional.heart.org/guidelines-and-statements",
    "ACC": "https://www.acc.org/guidelines",
    "ACC/AHA": "https://professional.heart.org/guidelines-and-statements",
    # Pulmonary
    "CHEST": "https://www.chestnet.org/guidelines-and-research",
    # UK Guidelines
    "NICE": "https://www.nice.org.uk/guidance",
}


def extract_citations(text: str) -> Tuple[str, List[Dict]]:
    """
    Extract clinical guideline citations from AI response text.
    
    Looks for patterns like:
    - (IDSA Guidelines for Community-Acquired Pneumonia, 2023)
    - (CDC Legionella Guidelines, 2024)
    - (ATS/IDSA Guidelines for Severe CAP, 2022)
    - According to IDSA guidelines...
    - Per CDC recommendations...
    
    Returns:
        - Cleaned text (citations remain inline)
        - List of citation dicts with text, url, and source
    """
    citations = []
    seen_spans = set()  # Track (start, end) positions to avoid duplicates
    
    # All medical organizations to detect - longer/specific ones first to avoid partial matches
    # IMPORTANT: Sub-entry patterns (WHO_MENINGITIS, etc.) must come BEFORE generic fallbacks (WHO)
    ORGS = r'WHO_MENINGITIS|WHO_HEPATITIS_B|WHO_TB|CDC_LEGIONELLA|CDC_RESPIRATORY|CDC_SEPSIS|USPSTF_COLORECTAL|USPSTF_DIABETES|USPSTF_CARDIO|USPSTF_BREAST|AAD_MELANOMA|USPSTF|SCCM|ESICM|CHEST|NCCN|ASCO|ESMO|AAD|ACR|ADA|AHA|ACC|IDSA|CDC|ATS|WHO|NICE|BTS|PMC|PubMed|SSC'
    COMBO_ORGS = r'ATS/IDSA|ACC/AHA|Surviving Sepsis Campaign'
    
    # Organization aliases - map alternative names to canonical names for URL lookup
    # This handles cases where Gemini uses alternative phrasings like "Primary Care Clinics" instead of "PMC"
    # IMPORTANT: Sub-entry aliases must be checked BEFORE generic fallback aliases
    ORG_ALIASES = {
        # WHO sub-entries (check these FIRST)
        "WORLD HEALTH ORGANIZATION MENINGITIS": "WHO_MENINGITIS",
        "WHO MENINGITIS": "WHO_MENINGITIS",
        "WORLD HEALTH ORGANIZATION TB": "WHO_TB",
        "WORLD HEALTH ORGANIZATION TUBERCULOSIS": "WHO_TB",
        "WHO TB": "WHO_TB",
        "WORLD HEALTH ORGANIZATION HEPATITIS B": "WHO_HEPATITIS_B",
        "WHO HEPATITIS B": "WHO_HEPATITIS_B",
        # CDC sub-entries
        "CDC SEPSIS": "CDC_SEPSIS",
        "CDC HOSPITAL SEPSIS": "CDC_SEPSIS",
        "CDC LEGIONELLA": "CDC_LEGIONELLA",
        "CDC RESPIRATORY": "CDC_RESPIRATORY",
        "CDC RESPIRATORY VIRUS": "CDC_RESPIRATORY",
        # USPSTF sub-entries
        "US PREVENTIVE SERVICES TASK FORCE BREAST": "USPSTF_BREAST",
        "USPSTF BREAST": "USPSTF_BREAST",
        "USPSTF COLORECTAL": "USPSTF_COLORECTAL",
        "USPSTF DIABETES": "USPSTF_DIABETES",
        "USPSTF STATIN": "USPSTF_CARDIO",
        "USPSTF CARDIOVASCULAR": "USPSTF_CARDIO",
        # AAD sub-entries (check BEFORE generic AAD)
        "AAD MELANOMA": "AAD_MELANOMA",
        "AAD MELANOMA GUIDELINES": "AAD_MELANOMA",
        "AMERICAN ACADEMY OF DERMATOLOGY MELANOMA": "AAD_MELANOMA",
        # Generic fallbacks (check AFTER sub-entries)
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
        "U S PREVENTIVE SERVICES TASK FORCE": "USPSTF",
        "PREVENTIVE SERVICES TASK FORCE": "USPSTF",
        "WORLD HEALTH ORGANIZATION": "WHO",
    }
    
    # Pattern 1: Full citations in parentheses with year
    # Matches: (IDSA Guidelines for Community-Acquired Pneumonia, 2023)
    #          (ATS/IDSA Consensus Guidelines, 2021)
    #          (NCCN Melanoma Guidelines, 2024)
    #          (CDC Legionella Guidelines, 2024)
    #          (ADA Standards of Care, 2024)
    #          (ACR Appropriateness Criteria, 2022)
    citation_pattern1 = rf'\((?:the\s+)?({COMBO_ORGS}|{ORGS})\b[^)]{{0,150}}?(?:Guidelines?|Consensus\s+Guidelines|Standards?|Appropriateness\s+Criteria|recommendations?|guidance|Criteria|Statements?)\b[^)]{{0,100}}?\d{{4}}[^)]{{0,10}}?\)'
    
    # Pattern 2: Attribution phrases with year
    # Matches: "According to IDSA guidelines from 2023"
    #          "Per NCCN recommendations (2024)"
    #          "Based on WHO guidelines 2023"
    #          "Per ACR Appropriateness Criteria guidelines from 2022"
    attribution_pattern = rf'(?:According to|Per|Based on|Following)\s+(?:the\s+)?({COMBO_ORGS}|{ORGS})\b[^,.]{{0,100}}?(?:Guidelines?|Standards?|recommendations?|guidance|criteria)[^,.]{{0,60}}?\d{{4}}'
    
    # Pattern 3: Simple (Org Year) format
    # Matches: (NCCN 2024) or (IDSA, 2023)
    simple_pattern = rf'\(({COMBO_ORGS}|{ORGS})[/,\s]+\d{{4}}\)'
    
    # Pattern 4: Alternative organization names with year
    # Matches: (Primary Care Clinics, 2020) or (British Thoracic Society, 2009)
    # This catches citations using full organization names instead of acronyms
    alias_names = "|".join(re.escape(alias) for alias in ORG_ALIASES.keys())
    alias_pattern = rf'\((?:the\s+)?({alias_names})[^)]*?\d{{4}}[^)]*?\)'
    
    # Pattern 5: Attribution with alternative organization names
    # Matches: "According to Primary Care Clinics (2020)" or "Per British Thoracic Society guidelines 2009"
    attribution_alias_pattern = rf'(?:According to|Per|Based on|Following)\s+(?:the\s+)?({alias_names})[^,.]{{0,100}}?\d{{4}}'
    
    # Find all matches with their positions
    all_matches = []
    
    for pattern in [citation_pattern1, attribution_pattern, simple_pattern, alias_pattern, attribution_alias_pattern]:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Skip if this span overlaps with an already-found citation
            span = (match.start(), match.end())
            overlap = False
            for existing_span in seen_spans:
                if not (span[1] <= existing_span[0] or span[0] >= existing_span[1]):
                    overlap = True
                    break
            
            if not overlap:
                all_matches.append((span, match.group(0)))
                seen_spans.add(span)
    
    # Process unique matches
    for span, citation_text in all_matches:
        # Determine source and URL
        citation_upper = citation_text.upper()
        source = "Unknown"
        url = ""
        
        # Check organization aliases first (e.g., "Primary Care Clinics" -> PMC)
        for alias, canonical in ORG_ALIASES.items():
            if alias in citation_upper:
                source = canonical
                url = GUIDELINE_URLS.get(canonical, "")
                break
        
        # If no alias matched, check for combined organizations and individual orgs
        if source == "Unknown":
            # Check for combined organizations first (ATS/IDSA, ACC/AHA, Surviving Sepsis Campaign)
            if "ATS/IDSA" in citation_upper or ("ATS" in citation_upper and "IDSA" in citation_upper):
                source = "ATS/IDSA"
                url = GUIDELINE_URLS.get("ATS/IDSA", GUIDELINE_URLS.get("ATS", ""))
            elif "ACC/AHA" in citation_upper or ("ACC" in citation_upper and "AHA" in citation_upper):
                source = "ACC/AHA"
                url = GUIDELINE_URLS.get("ACC/AHA", GUIDELINE_URLS.get("AHA", ""))
            elif "SURVIVING SEPSIS CAMPAIGN" in citation_upper or "SSC" in citation_upper:
                source = "SSC"
                url = GUIDELINE_URLS.get("SSC", "")
            elif "SCCM" in citation_upper:
                source = "SCCM"
                url = GUIDELINE_URLS.get("SCCM", "")
            elif "ESICM" in citation_upper:
                source = "ESICM"
                url = GUIDELINE_URLS.get("ESICM", "")
            elif "BTS" in citation_upper:
                source = "BTS"
                url = GUIDELINE_URLS.get("BTS", "")
            elif "PUBMED" in citation_upper or "PMC" in citation_upper:
                source = "PMC"
                url = GUIDELINE_URLS.get("PMC", "")
            elif "ADA" in citation_upper and "AAD" in citation_upper:
                # Disambiguate: AAD (dermatology) vs ADA (diabetes)
                context_window = text[max(0, span[0] - 200):min(len(text), span[1] + 200)].upper()
                if any(word in context_window for word in ["DERMATOLOGY", "SKIN", "MELANOMA", "PSORIASIS", "ECZEMA"]):
                    source = "AAD"
                    url = GUIDELINE_URLS.get("AAD", "")
                else:
                    source = "ADA"
                    url = GUIDELINE_URLS.get("ADA", "")
            # WHO - check specific sub-entries BEFORE generic fallback
            elif "WHO MENINGITIS" in citation_upper or "MENINGITIS" in citation_upper and "WHO" in citation_upper:
                source = "WHO_MENINGITIS"
                url = GUIDELINE_URLS.get("WHO_MENINGITIS", "")
            elif "WHO TB" in citation_upper or "WHO TUBERCULOSIS" in citation_upper or ("TB" in citation_upper and "WHO" in citation_upper):
                source = "WHO_TB"
                url = GUIDELINE_URLS.get("WHO_TB", "")
            elif "WHO HEPATITIS" in citation_upper or ("HEPATITIS" in citation_upper and "WHO" in citation_upper):
                source = "WHO_HEPATITIS_B"
                url = GUIDELINE_URLS.get("WHO_HEPATITIS_B", "")
            # CDC - check specific sub-entries BEFORE generic fallback
            elif "CDC SEPSIS" in citation_upper or "HOSPITAL SEPSIS" in citation_upper:
                source = "CDC_SEPSIS"
                url = GUIDELINE_URLS.get("CDC_SEPSIS", "")
            elif "CDC LEGIONELLA" in citation_upper or "LEGIONELLA" in citation_upper:
                source = "CDC_LEGIONELLA"
                url = GUIDELINE_URLS.get("CDC_LEGIONELLA", "")
            elif "CDC RESPIRATORY" in citation_upper or "RESPIRATORY VIRUS" in citation_upper:
                source = "CDC_RESPIRATORY"
                url = GUIDELINE_URLS.get("CDC_RESPIRATORY", "")
            # USPSTF - check specific sub-entries BEFORE generic fallback
            elif "USPSTF BREAST" in citation_upper or "BREAST CANCER SCREENING" in citation_upper:
                source = "USPSTF_BREAST"
                url = GUIDELINE_URLS.get("USPSTF_BREAST", "")
            elif "USPSTF COLORECTAL" in citation_upper or "COLORECTAL CANCER" in citation_upper:
                source = "USPSTF_COLORECTAL"
                url = GUIDELINE_URLS.get("USPSTF_COLORECTAL", "")
            elif "USPSTF DIABETES" in citation_upper or ("PREDIABETES" in citation_upper and "USPSTF" in citation_upper):
                source = "USPSTF_DIABETES"
                url = GUIDELINE_URLS.get("USPSTF_DIABETES", "")
            elif "USPSTF STATIN" in citation_upper or "USPSTF CARDIOVASCULAR" in citation_upper:
                source = "USPSTF_CARDIO"
                url = GUIDELINE_URLS.get("USPSTF_CARDIO", "")
            # Single organizations - check in order of specificity (longer acronyms first)
            elif "USPSTF" in citation_upper:
                source = "USPSTF"
                url = GUIDELINE_URLS.get("USPSTF", "")
            elif "NCCN" in citation_upper:
                source = "NCCN"
                url = GUIDELINE_URLS.get("NCCN", "")
            elif "ASCO" in citation_upper:
                source = "ASCO"
                url = GUIDELINE_URLS.get("ASCO", "")
            elif "ESMO" in citation_upper:
                source = "ESMO"
                url = GUIDELINE_URLS.get("ESMO", "")
            # AAD - check for melanoma sub-entry BEFORE generic fallback
            elif "AAD MELANOMA" in citation_upper or ("MELANOMA" in citation_upper and "AAD" in citation_upper):
                source = "AAD_MELANOMA"
                url = GUIDELINE_URLS.get("AAD_MELANOMA", "")
            elif "AAD" in citation_upper:
                source = "AAD"
                url = GUIDELINE_URLS.get("AAD", "")
            elif "ACR" in citation_upper:
                source = "ACR"
                url = GUIDELINE_URLS.get("ACR", "")
            elif "ADA" in citation_upper:
                source = "ADA"
                url = GUIDELINE_URLS.get("ADA", "")
            elif "AHA" in citation_upper:
                source = "AHA"
                url = GUIDELINE_URLS.get("AHA", "")
            elif "CHEST" in citation_upper:
                source = "CHEST"
                url = GUIDELINE_URLS.get("CHEST", "")
            elif "WHO" in citation_upper:
                source = "WHO"
                url = GUIDELINE_URLS.get("WHO", "")
            elif "NICE" in citation_upper:
                source = "NICE"
                url = GUIDELINE_URLS.get("NICE", "")
            elif "IDSA" in citation_upper:
                source = "IDSA"
                url = GUIDELINE_URLS.get("IDSA", "")
            elif "CDC" in citation_upper:
                source = "CDC"
                url = GUIDELINE_URLS.get("CDC", "")
            elif "ACC" in citation_upper:
                source = "ACC"
                url = GUIDELINE_URLS.get("ACC", "")
            elif "ATS" in citation_upper:
                source = "ATS"
                url = GUIDELINE_URLS.get("ATS", "")
        
        # Format citation text consistently
        formatted_text = citation_text
        if not citation_text.startswith("("):
            formatted_text = f"({citation_text})"
        
        if source == "AAD_MELANOMA":
            output_source = "AAD"
            url = GUIDELINE_URLS.get("AAD", "")
        else:
            output_source = source
        citations.append({
            "text": formatted_text,
            "url": url,
            "source": output_source
        })
    
    def _normalize_citation_key(c: dict) -> str:
        """Normalize citation for dedup: strip 'According to the' prefix, use source + year."""
        text = c["text"]
        # Strip common prefixes
        text = re.sub(r"^\(?\s*(?:According to the|Per the|Based on the)\s+", "", text, flags=re.IGNORECASE)
        # Extract year
        year_match = re.search(r"\d{4}", text)
        year = year_match.group(0) if year_match else ""
        # Normalize to source + year
        return f"{c['source']}:{year}"
    
    # Remove duplicate citations while preserving order (dedupe by normalized key)
    seen = set()
    unique_citations = []
    for c in citations:
        key = _normalize_citation_key(c)
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)
    
    return text, unique_citations

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
    episode_summaries: list[str] = field(default_factory=list)  # Summaries of 5-round episodes
    last_episode_round: int = 0  # Track when we last created an episode summary
    
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
        
        # Include episode summaries for longer debates (hierarchical summarization)
        if self.episode_summaries:
            lines.append("\n=== Previous Debate Episodes ===")
            # Show last 3 episodes (most recent first)
            for i, summary in enumerate(reversed(self.episode_summaries[-3:]), 1):
                episode_num = len(self.episode_summaries) - i + 1
                lines.append(f"Episode {episode_num}: {summary[:250]}...")
        
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
- Always cite specific clinical evidence (e.g., "Based on the ferritin of [value]...") when values are provided
- Be conversational but precise -- you're a senior diagnostician leading a case discussion
- Acknowledge valid challenges and update your reasoning accordingly
- If the user raises a point that changes the differential, reflect that in the updated diagnoses
- When defending a diagnosis, provide specific evidence, not vague claims

CONSTRAINTS (for timely responses):
- Keep responses under 800 tokens (~600 words) to ensure delivery within 180 seconds
- Focus on the 2-3 most critical differential diagnoses
- Cite evidence concisely (1-2 sentences per point)
- Suggest at most 1 test per round
- Avoid repeating information from previous rounds or episode summaries
- If a query is too complex or multi-part, ask the user to break it into smaller questions

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
        # ThreadPoolExecutor for MedGemma calls with timeout
        self._medgemma_executor = ThreadPoolExecutor(max_workers=1)
    
    def initialize(self, api_key: str = None):
        """Initialize the Gemini client with timeout configuration."""
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "No Gemini API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                "environment variable, or pass api_key to initialize()."
            )
        
        # Configure timeout: 90 seconds (90000 milliseconds)
        timeout_ms = int(DEFAULT_TIMEOUT_SECONDS * 1000)
        self.client = genai.Client(
            api_key=key, 
            http_options=types.HttpOptions(timeout=timeout_ms)
        )
        logger.info(f"Gemini orchestrator initialized with model: {self._model_name} (timeout: {DEFAULT_TIMEOUT_SECONDS}s)")
    
    def cleanup(self):
        """Cleanup resources including thread pool executor."""
        if hasattr(self, '_medgemma_executor'):
            self._medgemma_executor.shutdown(wait=True)
            logger.info("MedGemma executor shut down")
    
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
    
    async def _query_medgemma_with_timeout(
        self, 
        question: str, 
        clinical_context: str, 
        timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> str:
        """Query MedGemma with timeout protection.
        
        Args:
            question: The medical question to ask
            clinical_context: Context about the patient case
            timeout: Maximum time to wait in seconds (default: 90s)
            
        Returns:
            MedGemma's response, or a timeout message if query takes too long
        """
        try:
            # Run MedGemma query in thread with timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(self._query_medgemma, question, clinical_context),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(f"MedGemma query timed out after {timeout}s. Question: {question[:100]}...")
            return self._generate_timeout_response(question)
    
    def _generate_timeout_response(self, question: str) -> str:
        """Generate a graceful timeout response when MedGemma takes too long.
        
        This provides helpful guidance to the user when complex queries timeout.
        """
        return f"""The medical analysis is taking longer than expected (>{DEFAULT_TIMEOUT_SECONDS}s).

This typically happens when the question involves complex multi-part reasoning.

RECOMMENDATIONS:
1. Try breaking your question into smaller, focused parts
2. Ask about one specific symptom or finding at a time
3. Focus on the most critical differential diagnoses first

For example, instead of asking multiple questions at once:
- Ask: "What could explain the low platelets?"
- Then: "Should we test for Legionella?"

Your current question was: "{question[:150]}..."

Please try rephrasing as a single, focused question."""
    
    def process_debate_turn(
        self,
        user_challenge: str,
        clinical_state: ClinicalState,
        previous_rounds: list[dict] = None,
        retrieved_context: str = "",
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
            retrieved_context: Retrieved guideline context from RAG (optional)
            
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
        
        # --- Step 2: Query MedGemma with the focused question (with timeout) ---
        try:
            # Submit MedGemma query to thread pool with timeout
            future = self._medgemma_executor.submit(
                self._query_medgemma, medgemma_question, state_summary
            )
            medgemma_analysis = future.result(timeout=DEFAULT_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            logger.warning(f"MedGemma query timed out after {DEFAULT_TIMEOUT_SECONDS}s")
            medgemma_analysis = self._generate_timeout_response(medgemma_question)
        
        # --- Step 3: Ask Gemini to synthesize the final response ---
        synthesis_prompt = self._build_synthesis_prompt(
            user_challenge, state_summary, medgemma_question,
            medgemma_analysis, previous_rounds, retrieved_context
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
        
        # RAG: Extract citations from ai_response
        ai_response_text = result.get("ai_response", "")
        _, citations = extract_citations(ai_response_text)
        result["citations"] = citations
        result["has_guidelines"] = len(citations) > 0
        
        # Debug logging
        logger.info(f"[RAG] Extracted {len(citations)} citations from response")
        if citations:
            for c in citations:
                logger.info(f"[RAG] Citation: {c['text']} -> {c['url']}")
        else:
            logger.info(f"[RAG] No citations found. AI response snippet: {ai_response_text[:200]}...")
        
        # Update clinical state with new findings
        if result.get("key_findings_update"):
            clinical_state.key_findings.extend(result.get("key_findings_update", []))
        if result.get("newly_ruled_out"):
            clinical_state.ruled_out.extend(result.get("newly_ruled_out", []))
        if result.get("updated_differential"):
            clinical_state.differential = result.get("updated_differential", [])
        
        # Hierarchical Summarization: Create episode summary every 5 rounds
        rounds_since_last_episode = clinical_state.debate_round - clinical_state.last_episode_round
        logger.info(f"[Episode] round={clinical_state.debate_round}, last_episode={clinical_state.last_episode_round}, rounds_since={rounds_since_last_episode}, previous_rounds={len(previous_rounds) if previous_rounds else 0}")
        if rounds_since_last_episode >= 5 and previous_rounds:
            # Get the last 5 rounds for this episode
            episode_rounds = previous_rounds[-5:]
            episode_summary = self._create_episode_summary(episode_rounds)
            if episode_summary:
                clinical_state.episode_summaries.append(episode_summary)
                clinical_state.last_episode_round = clinical_state.debate_round
                logger.info(f"Created episode summary at round {clinical_state.debate_round}")
        
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
        retrieved_context: str = "",
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
        
        # Build the prompt with optional RAG context
        rag_section = ""
        citation_instruction = ""
        if retrieved_context:
            rag_section = f"""

RETRIEVED EVIDENCE-BASED GUIDELINES:
{retrieved_context}

You MUST cite ONLY the above retrieved guidelines when making clinical recommendations. Do not hallucinate citations for guidelines that were not retrieved.
"""
            citation_instruction = """3. Cite the retrieved guidelines using these EXACT formats (do not change the year):
    - CDC Sepsis: "(CDC Hospital Sepsis Program Core Elements, 2025)"
    - CDC Respiratory: "(CDC Respiratory Virus Guidance, 2025)"
    - CDC Legionella: "(CDC Clinical Guidance for Legionella, 2025)"
    - PMC pneumonia: "(PMC Guidelines for Pneumonia Evaluation, 2018)"
    - USPSTF Breast Cancer: "(USPSTF Breast Cancer Screening Guidelines, 2024)"
    - USPSTF Colorectal: "(USPSTF Colorectal Cancer Screening Guidelines, 2021)"
    - USPSTF Diabetes: "(USPSTF Diabetes Screening Guidelines, 2021)"
    - USPSTF Cardiovascular: "(USPSTF Statin Use Guidelines, 2022)"
    - WHO Meningitis: "(WHO Meningitis Guidelines, 2025)"
    - WHO TB: "(WHO TB Prevention Guidelines, 2024)"
    - WHO Hepatitis B: "(WHO Hepatitis B Guidelines, 2024)"
    - AAD Melanoma: "(AAD Melanoma Guidelines, 2018)"
    
    Only cite guidelines that are clinically relevant to your recommendation. If a retrieved guideline is not applicable to this case, do not cite it."""
        else:
            citation_instruction = """3. Do NOT cite any clinical guidelines — none were retrieved for this topic. Focus purely on clinical reasoning from MedGemma's analysis"""
        
        return f"""{state_summary}
{recent_context}

The clinician challenged: "{user_challenge}"

You asked your medical specialist: "{medgemma_question}"

MedGemma's analysis:
{medgemma_analysis}
{rag_section}

Now synthesize this into your response. You must:
1. Address the user's challenge directly and conversationally
2. Incorporate MedGemma's analysis with specific evidence citations
{citation_instruction}
4. Update the differential if warranted by the analysis
5. Suggest a test if it would help clarify

CRITICAL: The "ai_response" field must be a plain conversational text string, NOT a JSON object or nested JSON. Write it as you would speak to a colleague."""
    
    def _parse_orchestrator_response(self, text: str) -> dict:
        """Parse Gemini's JSON response with fallback handling.
        
        Handles:
        1. JSON in code blocks
        2. Missing commas between fields
        3. Truncated JSON (token limit hit mid-string) — extracts ai_response via regex
        4. Double-wrapped JSON (ai_response contains JSON string)
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
                # Insert missing commas between quote-key pairs
                fixed_text = re.sub(r'"\s*\n\s*"', '",\n"', text)
                data = json.loads(fixed_text)
                logger.info("Successfully repaired malformed JSON (missing commas)")
            except json.JSONDecodeError:
                # Likely truncated JSON from token limit — extract ai_response via regex
                logger.warning(f"JSON parse failed: {e}. Attempting regex extraction from truncated response.")
                ai_match = re.search(
                    r'"ai_response"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)',
                    text, re.DOTALL
                )
                if ai_match:
                    extracted = ai_match.group(1)
                    # Unescape JSON string escapes
                    extracted = extracted.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                    logger.info(f"Extracted ai_response via regex ({len(extracted)} chars)")
                    data = {
                        "ai_response": extracted,
                        "updated_differential": [],
                        "suggested_test": None,
                    }
                else:
                    logger.error(f"Failed to parse Gemini response: {e}\nText: {text[:500]}")
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
    
    def _create_episode_summary(self, rounds: list[dict]) -> str:
        """Create a summary of the last N debate rounds using Gemini.
        
        This is part of hierarchical summarization to keep prompt sizes
        manageable for long debates (20+ rounds).
        
        Note: At round 5, previous_rounds contains only rounds 1-4 (4 items)
        because the current round's response hasn't been added to debateRounds
        yet (it's added AFTER the API returns). So we accept 4+ rounds.
        
        Args:
            rounds: List of debate round dictionaries (4-5 rounds typical)
            
        Returns:
            A concise summary of the episode
        """
        if len(rounds) < 4 or self.client is None:
            return ""
        
        # Build context from the rounds
        episode_context = []
        for i, r in enumerate(rounds, 1):
            challenge = r.get("user_challenge", r.get("challenge", ""))
            response = r.get("ai_response", r.get("response", ""))
            episode_context.append(f"Round {i}:\nUser: {challenge[:100]}...\nAI: {response[:150]}...")
        
        summary_prompt = f"""Summarize this diagnostic debate episode ({len(rounds)} rounds) in 2-3 sentences.
Focus on:
- Key diagnostic insights gained
- Major differential updates
- Critical questions answered

Debate Episode:
{chr(10).join(episode_context)}

Provide a concise summary:"""
        
        try:
            summary_response = self.client.models.generate_content(
                model=self._model_name,
                contents=summary_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=200,
                ),
            )
            summary = summary_response.text.strip()
            logger.info(f"Created episode summary: {summary[:100]}...")
            return summary
        except Exception as e:
            logger.error(f"Failed to create episode summary: {e}")
            # Fallback: create a simple manual summary
            return f"Debate rounds covered {len(rounds)} exchanges about differential diagnosis."


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
