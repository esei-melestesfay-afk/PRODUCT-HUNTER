import hashlib
import json
import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from sqlalchemy import delete, or_, select

# Applies the multilingual V5 lexicon before analyzer is used.
import sitecustomize  # noqa: F401
from analyzer import split_ads
from claude_ranker import (
    finalist_limit, is_configured as claude_ready, model_name as claude_model,
    review_clusters_with_claude,
)
from database import (
    Ad, Cluster, ClusterMembership, Job, JobChunk, SearchSession, TestResult,
    Top5Snapshot, backend_name, init_db, persistent_backend, session_scope,
)
from hybrid_view import serialize_cluster, snapshot_top5, top5, watchlist
from keywords import COUNTRY_STRATEGIES, DEFAULT_ORDER, next_keyword
from v5_engine import choose_or_create_cluster, prepare_ad, recompute_cluster

app = Flask(__name__)


def engine_name():
    return "V5 Claude Hybrid" if claude_ready() else "V5 Deterministic Fallback"


def _metrics_for_storage(item):
    keys = [
        "problem_strength", "severity_score", "frequency_score", "emotion_score",
        "fit35_score", "evergreen_score", "clarity_score", "value_score",
        "demo_score", "broad_market_score", "direct_response_score",
        "trend_penalty", "compliance_penalty", "commodity_penalty",
        "confidence_score", "base_score", "willingness_to_pay", "domain",
        "strength_reasons", "warnings", "identity_tokens",
    ]
    return {k: item.get(k) for k in keys}


def _ad_from_item(item, raw, country, keyword, search_session_id):
    return Ad(
        library_id=item.get("meta_library_id") or None,
        fingerprint=item["fingerprint"],
        company=item.get("company") or "Okänt företag",
        company_normalized=item.get("company_normalized") or "",
        product_name=item.get("product_name") or "Fysisk produkt",
        category=item.get("category") or "Övrig vardagsprodukt",
        problem_type=item.get("problem_type") or "Allmänt vardagsproblem",
        problem_summary=item.get("problem_summary") or "",
        country=country or "SE",
        keyword=keyword or "",
        search_session_id=search_session_id,
        raw_text=raw[:30000],
        ad_status=item.get("ad_status") or "unknown",
        ad_start_date=item.get("ad_start_date") or "",
        ad_end_date=item.get("ad_end_date") or "",
        ad_age_days=item.get("ad_age_days"),
        simhash=item.get("simhash") or "",
        data_quality=float(item.get("data_quality") or 0),
        metrics_json=json.dumps(_metrics_for_storage(item), ensure_ascii=False),
    )


def _job_payload(job):
    return {
        "job_id": job.id,
        "status": job.status,
        "total_chunks": job.total_chunks,
        "processed_chunks": job.processed_chunks,
        "total_ads": job.total_ads,
        "new_ads": job.new_ads,
        "duplicate_ads": job.duplicate_ads,
    }


def _process_chunk(session, job, chunk, country, keyword):
    chunk.status = "processing"
    chunk.retry_count = int(chunk.retry_count or 0) + 1
    session.flush()

    blocks = split_ads(chunk.raw_text)
    impacted_clusters = set()
    new_ads = 0
    duplicates = 0

    search_session = session.get(SearchSession, job.search_session_id) if job.search_session_id else None
    if search_session:
        search_session.ads_pasted_count = int(search_session.ads_pasted_count or 0) + len(blocks)

    for raw in blocks:
        item = prepare_ad(raw, country, keyword)
        conditions = [Ad.fingerprint == item["fingerprint"]]
        if item.get("meta_library_id"):
            conditions.append(Ad.library_id == item["meta_library_id"])
        existing = session.execute(select(Ad).where(or_(*conditions)).limit(1)).scalar_one_or_none()
        if existing:
            duplicates += 1
            continue

        ad = _ad_from_item(item, raw, country, keyword, job.search_session_id)
        session.add(ad)
        session.flush()
        cluster_id = choose_or_create_cluster(session, item, ad.id)
        impacted_clusters.add(cluster_id)
        new_ads += 1

    recent_clusters = []
    for cluster_id in impacted_clusters:
        cluster = recompute_cluster(session, cluster_id)
        if cluster:
            recent_clusters.append(serialize_cluster(session, cluster))

    chunk.status = "done"
    chunk.error = ""
    chunk.processed_at = datetime.utcnow()
    job.status = "processing"
    job.processed_chunks = int(job.processed_chunks or 0) + 1
    job.total_ads = int(job.total_ads or 0) + len(blocks)
    job.new_ads = int(job.new_ads or 0) + new_ads
    job.duplicate_ads = int(job.duplicate_ads or 0) + duplicates

    if job.total_chunks and job.processed_chunks >= job.total_chunks:
        job.status = "done"
        job.completed_at = datetime.utcnow()

    session.flush()
    recent_clusters.sort(
        key=lambda x: (x.get("final_score", 0), x.get("market_proof", 0)),
        reverse=True,
    )
    return {
        "chunk_ads": len(blocks),
        "chunk_new": new_ads,
        "chunk_duplicates": duplicates,
        "recent_clusters": recent_clusters[:20],
    }


def _finalize_with_claude(session, job):
    if job.status != "done":
        return {"attempted": False, "reviewed": 0, "cached": 0, "reason": "job_not_done"}

    claude_meta = {
        "attempted": False,
        "reviewed": 0,
        "cached": 0,
        "model": claude_model(),
        "finalist_limit": finalist_limit(),
    }
    if claude_ready():
        try:
            claude_meta.update(review_clusters_with_claude(session))
        except Exception as exc:
            app.logger.exception("Automatic Claude finalist review failed")
            claude_meta["error"] = str(exc)[:260]
    else:
        claude_meta["error"] = "ANTHROPIC_API_KEY saknas"

    snapshot_top5(session)
    return claude_meta


@app.route("/")
def index():
    with session_scope() as session:
        initial_top = top5(session, 5)
    return render_template(
        "index.html",
        countries=COUNTRY_STRATEGIES,
        country_order=DEFAULT_ORDER,
        top5=initial_top,
        claude_ready=claude_ready(),
        claude_model=claude_model(),
        database_backend=backend_name(),
        database_persistent=persistent_backend(),
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "engine": engine_name(),
        "claude_auto": claude_ready(),
        "claude_optional": claude_ready(),
        "claude_model": claude_model(),
        "claude_finalist_limit": finalist_limit(),
        "zero_credit_default": not claude_ready(),
        "zero_credit_fallback": True,
        "database_backend": backend_name(),
        "database_persistent": persistent_backend(),
    })


@app.route("/api/keyword")
def api_keyword():
    country = request.args.get("country", "SE")
    try:
        idx = int(request.args.get("index", 0))
    except ValueError:
        idx = 0
    strategy = COUNTRY_STRATEGIES.get(country, COUNTRY_STRATEGIES["SE"])
    return jsonify({
        "country": country,
        "country_name": strategy["name"],
        "keyword": next_keyword(country, idx),
        "index": idx,
    })


@app.route("/api/jobs", methods=["POST"])
def create_job():
    payload = request.get_json(silent=True) or {}
    country = payload.get("country", "SE")
    keyword = (payload.get("keyword") or "").strip()
    try:
        total_chunks = max(1, int(payload.get("total_chunks") or 1))
    except Exception:
        total_chunks = 1

    search_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(SearchSession(id=search_id, country=country, keyword=keyword))
        job = Job(id=job_id, search_session_id=search_id, status="pending", total_chunks=total_chunks)
        session.add(job)
        session.flush()
        response = _job_payload(job)
    return jsonify(response), 201


@app.route("/api/jobs/<job_id>/chunks", methods=["POST"])
def process_job_chunk(job_id):
    payload = request.get_json(silent=True) or {}
    raw = (payload.get("raw") or "").strip()
    if not raw:
        return jsonify({"error": "Tom annonsdel."}), 400
    try:
        chunk_index = int(payload.get("chunk_index", 0))
    except Exception:
        return jsonify({"error": "Ogiltigt chunk-index."}), 400

    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                return jsonify({"error": "Jobbet finns inte."}), 404
            search = session.get(SearchSession, job.search_session_id) if job.search_session_id else None
            country = search.country if search else "SE"
            keyword = search.keyword if search else ""

            existing = session.execute(
                select(JobChunk).where(
                    JobChunk.job_id == job_id,
                    or_(JobChunk.chunk_index == chunk_index, JobChunk.content_hash == content_hash),
                ).limit(1)
            ).scalar_one_or_none()

            if existing and existing.status == "done":
                response = _job_payload(job)
                response.update({
                    "chunk_ads": 0,
                    "chunk_new": 0,
                    "chunk_duplicates": 0,
                    "recent_clusters": [],
                    "top5": top5(session, 5),
                    "watchlist": watchlist(session, 5),
                    "already_done": True,
                })
                return jsonify(response)

            chunk = existing or JobChunk(
                job_id=job_id,
                chunk_index=chunk_index,
                status="pending",
                retry_count=0,
                content_hash=content_hash,
                raw_text=raw,
            )
            if not existing:
                session.add(chunk)
                session.flush()
            else:
                chunk.raw_text = raw
                chunk.content_hash = content_hash

            try:
                result = _process_chunk(session, job, chunk, country, keyword)
            except Exception as exc:
                chunk.status = "failed"
                chunk.error = str(exc)[:1000]
                job.status = "partial"
                session.flush()
                raise

            claude_meta = _finalize_with_claude(session, job) if job.status == "done" else None
            response = _job_payload(job)
            response.update(result)
            response["top5"] = top5(session, 5)
            response["watchlist"] = watchlist(session, 5)
            if claude_meta is not None:
                response["claude"] = claude_meta
            return jsonify(response)
    except Exception as exc:
        app.logger.exception("V5 chunk processing failed")
        return jsonify({"error": f"Analysen stoppades: {str(exc)[:240]}"}), 500


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Jobbet finns inte."}), 404
        result = _job_payload(job)
        result["top5"] = top5(session, 5)
        result["watchlist"] = watchlist(session, 5)
        return jsonify(result)


@app.route("/api/analyze", methods=["POST"])
def legacy_hybrid_analyze():
    payload = request.get_json(silent=True) or {}
    raw = (payload.get("raw") or "").strip()
    if not raw:
        return jsonify({"error": "Klistra in minst en annons."}), 400
    country = payload.get("country", "SE")
    keyword = (payload.get("keyword") or "").strip()

    search_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(SearchSession(id=search_id, country=country, keyword=keyword))
        job = Job(id=job_id, search_session_id=search_id, status="pending", total_chunks=1)
        session.add(job)
        chunk = JobChunk(
            job_id=job_id,
            chunk_index=0,
            status="pending",
            retry_count=0,
            content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            raw_text=raw,
        )
        session.add(chunk)
        session.flush()
        result = _process_chunk(session, job, chunk, country, keyword)
        claude_meta = _finalize_with_claude(session, job)
        return jsonify({
            "count": result["chunk_new"],
            "duplicates_skipped": result["chunk_duplicates"],
            "analyzed": result["recent_clusters"],
            "top5": top5(session, 5),
            "watchlist": watchlist(session, 5),
            "library_count": session.query(Ad).count(),
            "engine": engine_name(),
            "claude": claude_meta,
        })


@app.route("/api/top")
def api_top():
    with session_scope() as session:
        return jsonify({
            "top5": top5(session, 5),
            "watchlist": watchlist(session, 5),
            "library_count": session.query(Ad).count(),
            "cluster_count": session.query(Cluster).count(),
            "engine": engine_name(),
            "claude_auto": claude_ready(),
        })


@app.route("/api/clusters/<int:cluster_id>/deep-review", methods=["POST"])
def deep_review(cluster_id):
    if not claude_ready():
        return jsonify({"error": "Claude är inte ansluten. Lägg in ANTHROPIC_API_KEY."}), 503

    try:
        with session_scope() as session:
            cluster = session.get(Cluster, cluster_id)
            if not cluster:
                return jsonify({"error": "Produkten finns inte."}), 404
            meta = review_clusters_with_claude(session, [cluster_id], force=True)
            cluster = session.get(Cluster, cluster_id)
            item = serialize_cluster(session, cluster)
            return jsonify({
                "ok": True,
                "review": item.get("deep_review") or {},
                "cluster": item,
                "claude": meta,
                "top5": top5(session, 5),
            })
    except Exception as exc:
        app.logger.exception("Claude deep review failed")
        return jsonify({"error": f"Claude-granskningen misslyckades: {str(exc)[:220]}"}), 502


@app.route("/api/reset", methods=["POST"])
def api_reset():
    with session_scope() as session:
        session.execute(delete(Top5Snapshot))
        session.execute(delete(TestResult))
        session.execute(delete(ClusterMembership))
        session.execute(delete(JobChunk))
        session.execute(delete(Job))
        session.execute(delete(Cluster))
        session.execute(delete(Ad))
        session.execute(delete(SearchSession))
    return jsonify({"ok": True, "top5": [], "watchlist": []})


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "engine": engine_name(),
        "database": backend_name(),
        "persistent_database": persistent_backend(),
        "claude_auto": claude_ready(),
        "claude_model": claude_model(),
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
