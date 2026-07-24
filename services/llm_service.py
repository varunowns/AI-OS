"""
LLM Service
-----------
Thin wrapper around the Anthropic API. Plugins call `ask()` rather than
touching the API directly — this is the seam where multi-provider support
(GPT, Gemini, local models) gets added later, per PLUGIN_SPEC's
"no hardcoded providers" rule. For the vertical slice, one provider is enough.

Requires: pip install anthropic
"""

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from core.plugin_registry import require

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = LLM_API_KEY or ANTHROPIC_API_KEY
        if not api_key:
            raise RuntimeError(
                "No API key configured. Set ANTHROPIC_API_KEY or AI_OS_LLM_API_KEY in your .env file."
            )
        kwargs = {"api_key": api_key}
        if LLM_BASE_URL:
            kwargs["base_url"] = LLM_BASE_URL
        _client = Anthropic(**kwargs)
    return _client


@require("llm:call")
def ask(prompt: str, system: str | None = None, max_tokens: int = 1024) -> str:
    """Send a single-turn prompt to Claude and return the text response."""
    client = _get_client()
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        system=system or "",
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")