"""
tests/ai/test_advisor.py
=========================
Testes do advisor pedagógico com mocks do LLM client.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from contracts.data_models import GroupingResult, SubjectEnum
from src.llm.advisor import PedagogicalAdvisor, _fallback_recommendation, get_default_model
from src.models.grade import hash_student_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_group() -> GroupingResult:
    return GroupingResult(
        group_id="grp_test001",
        student_hashes=[hash_student_id(f"aluno_{i}") for i in range(4)],
        shared_weaknesses=[SubjectEnum.MATEMATICA, SubjectEnum.CIENCIAS],
        similarity_score=0.82,
    )


VALID_LLM_RESPONSE = {
    "recommendations": [
        "Criar grupo de reforço em Matemática às quartas",
        "Usar material visual para geometria",
    ],
    "subjects_addressed": ["Matemática"],
    "disclaimer": "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir.",
}


# ---------------------------------------------------------------------------
# Testes: resposta válida
# ---------------------------------------------------------------------------

class TestAdvisorValid:
    def test_returns_ai_recommendation(self, sample_group):
        with patch("src.llm.advisor.LLMClient") as MockClient:
            instance = MockClient.return_value
            instance.chat = AsyncMock(return_value=VALID_LLM_RESPONSE)
            instance.close = lambda: None

            advisor = PedagogicalAdvisor()
            advisor._client = instance
            rec = asyncio.run(advisor.recommend(sample_group))

        assert rec.group_id == "grp_test001"
        assert len(rec.recommendations) == 2
        assert rec.disclaimer

    def test_disclaimer_always_present(self, sample_group):
        response_without_disclaimer = {**VALID_LLM_RESPONSE, "disclaimer": ""}

        with patch("src.llm.advisor.LLMClient") as MockClient:
            instance = MockClient.return_value
            instance.chat = AsyncMock(return_value=response_without_disclaimer)
            instance.close = lambda: None

            advisor = PedagogicalAdvisor()
            advisor._client = instance
            rec = asyncio.run(advisor.recommend(sample_group))

        # Sempre deve ter disclaimer — mesmo que LLM omita
        assert rec.disclaimer
        assert len(rec.disclaimer) > 10

    def test_model_read_from_contract(self):
        """Modelo deve vir de pedagogical_rules.json, não hardcoded."""
        model = get_default_model()
        assert model.value == "mistral"  # valor atual no contrato


# ---------------------------------------------------------------------------
# Testes: fallback
# ---------------------------------------------------------------------------

class TestAdvisorFallback:
    def test_fallback_on_llm_timeout(self, sample_group):
        from src.llm.client import LLMTimeoutError

        with patch("src.llm.advisor.LLMClient") as MockClient:
            instance = MockClient.return_value
            instance.chat = AsyncMock(side_effect=LLMTimeoutError("timeout"))
            instance.close = lambda: None

            advisor = PedagogicalAdvisor()
            advisor._client = instance
            rec = asyncio.run(advisor.recommend(sample_group))

        # Fallback nunca levanta exceção
        assert rec is not None
        assert rec.group_id == "grp_test001"
        assert len(rec.recommendations) >= 1

    def test_fallback_on_invalid_json_schema(self, sample_group):
        """Se LLM retorna JSON inválido para o schema, fallback é acionado."""
        bad_response = {"wrong_field": "data"}

        with patch("src.llm.advisor.LLMClient") as MockClient:
            instance = MockClient.return_value
            instance.chat = AsyncMock(return_value=bad_response)
            instance.close = lambda: None

            advisor = PedagogicalAdvisor()
            advisor._client = instance
            rec = asyncio.run(advisor.recommend(sample_group))

        assert rec is not None
        assert "indisponível" in rec.recommendations[0].lower() or len(rec.recommendations) >= 1

    def test_fallback_response_is_deterministic(self):
        from contracts.data_models import SupportedModel
        rec1 = _fallback_recommendation("grp_x", SupportedModel.MISTRAL)
        rec2 = _fallback_recommendation("grp_x", SupportedModel.MISTRAL)
        assert rec1.recommendations == rec2.recommendations

    def test_fallback_has_disclaimer(self):
        from contracts.data_models import SupportedModel
        rec = _fallback_recommendation("grp_y", SupportedModel.MISTRAL)
        assert rec.disclaimer


# ---------------------------------------------------------------------------
# Testes: segurança pedagógica
# ---------------------------------------------------------------------------

class TestAdvisorSecurity:
    def test_no_pii_in_user_message(self, sample_group):
        """Mensagem enviada ao LLM não deve conter IDs crus de alunos."""
        from src.llm.advisor import _build_user_message
        msg = _build_user_message(sample_group)
        for h in sample_group.student_hashes:
            assert h not in msg  # hashes não aparecem na mensagem

    def test_system_prompt_is_constant(self):
        """System prompt deve ser constante imutável, não f-string."""
        from src.llm.advisor import SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100
        assert "{" not in SYSTEM_PROMPT  # sem f-string / template
