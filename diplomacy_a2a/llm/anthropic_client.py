"""Anthropic implementation of LLMClient.

Wraps `anthropic.Anthropic` and exposes our provider-neutral `chat()`
interface. Adds prompt caching on the system prompt — for Diplomacy
the rules + persona + power assignment are re-sent on every call, so
caching cuts those tokens to ~10% of normal price after the first
write-to-cache.

Adds an explicit **retry + classify + log** layer on top of the SDK
(the SDK's own retries are disabled). On every API call:

- *Retryable* failures (rate limits, server errors, network blips,
  timeouts) are retried with exponential backoff up to `max_retries`,
  honoring any `retry-after` header.
- *Fatal* failures (auth, permission/credits, bad request, etc.) raise
  `RunnerError` with a friendly, actionable message — no silent retries
  that burn time when credits are out.
- Every retry attempt and final failure can be reported to a logger
  callback (the runner uses this to write `api_error` events into the
  transcript for forensics).

API key is read from `ANTHROPIC_API_KEY` by the SDK. Callers run
`dotenv.load_dotenv()` before instantiating this client.
"""
from __future__ import annotations

import time
from typing import Callable, Sequence

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message


class RunnerError(Exception):
    """Fatal API or runner error. Stops the run; message is end-user friendly."""


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

# Newer model tiers deprecate an explicit `temperature` and run only at the
# provider default; older Sonnet/Haiku still accept it. The parameter is
# omitted for known tiers proactively, and chat() self-heals if any other
# model rejects it with a 400.
_OMIT_TEMPERATURE_PREFIXES: tuple[str, ...] = ("claude-opus-4-8",)


def _omits_temperature(model: str) -> bool:
    return any(model.startswith(p) for p in _OMIT_TEMPERATURE_PREFIXES)


def _is_temperature_rejection(e: Exception) -> bool:
    return isinstance(e, BadRequestError) and "temperature" in str(e).lower()


def _categorize(e: Exception) -> str:
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
    msg = str(e)
    if isinstance(e, PermissionDeniedError) and "credit" in msg.lower():
        return RunnerError(
            "Anthropic API: insufficient credits. Add funds at "
            "https://console.anthropic.com/settings/billing and re-run.\n"
            f"Original error: {e}"
        )
    if isinstance(e, AuthenticationError):
        return RunnerError(
            "Anthropic API: authentication failed. Check ANTHROPIC_API_KEY in .env.\n"
            f"Original error: {e}"
        )
    if isinstance(e, BadRequestError):
        return RunnerError(
            "Anthropic API: bad request (likely an oversized prompt or invalid model id).\n"
            f"Original error: {e}"
        )
    return RunnerError(f"Anthropic API fatal error ({type(e).__name__}): {e}")


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


class AnthropicClient(LLMClient):
    def __init__(
        self,
        model: str,
        *,
        max_retries: int = 4,
        verbose_retries: bool = True,
    ) -> None:
        self.model = model
        # Our retry layer is the only one — visibility wins over silent retries.
        self._client = Anthropic(max_retries=0)
        self._max_retries = max_retries
        self._verbose_retries = verbose_retries
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
        include_temperature = not _omits_temperature(self.model)
        for attempt in range(1, self._max_retries + 2):  # one final attempt past max
            try:
                kwargs = dict(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                )
                if include_temperature:
                    kwargs["temperature"] = temperature
                response = self._client.messages.create(**kwargs)
            except _FATAL_TYPES as e:
                # A model that deprecates an explicit temperature rejects it
                # with a 400. Drop the parameter and retry rather than aborting.
                if include_temperature and _is_temperature_rejection(e):
                    include_temperature = False
                    continue
                self._log_error(attempt, e, fatal=True)
                raise _friendly_fatal(e) from e
            except _RETRYABLE_TYPES as e:
                last_chance = attempt > self._max_retries
                self._log_error(attempt, e, fatal=last_chance)
                if last_chance:
                    raise RunnerError(
                        f"Anthropic API gave up after {self._max_retries} retries. "
                        f"Last error ({type(e).__name__}): {e}"
                    ) from e
                wait = _retry_wait(e, attempt)
                if self._verbose_retries:
                    print(
                        f"  [WARN] {type(e).__name__} from Anthropic API — retrying "
                        f"in {wait:.1f}s (attempt {attempt}/{self._max_retries})",
                        flush=True,
                    )
                time.sleep(wait)
                continue
            else:
                text = "".join(block.text for block in response.content if block.type == "text")
                usage = response.usage
                return ChatResult(
                    text=text,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                    raw=response,
                )
        # Loop exit unreachable in practice, but keep the type checker happy.
        raise RunnerError("Anthropic API: retry loop exited without a result")  # pragma: no cover

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
