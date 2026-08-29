import argparse
import json
import os
import time
from datetime import datetime

from sqlalchemy import select

from database import Ad, Cluster, ClusterMembership, session_scope
from local_intelligence import LocalIntelligence, cosine, evidence_text, normalize, problem_text
from v5_engine import recompute_cluster

WORKER_VERSION = "v5.2-local-1"
DEFAULT_BATCH = int(os.environ.get("LOCAL_WORKER_BATCH", "80"))
CLUSTER_MIN_SIM = float(os.environ.get("CLUSTER_MIN_SIMILARITY", "0.82"))
CLUSTER_MIN_MARGIN = float(os.environ.get("CLUSTER_MIN_MARGIN", "0.05"))


def _load_json(value):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _save_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _is_done(ad, model_name, taxonomy_version):
    metrics = _load_json(ad.metrics_json)
    local = metrics.get("local_ml") or {}
    return (
        local.get("worker_version") == WORKER_VERSION
        and local.get("model") == model_name
        and local.get("taxonomy_version") == taxonomy_version
    )


def _cluster_signature(cluster):
    return _load_json(cluster.signature_json)


def _cluster_candidates(session, taxonomy_key):
    clusters = session.execute(select(Cluster).order_by(Cluster.updated_at.desc())).scalars().all()
    out = []
    for cluster in clusters:
        sig = _cluster_signature(cluster)
        if sig.get("taxonomy_key") != taxonomy_key:
            continue
        centroid = sig.get("product_centroid")
        if isinstance(centroid, list) and centroid:
            out.append((cluster, sig, centroid))
    return out


def _best_cluster(session, taxonomy_key, product_vector):
    scored = []
    for cluster, sig, centroid in _cluster_candidates(session, taxonomy_key):
        scored.append((cosine(product_vector, centroid), cluster, sig))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return None, 0.0, 0.0
    best_score, best_cluster, _ = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    return best_cluster, float(best_score), float(second_score)


def _membership(session, ad_id):
    return session.execute(
        select(ClusterMembership).where(ClusterMembership.ad_id == ad_id)
    ).scalar_one_or_none()


def _update_centroid(cluster, product_vector, taxonomy_result, model_name):
    sig = _cluster_signature(cluster)
    old = sig.get("product_centroid")
    count = int(sig.get("centroid_count") or 0)
    if isinstance(old, list) and old and len(old) == len(product_vector) and count > 0:
        merged = [
            (float(old[i]) * count + float(product_vector[i])) / (count + 1)
            for i in range(len(product_vector))
        ]
        centroid = normalize(merged)
        count += 1
    else:
        centroid = list(map(float, product_vector))
        count = 1

    sig.update({
        "taxonomy_key": taxonomy_result["key"],
        "taxonomy_label_sv": taxonomy_result["label_sv"],
        "taxonomy_score": taxonomy_result["score"],
        "product_centroid": centroid,
        "centroid_count": count,
        "embedding_model": model_name,
        "local_worker_version": WORKER_VERSION,
    })
    cluster.signature_json = _save_json(sig)
    cluster.updated_at = datetime.utcnow()


def _move_membership(session, membership, target_cluster, similarity):
    old_cluster_id = membership.cluster_id if membership else None
    if membership:
        membership.cluster_id = target_cluster.id
        membership.similarity = round(float(similarity), 4)
    else:
        session.add(ClusterMembership(
            cluster_id=target_cluster.id,
            ad_id=membership.ad_id if membership else None,
            similarity=round(float(similarity), 4),
        ))
    return old_cluster_id


def process_once(limit=DEFAULT_BATCH):
    intelligence = LocalIntelligence()
    taxonomy_version = intelligence.taxonomy.get("version", 1)
    processed = 0
    moved = 0
    unknown = 0

    with session_scope() as session:
        ads = session.execute(select(Ad).order_by(Ad.id.asc())).scalars().all()
        pending = [a for a in ads if not _is_done(a, intelligence.model_name, taxonomy_version)][:limit]

        for ad in pending:
            product_vector = intelligence.encode_product(evidence_text(ad))
            problem_vector = intelligence.encode_problem(problem_text(ad))
            taxonomy_result = intelligence.classify_product(evidence_text(ad), product_vector)
            if taxonomy_result["key"] == "unknown":
                unknown += 1

            membership = _membership(session, ad.id)
            current_cluster = session.get(Cluster, membership.cluster_id) if membership else None
            best_cluster, best_score, second_score = _best_cluster(
                session, taxonomy_result["key"], product_vector
            )

            target = current_cluster
            confident_match = (
                best_cluster is not None
                and best_score >= CLUSTER_MIN_SIM
                and (best_score - second_score) >= CLUSTER_MIN_MARGIN
            )
            if confident_match:
                target = best_cluster

            if target is None:
                # Server ingest normally creates a cluster first. Skip safely if a legacy row lacks one.
                metrics = _load_json(ad.metrics_json)
                metrics["local_ml"] = {
                    "worker_version": WORKER_VERSION,
                    "model": intelligence.model_name,
                    "taxonomy_version": taxonomy_version,
                    "taxonomy": taxonomy_result,
                    "problem_embedding_norm": round(sum(x*x for x in problem_vector) ** 0.5, 4),
                    "status": "NO_CLUSTER",
                }
                ad.metrics_json = _save_json(metrics)
                processed += 1
                continue

            old_cluster_id = membership.cluster_id if membership else None
            if membership and target.id != membership.cluster_id:
                membership.cluster_id = target.id
                membership.similarity = round(best_score, 4)
                moved += 1

            _update_centroid(target, product_vector, taxonomy_result, intelligence.model_name)

            metrics = _load_json(ad.metrics_json)
            metrics["local_ml"] = {
                "worker_version": WORKER_VERSION,
                "model": intelligence.model_name,
                "taxonomy_version": taxonomy_version,
                "taxonomy": taxonomy_result,
                "cluster_similarity": round(best_score, 4) if best_cluster else None,
                "cluster_margin": round(best_score - second_score, 4) if best_cluster else None,
                "problem_embedding_norm": round(sum(x*x for x in problem_vector) ** 0.5, 4),
                "status": "DONE",
            }
            ad.metrics_json = _save_json(metrics)

            recompute_cluster(session, target.id)
            if old_cluster_id and old_cluster_id != target.id:
                recompute_cluster(session, old_cluster_id)
            processed += 1

    return {"processed": processed, "moved": moved, "unknown": unknown}


def main():
    parser = argparse.ArgumentParser(description="PRODUCT HUNTER V5 local intelligence worker")
    parser.add_argument("--watch", action="store_true", help="Fortsätt kontrollera nya annonser")
    parser.add_argument("--interval", type=int, default=20, help="Sekunder mellan kontroller")
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH, help="Max annonser per omgång")
    args = parser.parse_args()

    while True:
        result = process_once(args.limit)
        print(
            f"V5 local worker: {result['processed']} behandlade, "
            f"{result['moved']} omgrupperade, {result['unknown']} okända"
        )
        if not args.watch:
            break
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    main()
