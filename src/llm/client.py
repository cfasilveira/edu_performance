"""
src/llm/client.py
=================
Cliente de comunicação com Ollama via litellm.
Agente 3 — IA & Pedagogia.

Responsabilidades:
- Abstração única de LLM (litellm → Ollama)
- Rate limiting via asyncio.Semaphore (≤ 3 req/min)
- Retry exponencial com tenacity (máx 2 tentativas)
- Cache de respostas com diskcache (TTL=3600s)
- Timeout de 60s por chamada
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any, Final

import diskcache
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

__all__ = ["LLMClient", "LLMError", "LLMTimeoutError"]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
OLLAMA_HOST: Final[str] = os.getenv("EDU_OLLAMA_HOST", "http://host.docker.internal:11434")
LLM_TIMEOUT_S: Final[float] = 60.0
LLM_MAX_RETRIES: Final[int] = 2
LLM_BACKOFF_MIN: Final[float] = 2.0
LLM_BACKOFF_MAX: Final[float] = 10.0
RATE_LIMIT_RPM: Final[int] = 3
CALL_INTERVAL_S: Final[float] = 60.0 / RATE_LIMIT_RPM  # 20s entre chamadas
CACHE_TTL_S: Final[int] = 3600
CACHE_DIR: Final[str] = "/tmp/edu_llm_cache"  # dentro do container


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Erro genérico de comunicação com o LLM."""


class LLMTimeoutError(LLMError):
    """Timeout na chamada ao LLM."""


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class LLMClient:
    """Cliente assíncrono para Ollama com rate limiting, cache e retry.

    Usage:
        client = LLMClient(model="mistral")
        response = await client.chat(system_prompt=SYSTEM, user_message=msg)
    """

    def __init__(self, model: str = "mistral") -> None:
        self._model = model
        self._semaphore = asyncio.Semaphore(1)   # 1 chamada simultânea
        self._last_call_time: float = 0.0
        self._cache: diskcache.Cache = diskcache.Cache(CACHE_DIR, size_limit=500_000_000)
        log.info("llm_client_initialized", model=self._model, host=OLLAMA_HOST)

    # ── Cache ──────────────────────────────────────────────────────────────

    def _cache_key(self, system: str, user: str) -> str:
        """Gera chave de cache determinística para um par (system, user)."""
        raw = f"{self._model}:{system}:{user}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, system: str, user: str) -> dict[str, Any] | None:
        key = self._cache_key(system, user)
        result = self._cache.get(key)
        if result is not None:
            log.info("llm_cache_hit", key=key[:12])
        return result  # type: ignore[return-value]

    def _set_cached(self, system: str, user: str, value: dict[str, Any]) -> None:
        key = self._cache_key(system, user)
        self._cache.set(key, value, expire=CACHE_TTL_S)

    # ── Rate limiting ──────────────────────────────────────────────────────

    async def _wait_rate_limit(self) -> None:
        """Garante intervalo mínimo entre chamadas (20s para ≤ 3 rpm)."""
        elapsed = time.monotonic() - self._last_call_time
        wait = CALL_INTERVAL_S - elapsed
        if wait > 0:
            log.debug("llm_rate_limit_wait", seconds=round(wait, 1))
            await asyncio.sleep(wait)

    # ── Chamada principal ──────────────────────────────────────────────────

    async def _call_ollama_raw(self, system: str, user: str) -> dict[str, Any]:
        """Chama a API Ollama via litellm com timeout.

        Args:
            system: System prompt imutável (constante do advisor).
            user: Mensagem do usuário (já sanitizada).

        Returns:
            Conteúdo JSON parseado da resposta.

        Raises:
            LLMTimeoutError: Se a chamada exceder LLM_TIMEOUT_S.
            LLMError: Em qualquer outro erro de comunicação.
        """
        # Import aqui para facilitar mock em testes
        import litellm  # type: ignore[import]

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    litellm.completion,
                    model=f"ollama/{self._model}",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    api_base=OLLAMA_HOST,
                    format="json",
                    temperature=0.3,
                ),
                timeout=LLM_TIMEOUT_S,
            )
            raw_content: str = response.choices[0].message.content  # type: ignore[union-attr]
            return json.loads(raw_content)

        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"Ollama não respondeu em {LLM_TIMEOUT_S}s") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"Resposta do LLM não é JSON válido: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Erro na comunicação com Ollama: {exc}") from exc

    async def chat(self, *, system_prompt: str, user_message: str) -> dict[str, Any]:
        """Interface pública: envia mensagem ao LLM com cache, rate limit e retry.

        Args:
            system_prompt: Prompt de sistema imutável (definido no advisor).
            user_message: Mensagem do usuário — deve ser pré-sanitizada.

        Returns:
            Dicionário com a resposta do LLM (JSON parseado).

        Raises:
            LLMTimeoutError: Após retry máximo por timeout.
            LLMError: Após retry máximo por outro erro.
        """
        # 1. Cache hit?
        cached = self._get_cached(system_prompt, user_message)
        if cached is not None:
            return cached

        # 2. Rate limiting + semáforo (1 chamada simultânea)
        async with self._semaphore:
            await self._wait_rate_limit()

            # 3. Retry exponencial
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(LLM_MAX_RETRIES),
                    wait=wait_exponential(min=LLM_BACKOFF_MIN, max=LLM_BACKOFF_MAX),
                    retry=retry_if_exception_type(LLMError),
                    reraise=True,
                ):
                    with attempt:
                        log.info(
                            "llm_call_start",
                            model=self._model,
                            attempt=attempt.retry_state.attempt_number,
                        )
                        result = await self._call_ollama_raw(system_prompt, user_message)

            except (LLMError, LLMTimeoutError) as exc:
                log.error("llm_call_failed", model=self._model, error=str(exc))
                raise
            finally:
                self._last_call_time = time.monotonic()

        # 4. Cachear resultado válido
        self._set_cached(system_prompt, user_message, result)
        log.info("llm_call_success", model=self._model)
        return result

    def close(self) -> None:
        """Fecha o cache de disco."""
        self._cache.close()
