"""
RAG evaluation module for Modal backend.

Implements the same interface as ai-service/rag_evaluation.py:
- RetrievedContext dataclass
- EvaluationResult dataclass
- get_evaluator() singleton
"""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    faithfulness: float
    relevance: float
    comprehensiveness: float
    overall: float
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievedContext:
    content: str
    source: str
    topic: str
    distance: float = 0.0


EVALUATION_PROMPT = """You are evaluating a medical AI response for a clinical QA system.

Score each metric from 0.0 to 1.0:
1. faithfulness: claims supported by retrieved context
2. relevance: directly answers the question
3. comprehensiveness: covers key aspects

Clinical Question:
{question}

Retrieved Context:
{context}

AI Response:
{response}

Return ONLY valid JSON:
{{
  "faithfulness": <float>,
  "relevance": <float>,
  "comprehensiveness": <float>,
  "overall": <float>,
  "reasoning": "<short explanation>"
}}
"""


class RAGEvaluator:
    def __init__(self):
        self.client = None
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    def initialize(self, api_key: str = None):
        from google import genai
        from google.genai import types

        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("No Gemini API key found for evaluation.")

        self.client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=60000),
        )

    def _get_client(self):
        if self.client is None:
            self.initialize()
        return self.client

    def evaluate_response(
        self,
        question: str,
        response: str,
        retrieved_contexts: List[RetrievedContext],
    ) -> EvaluationResult:
        client = self._get_client()
        from google.genai import types

        context_text = self._format_context(retrieved_contexts)
        prompt = EVALUATION_PROMPT.format(
            question=question,
            context=context_text,
            response=response,
        )

        try:
            eval_response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            )
            parsed = self._parse_json(eval_response.text)
            return EvaluationResult(
                faithfulness=float(parsed.get("faithfulness", 0.0)),
                relevance=float(parsed.get("relevance", 0.0)),
                comprehensiveness=float(parsed.get("comprehensiveness", 0.0)),
                overall=float(parsed.get("overall", 0.0)),
                reasoning=parsed.get("reasoning", ""),
            )
        except Exception as e:
            logger.error("RAG evaluation failed: %s", e)
            return EvaluationResult(
                faithfulness=0.0,
                relevance=0.0,
                comprehensiveness=0.0,
                overall=0.0,
                reasoning=f"Evaluation error: {str(e)}",
            )

    def _format_context(self, contexts: List[RetrievedContext]) -> str:
        if not contexts:
            return "[No context retrieved]"
        parts = []
        for idx, ctx in enumerate(contexts, 1):
            parts.append(
                f"[Context {idx}] Source: {ctx.source} | Topic: {ctx.topic}\n{ctx.content}"
            )
        return "\n---\n".join(parts)

    def _parse_json(self, text: str) -> dict:
        block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if block:
            text = block.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "faithfulness": 0.0,
                "relevance": 0.0,
                "comprehensiveness": 0.0,
                "overall": 0.0,
                "reasoning": f"Failed to parse evaluator JSON: {text[:200]}",
            }


_evaluator_instance: Optional[RAGEvaluator] = None


def get_evaluator() -> RAGEvaluator:
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = RAGEvaluator()
    return _evaluator_instance
