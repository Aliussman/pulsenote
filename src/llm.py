"""One place that talks to the model provider. Swap this out if you use a different API.

Set PULSENOTE_MODEL to the exact model name you want to evaluate and log it in your README.
Set PULSENOTE_TEMPERATURE (for example 0) if your model supports it and you want steadier runs.
"""

import os


def make_anthropic_call(max_tokens: int = 2000):
    import anthropic  # pip install anthropic; reads ANTHROPIC_API_KEY from the environment

    client = anthropic.Anthropic()
    model = os.environ["PULSENOTE_MODEL"]
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
