from datetime import datetime

from sqlalchemy import select

from database import Cluster, Top5Snapshot
from v5_engine import serialize_cluster as serialize_base
from v5_engine import watchlist as base_watchlist


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hybrid_decision(item):
    review = item.get("deep_review") or {}
    final = _num(item.get("final_score"))
    problem = _num(item.get("problem_solving_score"))
    deterministic_evergreen = _num((item.get("breakdown") or {}).get("opportunity", {}).get("evergreen"))

    if review:
        if review.get("physical_product") is False:
            return "SVAG / SKIPPA"
        if _num(review.get("compliance_risk")) >= 8.0:
            return "BEHÅLL / MER RESEARCH" if final >= 55 else "SVAG / SKIPPA"
        evergreen = _num(review.get("evergreen_strength"), deterministic_evergreen)
        ai_conf = min(_num(review.get("confidence")), _num(review.get("product_identity_confidence")))
        if final >= 83 and problem >= 6.5 and evergreen >= 6.5 and ai_conf >= 6.0:
            return "TESTA FÖRST"
        if final >= 73 and evergreen >= 5.5:
            return "STARK KANDIDAT"
        if final >= 61:
            return "BEHÅLL / MER RESEARCH"
        return "SVAG / SKIPPA"

    return item.get("decision") or "MER DATA"


def serialize_cluster(session, cluster):
    item = serialize_base(session, cluster)
    if not item:
        return None
    review = item.get("deep_review") or {}
    hybrid = review.get("hybrid_score")
    final = _num(hybrid, _num(item.get("opportunity_score"))) if hybrid is not None else _num(item.get("opportunity_score"))
    item["deterministic_score"] = round(_num(item.get("opportunity_score")), 1)
    item["final_score"] = round(final, 1)
    item["claude_reviewed"] = bool(review.get("review_version") and review.get("model"))
    item["claude_score"] = round(_num(review.get("claude_score")), 1) if item["claude_reviewed"] else None
    item["claude_confidence"] = round(_num(review.get("confidence")), 1) if item["claude_reviewed"] else None
    item["claude_model"] = review.get("model") if item["claude_reviewed"] else None
    item["ai_weight"] = review.get("ai_weight") if item["claude_reviewed"] else 0
    item["decision"] = _hybrid_decision(item)
    return item


def top5(session, limit=5):
    # Pull a wider deterministic pool because Claude can move finalists up or down.
    clusters = session.execute(
        select(Cluster)
        .where(Cluster.age_status != "NEW")
        .order_by(Cluster.opportunity_score.desc(), Cluster.market_proof.desc(), Cluster.confidence.desc())
        .limit(max(50, limit * 10))
    ).scalars().all()
    items = [serialize_cluster(session, c) for c in clusters]
    items = [x for x in items if x]
    items.sort(
        key=lambda x: (
            _num(x.get("final_score")),
            _num(x.get("market_proof")),
            _num(x.get("confidence")),
            _num(x.get("deterministic_score")),
        ),
        reverse=True,
    )
    return items[:limit]


def watchlist(session, limit=5):
    # NEW products are intentionally not auto-sent to Claude; keep them as evidence watchlist.
    return base_watchlist(session, limit)


def snapshot_top5(session):
    now = datetime.utcnow()
    for rank, item in enumerate(top5(session, 5), 1):
        session.add(
            Top5Snapshot(
                snapshot_at=now,
                rank=rank,
                cluster_id=item["id"],
                opportunity_score=_num(item.get("final_score")),
                evidence_delta_json="{}",
            )
        )
    session.flush()
