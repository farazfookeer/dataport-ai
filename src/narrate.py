from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import Anthropic

from .logger import RunLogger

DEFAULT_MODEL = "claude-sonnet-4-6"

CATEGORIES = [
    "Trends",
    "Anomalies",
    "Distributions",
    "Relationships",
    "Segments",
    "Comparisons",
    "Composition",
    "Data Quality",
]

CATEGORY_TO_VIZ = {
    "Trends": ["Line chart", "Area chart"],
    "Anomalies": ["Highlight table", "Scatter plot with outlier coloring"],
    "Distributions": ["Histogram", "Box plot"],
    "Relationships": ["Scatter plot", "Correlation heatmap"],
    "Segments": ["Grouped bar", "Treemap"],
    "Comparisons": ["Bar chart", "Bullet chart"],
    "Composition": ["Stacked bar", "Pie", "Treemap"],
    "Data Quality": ["Profile table (pre-Tableau)"],
}

SYSTEM_PROMPT = """You are a senior data analyst helping a university student prepare a
dataset for Tableau. You receive a list of raw statistical findings about their dataset.

Your job:
1. Assign each finding to EXACTLY ONE category from this fixed list:
   Trends, Anomalies, Distributions, Relationships, Segments, Comparisons, Composition, Data Quality
2. Rewrite each finding as a clear, useful "data story" the student can use as a
   talking point in their Tableau dashboard. One or two sentences. Concrete and
   specific to the column names and numbers given. Avoid hedging.
3. For each category that has at least one finding, write a 2-3 sentence
   "category narrative" summarizing what the data is telling us in that category.

Respond with VALID JSON ONLY, matching this schema exactly:
{
  "stories": [
    {
      "finding_id": <int>,
      "category": "<one of the categories>",
      "headline": "<short title, max 8 words>",
      "story": "<1-2 sentence narrative>"
    }
  ],
  "category_narratives": {
    "<Category>": "<2-3 sentence summary>"
  }
}

Do not include any prose outside the JSON. Do not invent numbers not in the findings."""


class NarrateError(RuntimeError):
    pass


def narrate(
    findings: list[dict[str, Any]],
    profile_data: dict[str, Any],
    logger: RunLogger,
    model: str | None = None,
) -> dict[str, Any]:
    """Send findings to Claude, get categorized stories + per-category narratives.

    Raises NarrateError if API key missing or response is malformed.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise NarrateError(
            "ANTHROPIC_API_KEY is required. Set it via env var or .env file."
        )

    if not findings:
        logger.log("NARRATE", "No findings to narrate")
        return {"stories": [], "category_narratives": {}, "by_category": {}}

    model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    logger.log("NARRATE", f"Calling {model} with {len(findings)} findings")

    enumerated = [
        {"finding_id": i, **f} for i, f in enumerate(findings)
    ]
    user_payload = {
        "dataset_overview": profile_data.get("overall", {}),
        "findings": [
            {
                "finding_id": f["finding_id"],
                "type": f["type"],
                "columns": f["columns"],
                "summary": f["summary"],
                "payload": f["payload"],
            }
            for f in enumerated
        ],
    }

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    "Categorize and narrate these findings. JSON only:\n\n"
                    + json.dumps(user_payload, default=str)
                ),
            }
        ],
    )

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    parsed = _extract_json(raw_text)
    if not parsed or "stories" not in parsed:
        raise NarrateError(
            f"Claude response did not contain valid JSON. Raw: {raw_text[:400]}"
        )

    by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for story in parsed.get("stories", []):
        fid = story.get("finding_id")
        cat = story.get("category", "Data Quality")
        if cat not in by_category:
            cat = "Data Quality"
        finding = findings[fid] if isinstance(fid, int) and 0 <= fid < len(findings) else {}
        by_category[cat].append(
            {
                "headline": story.get("headline", "Insight"),
                "story": story.get("story", ""),
                "viz_recommendations": CATEGORY_TO_VIZ.get(cat, []),
                "raw_finding": finding,
            }
        )

    by_category = {k: v for k, v in by_category.items() if v}
    logger.log(
        "NARRATE",
        f"Categorized into {len(by_category)} buckets: {', '.join(by_category)}",
    )

    return {
        "stories": parsed.get("stories", []),
        "category_narratives": parsed.get("category_narratives", {}),
        "by_category": by_category,
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from the model's response, tolerating
    surrounding code fences."""
    text = text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None
