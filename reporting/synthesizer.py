"""
reporting/synthesizer.py
Use Claude to synthesize all pipeline outputs into a markdown research report.
"""

import json
from pathlib import Path

import anthropic

from agents._utils import api_call

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesis.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


def synthesize_report(
    theme: dict,
    hypotheses: list[dict],
    precedents: dict,
    backtest_results: list[dict],
    model: str,
    trace,
) -> str:
    """
    Generate the full markdown research report narrative.

    Args:
        theme: theme dict
        hypotheses: list of hypothesis dicts
        precedents: dict mapping ticker -> list of episode dicts
        backtest_results: list of backtest result dicts
        model: Claude model string (may be opus for --quality high)
        trace: ExecutionTrace instance

    Returns:
        Markdown string (without title header — added by pipeline.py)
    """
    client = anthropic.Anthropic()

    payload = {
        "theme": theme,
        "hypotheses": hypotheses,
        "precedents": precedents,
        "backtest_results": backtest_results,
    }

    response = api_call(
        client,
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Synthesize the following research pipeline output into a full "
                    "investment research report:\n\n"
                    + json.dumps(payload, indent=2)
                ),
            }
        ],
    )
    trace.record_claude_call("synthesizer", model, response.usage)

    return next(b.text for b in response.content if hasattr(b, "text"))
