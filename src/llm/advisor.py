"""
src/llm/advisor.py
==================
Lógica pedagógica: constrói prompts, chama o LLM e valida a resposta.
Agente 3 — IA & Pedagogia.

NUNCA concatene input do usuário no SYSTEM_PROMPT.
Todo input passa por sanitize_text_input antes de ir ao LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import structlog
from pydantic import ValidationError

from contracts.data_models import AIRecommendation, GroupingResult, SubjectEnum, SupportedModel
from src.llm.client import LLMClient, LLMError, LLMTimeoutError
from src.models.grade import sanitize_text_input

__all__ = ["PedagogicalAdvisor", "get_default_model"]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constante imutável — NUNCA concatene com input do usuário
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: Final[str] = """Você é um assistente pedagógico especializado em análise de desempenho escolar.
Sua função é gerar recomendações formativas e práticas para grupos de alunos com dificuldades compartilhadas.

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em JSON válido com exatamente os campos: recommendations (lista de strings), subjects_addressed (lista de strings), disclaimer (string).
2. Use tom FORMATIVO e ENCORAJADOR — nunca punitivo.
3. Máximo 5 recomendações por grupo. Seja específico e acionável.
4. NUNCA faça diagnósticos médicos ou psicológicos.
5. SEMPRE inclua: "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir."
6. Foque em estratégias pedagógicas concretas (horários, métodos, materiais).

FORMATO DE RESPOSTA (JSON obrigatório):
{
  "recommendations": ["Recomendação 1", "Recomendação 2"],
  "subjects_addressed": ["Matemática"],
  "disclaimer": "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir."
}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "contracts" / "pedagogical_rules.json"


def get_default_model() -> SupportedModel:
    """Lê o modelo padrão de pedagogical_rules.json e valida com o enum.

    Returns:
        SupportedModel ativo conforme o contrato.

    Raises:
        ValueError: Se o modelo no contrato não está em SupportedModel.
    """
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            rules = json.load(f)
        model_str = rules["models"]["default"]
        return SupportedModel(model_str)
    except (KeyError, FileNotFoundError) as exc:
        log.warning("rules_not_found_using_mistral", error=str(exc))
        return SupportedModel.MISTRAL


def _build_user_message(group: GroupingResult) -> str:
    """Constrói mensagem do usuário a partir do grupo — sem PII.

    Args:
        group: Resultado do agrupamento (hashes, disciplinas).

    Returns:
        String sanitizada para envio ao LLM.
    """
    weaknesses = ", ".join(s.value for s in group.shared_weaknesses) or "diversas disciplinas"
    size = len(group.student_hashes)
    similarity = f"{group.similarity_score:.0%}"

    raw_message = (
        f"Grupo de {size} alunos com dificuldades compartilhadas em: {weaknesses}. "
        f"Similaridade do grupo: {similarity}. "
        f"Gere recomendações pedagógicas práticas para este grupo."
    )
    return sanitize_text_input(raw_message)


def _fallback_recommendation(group_id: str, model: SupportedModel) -> AIRecommendation:
    """Retorna recomendação determinística de fallback quando o LLM falha.

    Args:
        group_id: ID do grupo afetado.
        model: Modelo que falhou.

    Returns:
        AIRecommendation com mensagem de fallback — nunca levanta exceção.
    """
    return AIRecommendation(
        group_id=group_id,
        recommendations=[
            "Análise de IA temporariamente indisponível.",
            "Recomendação manual: Consulte o professor responsável pelas disciplinas do grupo.",
            "Considere agendar uma reunião pedagógica para discutir as dificuldades identificadas.",
        ],
        subjects_addressed=[],
        model_used=model,
        disclaimer="IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir.",
    )


# ---------------------------------------------------------------------------
# Advisor principal
# ---------------------------------------------------------------------------

class PedagogicalAdvisor:
    """Gerador de recomendações pedagógicas via LLM local.

    Usage:
        advisor = PedagogicalAdvisor()
        rec = await advisor.recommend(group)
    """

    def __init__(self, model: SupportedModel | None = None) -> None:
        self._model = model or get_default_model()
        self._client = LLMClient(model=self._model.value)
        log.info("advisor_initialized", model=self._model.value)

    async def recommend(self, group: GroupingResult) -> AIRecommendation:
        """Gera recomendação pedagógica para um grupo de alunos.

        Nunca levanta exceção — retorna fallback em caso de falha.

        Args:
            group: GroupingResult com student_hashes e shared_weaknesses.

        Returns:
            AIRecommendation sempre válida (com ou sem fallback).
        """
        # ── 1. Construir mensagem sem PII ─────────────────────────────────
        user_message = _build_user_message(group)

        # ── 2. Chamar LLM com retry/cache ─────────────────────────────────
        try:
            raw = await self._client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
            )

            # ── 3. Validar schema Pydantic ANTES de usar ──────────────────
            subjects = [
                SubjectEnum(s) for s in raw.get("subjects_addressed", [])
                if s in {e.value for e in SubjectEnum}
            ]

            recommendation = AIRecommendation(
                group_id=group.group_id,
                recommendations=raw.get("recommendations", []),
                subjects_addressed=subjects,
                model_used=self._model,
                disclaimer=raw.get(
                    "disclaimer",
                    "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir.",
                ),
            )
            log.info(
                "recommendation_generated",
                group_id=group.group_id,
                model=self._model.value,
                n_recommendations=len(recommendation.recommendations),
            )
            return recommendation

        except (LLMError, LLMTimeoutError, ValidationError, KeyError) as exc:
            log.error(
                "recommendation_fallback",
                group_id=group.group_id,
                error=str(exc),
            )
            return _fallback_recommendation(group.group_id, self._model)

    def close(self) -> None:
        self._client.close()
