"""One place that talks to the model provider. Swap this out if you use a different API.

Set PULSENOTE_MODEL to the exact model name you want to evaluate and log it in your README.
Set PULSENOTE_TEMPERATURE (for example 0) if your model supports it and you want steadier runs.
"""

import os
import time


def make_anthropic_call(max_tokens: int = 2000):
    import anthropic  # pip install anthropic; reads ANTHROPIC_API_KEY from the environment

    client = anthropic.Anthropic()
    model = os.environ.get("PULSENOTE_MODEL", "claude-3-5-sonnet-20241022")
    temperature = os.environ.get("PULSENOTE_TEMPERATURE")

    def call(system: str, user: str) -> str:
        kwargs = {"temperature": float(temperature)} if temperature is not None else {}
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        return msg.content[0].text

    return call


def make_gemini_call(max_tokens: int = 4000):
    from google import genai  # pip install google-genai; reads GEMINI_API_KEY from environment
    from google.genai import types

    client = genai.Client()
    preferred_model = os.environ.get("PULSENOTE_MODEL", "gemini-2.5-flash")
    temperature = os.environ.get("PULSENOTE_TEMPERATURE", "0.0")

    # Order of candidate models to try (preferred first)
    candidates = [preferred_model]
    for m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.8-flash"]:
        if m not in candidates:
            candidates.append(m)

    def call(system: str, user: str) -> str:
        last_err = None
        for model_name in candidates:
            for attempt in range(2):
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=float(temperature) if temperature is not None else None,
                        max_output_tokens=max_tokens,
                        response_mime_type="application/json",
                    )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=user,
                        config=config,
                    )
                    if resp.text:
                        return resp.text
                except Exception as e:
                    last_err = e
                    err_str = str(e).lower()
                    # If high demand (503) or rate limit (429), back off and retry or fail over
                    if "503" in err_str or "unavailable" in err_str or "high demand" in err_str:
                        time.sleep(3 * (attempt + 1))
                        continue
                    if "429" in err_str or "resource_exhausted" in err_str:
                        time.sleep(4 * (attempt + 1))
                        continue
                    # If model not found or other client error, try next candidate model
                    break
        raise RuntimeError(f"Gemini API generation failed across candidate models. Last error: {last_err}")

    return call


def get_llm_call(max_tokens: int = 2000):
    """Automatically select provider based on PULSENOTE_PROVIDER or available API keys."""
    provider = os.environ.get("PULSENOTE_PROVIDER", "").lower()
    if provider == "anthropic" or (not provider and "ANTHROPIC_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ):
        return make_anthropic_call(max_tokens=max_tokens)
    return make_gemini_call(max_tokens=max_tokens)

