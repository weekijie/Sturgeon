"""
RAG Evaluation Module - LLM-as-a-Judge Framework

Implements the Guide-RAG paper's evaluation metrics for assessing RAG response quality:
- Faithfulness: Response supported by retrieved context
- Relevance: Response addresses the question
- Comprehensiveness: Response covers all aspects

Uses Gemini as the evaluation judge (already in stack, native JSON output).
"""

import os
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Results from RAG evaluation."""
    faithfulness: float
    relevance: float
    comprehensiveness: float
    overall: float
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        return cls(
            faithfulness=data.get("faithfulness", 0.0),
            relevance=data.get("relevance", 0.0),
            comprehensiveness=data.get("comprehensiveness", 0.0),
            overall=data.get("overall", 0.0),
            reasoning=data.get("reasoning", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class RetrievedContext:
    """Represents retrieved context for evaluation."""
    content: str
    source: str
    topic: str
    distance: float = 0.0


EVALUATION_PROMPT = """You are evaluating the quality of a medical AI response for a clinical question-answering system.

## Evaluation Criteria

### 1. Faithfulness (0-1)
Is the response supported by the retrieved context? If the response contains claims that cannot be substantiated by the retrieved context, it is unfaithful, even if factually correct.

Scoring:
- 1.0: All claims are directly supported by the retrieved context
- 0.7-0.9: Most claims supported, minor unsupported details
- 0.4-0.6: Some claims supported, some unsupported
- 0.1-0.3: Mostly unsupported claims
- 0.0: No claims supported by context

### 2. Relevance (0-1)
Does the response directly address the clinical question without digressions?

Scoring:
- 1.0: Directly and completely addresses the question
- 0.7-0.9: Addresses the question with minor tangential content
- 0.4-0.6: Partially addresses the question
- 0.1-0.3: Mostly irrelevant to the question
- 0.0: Does not address the question

### 3. Comprehensiveness (0-1)
Does the response thoroughly cover all important aspects of the clinical question?

Scoring:
- 1.0: Covers all critical aspects thoroughly
- 0.7-0.9: Covers most aspects with minor gaps
- 0.4-0.6: Covers some aspects, missing important points
- 0.1-0.3: Incomplete coverage, major gaps
- 0.0: Fails to address key aspects

## Input

**Clinical Question:**
{question}

**Retrieved Context:**
{context}

**AI Response:**
{response}

## Output

Provide your evaluation as a JSON object with the following format:
{{
  "faithfulness": <float 0-1>,
  "relevance": <float 0-1>,
  "comprehensiveness": <float 0-1>,
  "overall": <float 0-1, equal-weighted average>,
  "reasoning": "<Brief explanation of scores, highlighting specific strengths/weaknesses>"
}}

IMPORTANT: Return ONLY the JSON object, no additional text.
"""


PAIRWISE_PROMPT = """You are comparing two AI responses to the same clinical question.

## Task
Determine which response is better according to: {criteria_text}

## Input

**Clinical Question:**
{question}

**Retrieved Context:**
{context}

**Response A:**
{response_a}

**Response B:**
{response_b}

## Output
Return JSON with:
{{
  "winner": 0|1|2,  // 0=tie, 1=A better, 2=B better
  "reasoning": "<Explanation for your choice>"
}}

IMPORTANT: 
- Do not let response length influence your decision
- Do not let the order of presentation influence your decision
- Return ONLY the JSON object
"""


class RAGEvaluator:
    """
    LLM-as-a-Judge evaluator for RAG responses.
    
    Uses Gemini for evaluation (already in stack, native JSON output support).
    """
    
    def __init__(self):
        self.client = None
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    
    def initialize(self, api_key: str = None):
        """Initialize Gemini client for evaluation."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai not installed. Run: pip install google-genai")
        
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("No Gemini API key found for evaluation.")
        
        timeout_ms = 60000  # 60 seconds for evaluation
        self.client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=timeout_ms)
        )
        logger.info(f"RAG Evaluator initialized with model: {self._model_name}")
    
    def _get_client(self):
        """Get or initialize Gemini client."""
        if self.client is None:
            self.initialize()
        return self.client
    
    def evaluate_response(
        self,
        question: str,
        response: str,
        retrieved_contexts: List[RetrievedContext],
    ) -> EvaluationResult:
        """
        Evaluate a single RAG response.
        
        Args:
            question: The clinical question asked
            response: The AI's response
            retrieved_contexts: List of retrieved context chunks
            
        Returns:
            EvaluationResult with faithfulness, relevance, comprehensiveness scores
        """
        client = self._get_client()
        
        # Format context for evaluation
        context_str = self._format_context(retrieved_contexts)
        
        # Build evaluation prompt
        prompt = EVALUATION_PROMPT.format(
            question=question,
            context=context_str,
            response=response
        )
        
        try:
            from google.genai import types
            
            eval_response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Low temperature for consistent evaluation
                    max_output_tokens=512,
                    response_mime_type="application/json",
                )
            )
            
            # Parse JSON response
            result = self._parse_evaluation_response(eval_response.text)
            return result
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return EvaluationResult(
                faithfulness=0.0,
                relevance=0.0,
                comprehensiveness=0.0,
                overall=0.0,
                reasoning=f"Evaluation error: {str(e)}"
            )
    
    def pairwise_compare(
        self,
        question: str,
        response_a: str,
        response_b: str,
        retrieved_contexts: List[RetrievedContext],
        criteria: str = "overall"
    ) -> Dict[str, Any]:
        """
        Compare two responses head-to-head.
        
        Args:
            question: The clinical question
            response_a: First response
            response_b: Second response
            retrieved_contexts: Retrieved context
            criteria: Evaluation criteria ("faithfulness", "relevance", "comprehensiveness", "overall")
            
        Returns:
            Dict with winner (0=tie, 1=A, 2=B) and reasoning
        """
        client = self._get_client()
        
        criteria_texts = {
            "faithfulness": "Which response is more faithful to the retrieved context? (All claims supported by evidence)",
            "relevance": "Which response is more relevant to the clinical question? (Directly addresses the question)",
            "comprehensiveness": "Which response is more comprehensive? (Covers all important aspects)",
            "overall": "Which response is better overall? Consider faithfulness, relevance, and comprehensiveness equally."
        }
        
        criteria_text = criteria_texts.get(criteria, criteria_texts["overall"])
        context_str = self._format_context(retrieved_contexts)
        
        prompt = PAIRWISE_PROMPT.format(
            criteria_text=criteria_text,
            question=question,
            context=context_str,
            response_a=response_a,
            response_b=response_b
        )
        
        try:
            from google.genai import types
            
            eval_response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                    response_mime_type="application/json",
                )
            )
            
            result = self._parse_json(eval_response.text)
            return {
                "winner": result.get("winner", 0),
                "reasoning": result.get("reasoning", "Unable to parse reasoning")
            }
            
        except Exception as e:
            logger.error(f"Pairwise comparison failed: {e}")
            return {
                "winner": 0,
                "reasoning": f"Comparison error: {str(e)}"
            }
    
    def evaluate_corpus_config(
        self,
        questions: List[Dict[str, str]],
        get_response_fn,
        top_k: int = 12,
    ) -> Dict[str, Any]:
        """
        Evaluate a corpus configuration across multiple questions.
        
        This mirrors the Guide-RAG paper's evaluation framework.
        
        Args:
            questions: List of dicts with "question" and optional "expected_topics"
            get_response_fn: Function that takes (question, top_k) and returns (response, contexts)
            top_k: Number of chunks to retrieve
            
        Returns:
            Aggregated evaluation results
        """
        results = []
        
        for i, q_data in enumerate(questions):
            question = q_data.get("question", "")
            if not question:
                continue
            
            logger.info(f"Evaluating question {i+1}/{len(questions)}: {question[:50]}...")
            
            try:
                response, contexts = get_response_fn(question, top_k)
                eval_result = self.evaluate_response(question, response, contexts)
                results.append({
                    "question": question,
                    "evaluation": eval_result.to_dict()
                })
            except Exception as e:
                logger.error(f"Failed to evaluate question: {e}")
                results.append({
                    "question": question,
                    "evaluation": EvaluationResult(
                        faithfulness=0.0,
                        relevance=0.0,
                        comprehensiveness=0.0,
                        overall=0.0,
                        reasoning=f"Error: {str(e)}"
                    ).to_dict()
                })
        
        # Aggregate scores
        if results:
            avg_faithfulness = sum(r["evaluation"]["faithfulness"] for r in results) / len(results)
            avg_relevance = sum(r["evaluation"]["relevance"] for r in results) / len(results)
            avg_comprehensiveness = sum(r["evaluation"]["comprehensiveness"] for r in results) / len(results)
            avg_overall = sum(r["evaluation"]["overall"] for r in results) / len(results)
        else:
            avg_faithfulness = avg_relevance = avg_comprehensiveness = avg_overall = 0.0
        
        return {
            "num_questions": len(questions),
            "avg_faithfulness": round(avg_faithfulness, 3),
            "avg_relevance": round(avg_relevance, 3),
            "avg_comprehensiveness": round(avg_comprehensiveness, 3),
            "avg_overall": round(avg_overall, 3),
            "individual_results": results,
            "timestamp": datetime.now().isoformat()
        }
    
    def _format_context(self, contexts: List[RetrievedContext]) -> str:
        """Format retrieved contexts for evaluation prompt."""
        if not contexts:
            return "[No context retrieved]"
        
        parts = []
        for i, ctx in enumerate(contexts, 1):
            parts.append(f"""
[Context {i}] Source: {ctx.source} | Topic: {ctx.topic}
{ctx.content}
""")
        
        return "\n---\n".join(parts)
    
    def _parse_evaluation_response(self, text: str) -> EvaluationResult:
        """Parse evaluation JSON from LLM response."""
        data = self._parse_json(text)
        
        return EvaluationResult(
            faithfulness=float(data.get("faithfulness", 0.0)),
            relevance=float(data.get("relevance", 0.0)),
            comprehensiveness=float(data.get("comprehensiveness", 0.0)),
            overall=float(data.get("overall", 0.0)),
            reasoning=data.get("reasoning", "")
        )
    
    def _parse_json(self, text: str) -> dict:
        """Parse JSON from LLM response with error handling."""
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            text = json_match.group(1)
        
        # Find first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end + 1]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse evaluation JSON: {e}")
            return {
                "faithfulness": 0.0,
                "relevance": 0.0,
                "comprehensiveness": 0.0,
                "overall": 0.0,
                "reasoning": f"Failed to parse: {text[:200]}"
            }


# Singleton instance
_evaluator_instance: Optional[RAGEvaluator] = None


def get_evaluator() -> RAGEvaluator:
    """Get or create singleton evaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = RAGEvaluator()
    return _evaluator_instance
