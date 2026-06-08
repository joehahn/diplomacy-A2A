"""OpenRouter implementation of LLMClient.

Wraps the `openai` SDK pointed at OpenRouter's OpenAI-compatible endpoint
and exposes our provider-neutral `chat()` interface. This is the seam for
cheap-model playtests (Gemini, DeepSeek, Kimi, MiniMax) without juggling a
separate SDK and key per provider.

Mirrors `AnthropicClient`'s retry + classify + log layer (the SDK's own
retries are disabled so visibility wins). Raises the same `RunnerError` on
fatal failures, so callers that already catch it need no change.

OpenRouter does not expose Anthropic-style prompt caching through this path,
so the system prompt is sent as a plain leading message and the cache fields
on `ChatResult` stay 0.

Reasoning models (e.g. Kimi K2.6) bill a hidden chain-of-thought as output
that counts against `max_tokens`; with the harness's small per-call budgets
the reasoning can consume the whole budget and leave empty content. By
default this client disables reasoning (`reasoning: {enabled: false}`) so the
budget goes to the answer, and it treats empty content as a retry-then-fail
condition instead of silently returning "". Pass `enable_reasoning=True` to
keep reasoning on, in which case give the call a much larger `max_tokens`.

The key is read from `OPENROUTER_API_KEY`. Callers run `dotenv.load_dotenv()`
before instantiating this client.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from diplomacy_a2a.llm.anthropic_client import RunnerError
from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message

_BASE_URL = "https://openrouter.ai/api/v1"

# Errors that mean "retry won't help" — abort the run immediately.
_FATAL_TYPES: tuple[type[Exception], ...] = (
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    NotFoundError,
    UnprocessableEntityError,
)

# Errors that are usually transient — back off and retry.
_RETRYABLE_TYPES: tuple[type[Exception], ...] = (
    RateLimitError,
    InternalServerError,
    APIConnectionError,
    APITimeoutError,
)


def _is_temperature_rejection(e: Exception) -> bool:
    return isinstance(e, BadRequestError) and "temperature" in str(e).lower()


def _is_reasoning_rejection(e: Exception) -> bool:
    return isinstance(e, BadRequestError) and "reasoning" in str(e).lower()


class _EmptyResponse(Exception):
    """The model returned no usable text. Carries the finish_reason so the
    retry/error layer can explain the likely cause (reasoning models can burn
    the whole token budget on hidden reasoning and emit empty content)."""

    def __init__(self, finish_reason: str | None) -> None:
        super().__init__(f"empty content (finish_reason={finish_reason})")
        self.finish_reason = finish_reason


def _categorize(e: Exception) -> str:
    if isinstance(e, _EmptyResponse):
        return "empty_response"
    if isinstance(e, RateLimitError):
        return "rate_limit"
    if isinstance(e, PermissionDeniedError):
        return "permission_or_credits"
    if isinstance(e, AuthenticationError):
        return "auth"
    if isinstance(e, InternalServerError):
        return "server_error"
    if isinstance(e, APITimeoutError):
        return "timeout"
    if isinstance(e, APIConnectionError):
        return "network"
    if isinstance(e, BadRequestError):
        return "bad_request"
    if isinstance(e, NotFoundError):
        return "not_found"
    if isinstance(e, UnprocessableEntityError):
        return "unprocessable"
    return "other"


def _friendly_fatal(e: Exception) -> RunnerError:
    """Wrap a fatal API exception with an actionable error message."""
    msg = str(e).lower()
    if isinstance(e, (PermissionDeniedError, RateLimitError)) and "credit" in msg:
        return RunnerError(
            "OpenRouter API: insufficient credits. Add funds at "
            "https://openrouter.ai/settings/credits and re-run.\n"
            f"Original error: {e}"
        )
    if isinstance(e, AuthenticationError):
        return RunnerError(
            "OpenRouter API: authentication failed. Check OPENROUTER_API_KEY in .env.\n"
            f"Original error: {e}"
        )
    if isinstance(e, NotFoundError):
        return RunnerError(
            "OpenRouter API: model not found (check the model id in config.py against "
            "https://openrouter.ai/models).\n"
            f"Original error: {e}"
        )
    if isinstance(e, BadRequestError):
        return RunnerError(
            "OpenRouter API: bad request (likely an oversized prompt or unsupported parameter).\n"
            f"Original error: {e}"
        )
    return RunnerError(f"OpenRouter API fatal error ({type(e).__name__}): {e}")


def _retry_wait(e: Exception, attempt: int) -> float:
    """Seconds to wait before next attempt. Honors `retry-after` if present,
    otherwise exponential backoff capped at 30 s."""
    try:
        if isinstance(e, APIStatusError):
            ra = e.response.headers.get("retry-after")
            if ra:
                return min(float(ra), 60.0)
    except (AttributeError, ValueError, TypeError):
        pass
    return min(2 ** (attempt - 1), 30.0)


ErrorLogger = Callable[[dict], None]


class GatewayClient(LLMClient):
    def __init__(
        self,
        model: str,
        *,
        max_retries: int = 4,
        verbose_retries: bool = True,
        enable_reasoning: bool = False,
    ) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RunnerError(
                "OpenRouter API: OPENROUTER_API_KEY is not set. Add it to .env "
                "(see .env.example) to use gateway models."
            )
        self.model = model
        # Our retry layer is the only one — visibility wins over silent retries.
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL, max_retries=0)
        self._max_retries = max_retries
        self._verbose_retries = verbose_retries
        # Reasoning models hide a chain-of-thought that is billed as output and
        # counts against max_tokens; with the harness's small per-call budgets it
        # can consume the whole budget and leave empty content. Default off so
        # the budget goes to the answer; the agent's explicit strategy step is
        # the visible reasoning we actually want. Set True to let the model
        # reason (then give it a much larger max_tokens).
        self._enable_reasoning = enable_reasoning
        self._error_logger: ErrorLogger | None = None

    def set_error_logger(self, logger: ErrorLogger | None) -> None:
        """Runner attaches a logger so retries / failures land in the transcript."""
        self._error_logger = logger

    def chat(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
    ) -> ChatResult:
        include_temperature = True
        # When reasoning is off we ask OpenRouter to disable it explicitly; a
        # provider that does not accept the param self-heals below by dropping it.
        send_reasoning_off = not self._enable_reasoning
        for attempt in range(1, self._max_retries + 2):  # one final attempt past max
            try:
                kwargs = dict(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=(
                        [{"role": "system", "content": system}]
                        + [{"role": m.role, "content": m.content} for m in messages]
                    ),
                )
                if include_temperature:
                    kwargs["temperature"] = temperature
                if send_reasoning_off:
                    kwargs["extra_body"] = {"reasoning": {"enabled": False}}
                response = self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                text = choice.message.content or ""
                if not text.strip():
                    raise _EmptyResponse(getattr(choice, "finish_reason", None))
            except _EmptyResponse as e:
                # No usable text. Common cause: a reasoning model spent the whole
                # max_tokens budget on hidden reasoning. Retry, then fail loudly
                # rather than letting the caller treat empty as "no orders".
                last_chance = attempt > self._max_retries
                self._log_error(attempt, e, fatal=last_chance)
                if last_chance:
                    raise RunnerError(
                        f"OpenRouter API ({self.model}): returned empty content "
                        f"after {self._max_retries} retries (finish_reason="
                        f"{e.finish_reason}). If this is a reasoning model, the "
                        f"reasoning likely consumed the token budget: raise "
                        f"max_tokens or construct GatewayClient with "
                        f"enable_reasoning=False."
                    ) from e
                wait = _retry_wait(e, attempt)
                if self._verbose_retries:
                    print(
                        f"  [WARN] empty content from OpenRouter API ({self.model}) "
                        f"— retrying in {wait:.1f}s (attempt {attempt}/{self._max_retries})",
                        flush=True,
                    )
                time.sleep(wait)
                continue
            except _FATAL_TYPES as e:
                # Some models (reasoning tiers) reject an explicit temperature
                # with a 400. Drop the parameter and retry rather than aborting.
                if include_temperature and _is_temperature_rejection(e):
                    include_temperature = False
                    continue
                # A provider that does not accept the reasoning param: drop it.
                if send_reasoning_off and _is_reasoning_rejection(e):
                    send_reasoning_off = False
                    continue
                self._log_error(attempt, e, fatal=True)
                raise _friendly_fatal(e) from e
            except _RETRYABLE_TYPES as e:
                last_chance = attempt > self._max_retries
                self._log_error(attempt, e, fatal=last_chance)
                if last_chance:
                    raise RunnerError(
                        f"OpenRouter API gave up after {self._max_retries} retries. "
                        f"Last error ({type(e).__name__}): {e}"
                    ) from e
                wait = _retry_wait(e, attempt)
                if self._verbose_retries:
                    print(
                        f"  [WARN] {type(e).__name__} from OpenRouter API — retrying "
                        f"in {wait:.1f}s (attempt {attempt}/{self._max_retries})",
                        flush=True,
                    )
                time.sleep(wait)
                continue
            else:
                usage = response.usage
                return ChatResult(
                    text=text,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    raw=response,
                )
        # Loop exit unreachable in practice, but keep the type checker happy.
        raise RunnerError("OpenRouter API: retry loop exited without a result")  # pragma: no cover

    def _log_error(self, attempt: int, e: Exception, *, fatal: bool) -> None:
        if self._error_logger is None:
            return
        info: dict = {
            "attempt": attempt,
            "error_type": type(e).__name__,
            "fatal": fatal,
            "category": _categorize(e),
            "message": str(e)[:500],
            "model": self.model,
        }
        if isinstance(e, APIStatusError):
            info["status"] = getattr(e, "status_code", None)
        try:
            self._error_logger(info)
        except Exception:
            pass  # logger must never break the call itself
