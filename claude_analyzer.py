import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

DEFAULT_MODEL = "claude-sonnet-5"
BATCH_SIZE = 8
MAX_WORKERS = 3
MAX_AD_CHARS = 7000

SYSTEM_PROMPT = """
You are the semantic product-research engine inside a serious direct-response ecommerce research system.

GOAL
Evaluate PHYSICAL products for long-term, evergreen selling to adults, especially 35+, where the purchase is driven by a real recurring problem, frustration, discomfort, wasted time, lost independence, mess, sleep issue, home problem, car problem, pet problem, or similar practical pain.

WHAT A GREAT PRODUCT LOOKS LIKE
- The customer quickly recognizes: "I actually have this problem."
- The problem occurs repeatedly, not once in a lifetime.
- The solution can materially make daily life easier, more comfortable, safer, cleaner, faster, calmer, or less frustrating.
- It is understandable within seconds from an ad.
- It does not depend on TikTok hype, novelty, a meme, a short season, or aesthetics alone.
- It has plausible willingness to pay because the problem matters.
- It can appeal to a sufficiently broad adult market.
- It is a physical product.

IMPORTANT RULES
- Judge the PRODUCT OPPORTUNITY, not how polished the copywriting is.
- Do not reward fake urgency, discounts, exaggerated claims, or hype.
- Do not assume an ad is profitable.
- Ad longevity and cross-seller proof are calculated separately by code; do not invent sales/profit evidence.
- Use only evidence available in the pasted ad. If evidence is missing, lower confidence instead of inventing facts.
- Country must NOT affect the product score.
- Distinguish "nice to have" from "I want this because it fixes something annoying/painful."
- A product can be emotional without being dramatic: relief, independence, comfort, avoiding embarrassment, saving time, reducing daily frustration, protecting family/home, and sleeping better all count.
- Penalize commodity products that are easily price-compared and products whose appeal is mostly trend/novelty.
- Penalize medical/health claims that appear risky or unsupported, but do not automatically reject ordinary comfort products.
- Output short explanatory text in Swedish, even when the ad is in another language.
- Never output chain-of-thought. Return only concise conclusions and numeric assessments.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "analyses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "physical_product": {"type": "boolean"},
                    "product_name": {"type": "string"},
                    "category": {"type": "string"},
                    "core_problem": {"type": "string"},
                    "target_customer": {"type": "string"},
                    "purchase_reason": {"type": "string"},
                    "problem_severity": {"type": "number"},
                    "problem_frequency": {"type": "number"},
                    "emotional_pressure": {"type": "number"},
                    "fit_35_plus": {"type": "number"},
                    "evergreen_strength": {"type": "number"},
                    "willingness_to_pay": {"type": "number"},
                    "value_proposition": {"type": "number"},
                    "three_second_clarity": {"type": "number"},
                    "demo_strength": {"type": "number"},
                    "market_breadth": {"type": "number"},
                    "commodity_risk": {"type": "number"},
                    "seasonality_risk": {"type": "number"},
                    "compliance_risk": {"type": "number"},
                    "confidence": {"type": "number"},
                    "why_it_could_win": {"type": "string"},
                    "why_it_could_fail": {"type": "string"},
                    "red_flags": {"type": "array", "items": {"type": "string"}}
                },
                "required": [
                    "index", "physical_product", "product_name", "category",
                    "core_problem", "target_customer", "purchase_reason",
                    "problem_severity", "problem_frequency", "emotional_pressure",
                    "fit_35_plus", "evergreen_strength", "willingness_to_pay",
                    "value_proposition", "three_second_clarity", "demo_strength",
                    "market_breadth", "commodity_risk", "seasonality_risk",
                    "compliance_risk", "confidence", "why_it_could_win",
                    "why_it_could_fail", "red_flags"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["analyses"],
    "additionalProperties": False
}


def is_configured():
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def model_name():
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _clamp(v):
    try:
        return round(max(0.0, min(10.0, float(v))), 1)
    except (TypeError, ValueError):
        return 0.0


def _normalize_analysis(a):
    numeric = [
        "problem_severity", "problem_frequency", "emotional_pressure",
        "fit_35_plus", "evergreen_strength", "willingness_to_pay",
        "value_proposition", "three_second_clarity", "demo_strength",
        "market_breadth", "commodity_risk", "seasonality_risk",
        "compliance_risk", "confidence"
    ]
    for key in numeric:
        a[key] = _clamp(a.get(key))
    a["red_flags"] = [str(x)[:160] for x in (a.get("red_flags") or [])[:8]]
    for key in [
        "product_name", "category", "core_problem", "target_customer",
        "purchase_reason", "why_it_could_win", "why_it_could_fail"
    ]:
        a[key] = str(a.get(key) or "").strip()[:500]
    a["physical_product"] = bool(a.get("physical_product"))
    return a


def semantic_score(a):
    """Score is calculated by code, not handed to Claude as one arbitrary number."""
    score10 = (
        a["problem_severity"] * 0.16 +
        a["problem_frequency"] * 0.10 +
        a["emotional_pressure"] * 0.12 +
        a["fit_35_plus"] * 0.13 +
        a["evergreen_strength"] * 0.13 +
        a["willingness_to_pay"] * 0.12 +
        a["value_proposition"] * 0.09 +
        a["three_second_clarity"] * 0.06 +
        a["demo_strength"] * 0.04 +
        a["market_breadth"] * 0.05
    )
    score10 -= a["commodity_risk"] * 0.08
    score10 -= a["seasonality_risk"] * 0.06
    score10 -= a["compliance_risk"] * 0.04

    if not a["physical_product"]:
        score10 = min(score10, 2.5)
    if a["problem_severity"] < 4.5:
        score10 -= 0.8
    if a["problem_frequency"] < 4.0:
        score10 -= 0.5
    if a["evergreen_strength"] < 5.5:
        score10 -= 0.7
    if a["fit_35_plus"] < 4.0:
        score10 -= 0.35

    return round(max(0.0, min(10.0, score10)) * 10, 1)


def _build_user_content(batch):
    parts = [
        "Analyze every ad below independently. Use the exact AD INDEX to map your result.",
        "Scores are 0-10 where 10 is strongest/highest. For risk fields, 10 = highest risk.",
        ""
    ]
    for item in batch:
        parts.append(f"===== AD INDEX {item['index']} =====")
        parts.append((item["text"] or "")[:MAX_AD_CHARS])
        parts.append("")
    return "\n".join(parts)


def _analyze_batch(batch):
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_retries=3,
        timeout=120.0,
    )
    response = client.messages.create(
        model=model_name(),
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_content(batch)}],
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
        },
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
    payload = json.loads("".join(text_blocks))
    result = {}
    for a in payload.get("analyses", []):
        a = _normalize_analysis(a)
        idx = int(a.get("index", -1))
        a["semantic_score"] = semantic_score(a)
        a["ai_model"] = model_name()
        result[idx] = a
    return result


def analyze_ads_with_claude(blocks):
    """Analyze every unique ad, batching and parallelizing for larger pastes."""
    if not is_configured():
        raise RuntimeError("ANTHROPIC_API_KEY saknas.")

    indexed = [{"index": i, "text": block} for i, block in enumerate(blocks)]
    batches = [indexed[i:i+BATCH_SIZE] for i in range(0, len(indexed), BATCH_SIZE)]
    combined = {}
    errors = []

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(batches)))) as pool:
        future_map = {pool.submit(_analyze_batch, batch): batch for batch in batches}
        for future in as_completed(future_map):
            batch = future_map[future]
            try:
                combined.update(future.result())
            except Exception as exc:
                errors.append({
                    "indexes": [x["index"] for x in batch],
                    "error": str(exc)[:300]
                })

    missing = [i for i in range(len(blocks)) if i not in combined]
    if missing:
        for idx in missing:
            try:
                combined.update(_analyze_batch([{"index": idx, "text": blocks[idx]}]))
            except Exception as exc:
                errors.append({"indexes": [idx], "error": str(exc)[:300]})

    missing = [i for i in range(len(blocks)) if i not in combined]
    if missing:
        raise RuntimeError(
            "Claude kunde inte analysera alla annonser. Misslyckade index: "
            + ", ".join(map(str, missing[:20]))
        )

    return [combined[i] for i in range(len(blocks))], errors
