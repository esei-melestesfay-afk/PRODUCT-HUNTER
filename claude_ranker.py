import hashlib
import json
import math
import os
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select

from database import Ad, Cluster, ClusterMembership

REVIEW_VERSION = "v5.5-hybrid-1"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_FINALISTS = 10
DEFAULT_MIN_OPPORTUNITY = 50.0
MAX_AD_SAMPLES = 3
MAX_AD_CHARS = 2600

SYSTEM_PROMPT = """
You are the final semantic judge inside PRODUCT HUNTER V5, a serious ecommerce product-research system.

You do NOT inspect every ad. Deterministic code already parsed, deduplicated, clustered and scored a large Meta Ad Library paste. You only receive the strongest product clusters as finalists.

YOUR JOB
Judge the PRODUCT OPPORTUNITY behind each cluster, not the quality of the copywriter. Be skeptical, concise and evidence-bound.

PRIORITIZE
- A real recurring problem, frustration, discomfort, wasted time, lost independence, mess, sleep issue, home/car/pet problem, or other practical pain.
- Emotional buying motives grounded in relief, comfort, independence, embarrassment avoidance, safety, protecting home/family, saving time, reduced frustration or better sleep.
- Repeated/frequent problems over one-off problems.
- Evergreen demand over novelty, hype, meme, trend or short season.
- Clear product demonstration and a solution understandable in seconds.
- Plausible willingness to pay because the problem matters.
- Broad adult usefulness, especially realistic 35+ fit, without stereotypes.

DO NOT
- Infer profit, ROAS, spend, sales or winner status from ad longevity.
- Reward fake urgency, discounts, dramatic wording or TikTok hype by themselves.
- Let research country affect any score.
- Invent facts missing from the supplied ads.
- Treat multiple ads from one advertiser as independent market proof.
- Output chain-of-thought.

IMPORTANT
Market Proof is calculated separately by deterministic code from observed advertisers/runtime/creative evidence. Do not recreate or override Market Proof. Your scores should answer: "How strong is this product opportunity if the observed ads really describe this product?"

Return only the requested structured JSON. All explanatory strings must be short Swedish.
"""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_id": {"type": "integer"},
                    "physical_product": {"type": "boolean"},
                    "product_identity_confidence": {"type": "number"},
                    "problem_severity": {"type": "number"},
                    "problem_frequency": {"type": "number"},
                    "emotional_pressure": {"type": "number"},
                    "purchase_urgency": {"type": "number"},
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
                    "summary_sv": {"type": "string"},
                    "strongest_reason_sv": {"type": "string"},
                    "biggest_risk_sv": {"type": "string"}
                },
                "required": [
                    "cluster_id", "physical_product", "product_identity_confidence",
                    "problem_severity", "problem_frequency", "emotional_pressure",
                    "purchase_urgency", "fit_35_plus", "evergreen_strength",
                    "willingness_to_pay", "value_proposition", "three_second_clarity",
                    "demo_strength", "market_breadth", "commodity_risk",
                    "seasonality_risk", "compliance_risk", "confidence",
                    "summary_sv", "strongest_reason_sv", "biggest_risk_sv"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["reviews"],
    "additionalProperties": False
}


def is_configured():
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


def model_name():
    return (os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def finalist_limit():
    try:
        return max(1, min(20, int(os.environ.get("CLAUDE_AUTO_FINALISTS", DEFAULT_FINALISTS))))
    except Exception:
        return DEFAULT_FINALISTS


def min_opportunity():
    try:
        return max(0.0, min(100.0, float(os.environ.get("CLAUDE_MIN_OPPORTUNITY", DEFAULT_MIN_OPPORTUNITY))))
    except Exception:
        return DEFAULT_MIN_OPPORTUNITY


def _clamp10(value):
    try:
        return round(max(0.0, min(10.0, float(value))), 1)
    except (TypeError, ValueError):
        return 0.0


def _load_json(value, default=None):
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def claude_semantic_score(review):
    """Calculate Claude's semantic score in code; Claude never supplies one opaque final number."""
    positive = (
        review["problem_severity"] * 0.15
        + review["problem_frequency"] * 0.09
        + review["emotional_pressure"] * 0.13
        + review["purchase_urgency"] * 0.10
        + review["fit_35_plus"] * 0.11
        + review["evergreen_strength"] * 0.12
        + review["willingness_to_pay"] * 0.10
        + review["value_proposition"] * 0.07
        + review["three_second_clarity"] * 0.05
        + review["demo_strength"] * 0.04
        + review["market_breadth"] * 0.04
    )
    score10 = positive
    score10 -= review["commodity_risk"] * 0.06
    score10 -= review["seasonality_risk"] * 0.06
    score10 -= review["compliance_risk"] * 0.08

    if review["problem_severity"] < 4.0 and review["emotional_pressure"] < 4.0:
        score10 -= 0.8
    if review["evergreen_strength"] < 5.0:
        score10 -= 0.6
    if not review.get("physical_product", True):
        score10 = min(score10, 2.5)
    return round(max(0.0, min(10.0, score10)) * 10.0, 1)


def hybrid_score(deterministic_score, review):
    """Blend deterministic evidence with Claude, scaling Claude weight by review confidence."""
    det = max(0.0, min(100.0, float(deterministic_score or 0)))
    ai = float(review.get("claude_score") or claude_semantic_score(review))
    effective_conf = min(
        _clamp10(review.get("confidence")),
        _clamp10(review.get("product_identity_confidence")),
    )
    ai_weight = 0.12 + 0.23 * (effective_conf / 10.0)
    final = det * (1.0 - ai_weight) + ai * ai_weight

    if not review.get("physical_product", True):
        final = min(final, 35.0)
    if _clamp10(review.get("compliance_risk")) >= 8.0:
        final = min(final, 42.0)
    return round(max(0.0, min(100.0, final)), 1), round(ai_weight, 3)


def _normalize_review(review):
    numeric = [
        "product_identity_confidence", "problem_severity", "problem_frequency",
        "emotional_pressure", "purchase_urgency", "fit_35_plus",
        "evergreen_strength", "willingness_to_pay", "value_proposition",
        "three_second_clarity", "demo_strength", "market_breadth",
        "commodity_risk", "seasonality_risk", "compliance_risk", "confidence",
    ]
    for key in numeric:
        review[key] = _clamp10(review.get(key))
    review["physical_product"] = bool(review.get("physical_product"))
    for key in ("summary_sv", "strongest_reason_sv", "biggest_risk_sv"):
        review[key] = str(review.get(key) or "").strip()[:420]
    review["cluster_id"] = int(review.get("cluster_id"))
    review["claude_score"] = claude_semantic_score(review)
    return review


def _cluster_ads(session, cluster_id):
    return session.execute(
        select(Ad)
        .join(ClusterMembership, ClusterMembership.ad_id == Ad.id)
        .where(ClusterMembership.cluster_id == cluster_id)
        .order_by(Ad.ad_age_days.desc(), Ad.created_at.desc())
    ).scalars().all()


def _sample_ads(ads):
    selected = []
    seen_companies = set()
    for ad in ads:
        company_key = (ad.company_normalized or ad.company or "").strip()
        if company_key in seen_companies:
            continue
        selected.append(ad)
        seen_companies.add(company_key)
        if len(selected) >= MAX_AD_SAMPLES:
            break
    if len(selected) < MAX_AD_SAMPLES:
        chosen_ids = {a.id for a in selected}
        for ad in ads:
            if ad.id in chosen_ids:
                continue
            selected.append(ad)
            if len(selected) >= MAX_AD_SAMPLES:
                break
    return selected


def _evidence_hash(cluster, ads):
    evidence = {
        "review_version": REVIEW_VERSION,
        "cluster_id": cluster.id,
        "name": cluster.name,
        "category": cluster.category,
        "problem_type": cluster.problem_type,
        "deterministic_score": round(float(cluster.opportunity_score or 0), 1),
        "market_proof": round(float(cluster.market_proof or 0), 1),
        "ad_evidence": [
            {
                "id": ad.library_id or ad.fingerprint,
                "company": ad.company_normalized or ad.company,
                "status": ad.ad_status,
                "runtime": ad.ad_age_days,
            }
            for ad in ads
        ],
    }
    raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cluster_payload(session, cluster):
    ads = _cluster_ads(session, cluster.id)
    samples = _sample_ads(ads)
    breakdown = _load_json(cluster.breakdown_json)
    payload = {
        "cluster_id": cluster.id,
        "product_name": cluster.name,
        "category": cluster.category,
        "problem_type": cluster.problem_type,
        "deterministic_opportunity": round(float(cluster.opportunity_score or 0), 1),
        "market_proof": round(float(cluster.market_proof or 0), 1),
        "confidence": round(float(cluster.confidence or 0), 1),
        "age_status": cluster.age_status,
        "deterministic_breakdown": breakdown.get("opportunity", {}),
        "risk_breakdown": breakdown.get("penalties", {}),
        "observed_evidence": breakdown.get("market_proof", {}),
        "ads": [
            {
                "company": ad.company,
                "status": ad.ad_status,
                "runtime_days": ad.ad_age_days,
                "text": (ad.raw_text or "")[:MAX_AD_CHARS],
            }
            for ad in samples
        ],
    }
    return payload, _evidence_hash(cluster, ads)


def _candidate_clusters(session, explicit_ids=None):
    if explicit_ids:
        clusters = session.execute(
            select(Cluster).where(Cluster.id.in_([int(x) for x in explicit_ids]))
        ).scalars().all()
        by_id = {c.id: c for c in clusters}
        return [by_id[i] for i in [int(x) for x in explicit_ids] if i in by_id]

    limit = finalist_limit()
    pool = session.execute(
        select(Cluster)
        .where(Cluster.age_status != "NEW")
        .order_by(Cluster.opportunity_score.desc(), Cluster.market_proof.desc(), Cluster.confidence.desc())
        .limit(max(30, limit * 3))
    ).scalars().all()
    if not pool:
        return []
    strong = [c for c in pool if float(c.opportunity_score or 0) >= min_opportunity()]
    if len(strong) < min(5, limit):
        strong = pool[:limit]
    return strong[:limit]


def _build_user_content(payloads):
    return (
        "Final-review every product cluster below independently. Scores are 0-10; for risk fields 10 means highest risk. "
        "Research country is intentionally omitted from scoring and must never affect judgment.\n\n"
        + json.dumps(payloads, ensure_ascii=False)
    )


def _call_claude(payloads):
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_retries=3,
        timeout=180.0,
    )
    response = client.messages.create(
        model=model_name(),
        max_tokens=7000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_content(payloads)}],
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
        },
    )
    text = "".join(
        getattr(block, "text", "")
        for block in response.content
        if getattr(block, "type", "") == "text"
    )
    parsed = json.loads(text)
    return [_normalize_review(item) for item in parsed.get("reviews", [])]


def review_clusters_with_claude(session, cluster_ids=None, force=False):
    """Review only finalists, cache by evidence hash, and return compact run metadata."""
    if not is_configured():
        raise RuntimeError("ANTHROPIC_API_KEY saknas.")

    clusters = _candidate_clusters(session, explicit_ids=cluster_ids)
    if not clusters:
        return {"attempted": False, "reviewed": 0, "cached": 0, "model": model_name(), "cluster_ids": []}

    stale_payloads = []
    stale_meta = {}
    cached = 0
    for cluster in clusters:
        payload, evidence_hash = _cluster_payload(session, cluster)
        previous = _load_json(cluster.deep_review_json)
        if (
            not force
            and previous.get("review_version") == REVIEW_VERSION
            and previous.get("evidence_hash") == evidence_hash
        ):
            cached += 1
            continue
        stale_payloads.append(payload)
        stale_meta[cluster.id] = evidence_hash

    if not stale_payloads:
        return {
            "attempted": False,
            "reviewed": 0,
            "cached": cached,
            "model": model_name(),
            "cluster_ids": [c.id for c in clusters],
        }

    reviews = _call_claude(stale_payloads)
    returned = {int(r["cluster_id"]): r for r in reviews}
    reviewed_ids = []
    missing_ids = []

    for cluster in clusters:
        if cluster.id not in stale_meta:
            continue
        review = returned.get(cluster.id)
        if not review:
            missing_ids.append(cluster.id)
            continue
        final, ai_weight = hybrid_score(cluster.opportunity_score, review)
        review.update({
            "hybrid_score": final,
            "ai_weight": ai_weight,
            "deterministic_score": round(float(cluster.opportunity_score or 0), 1),
            "market_proof": round(float(cluster.market_proof or 0), 1),
            "evidence_hash": stale_meta[cluster.id],
            "review_version": REVIEW_VERSION,
            "model": model_name(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "automatic": not bool(cluster_ids),
        })
        cluster.deep_review_json = json.dumps(review, ensure_ascii=False)
        reviewed_ids.append(cluster.id)

    session.flush()
    return {
        "attempted": True,
        "reviewed": len(reviewed_ids),
        "cached": cached,
        "model": model_name(),
        "cluster_ids": reviewed_ids,
        "missing_cluster_ids": missing_ids,
    }
