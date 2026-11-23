"""The one door to Claude. Every call returns parsed JSON, or the caller's offline fallback."""
import json
import logging

import anthropic

from config import EFFORT, MODEL, OFFLINE

log = logging.getLogger("llm")
_client = None if OFFLINE else anthropic.AsyncAnthropic(timeout=40.0, max_retries=1)


def obj(props: dict, required: list | None = None) -> dict:
    """Small helper for strict JSON schemas."""
    return {"type": "object", "properties": props,
            "required": required or list(props), "additionalProperties": False}


async def ask_json(system: str, user: str, schema: dict, fallback, max_tokens: int = 4000) -> dict:
    if _client is None:
        out = fallback()
        out["_src"] = "offline"
        return out
    try:
        resp = await _client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise ValueError(f"stop_reason={resp.stop_reason}")
        text = next(b.text for b in resp.content if b.type == "text")
        out = json.loads(text)
        out["_src"] = "llm"
        return out
    except anthropic.RateLimitError as e:
        log.warning("rate limited, using fallback: %s", e)
    except anthropic.APIStatusError as e:
        log.warning("API error %s, using fallback: %s", e.status_code, e.message)
    except anthropic.APIConnectionError as e:
        log.warning("connection error, using fallback: %s", e)
    except (ValueError, StopIteration, json.JSONDecodeError) as e:
        log.warning("bad response, using fallback: %s", e)
    out = fallback()
    out["_src"] = "offline"
    return out
