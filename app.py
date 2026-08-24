from flask import Flask, render_template, request, jsonify
import sqlite3, json, os, re
from pathlib import Path
from datetime import datetime

from analyzer import analyze_ad_base, split_ads, enrich_market_context, similarity
from claude_analyzer import (
    analyze_ads_with_claude,
    is_configured as claude_configured,
    model_name as claude_model_name,
)
from keywords import COUNTRY_STRATEGIES, DEFAULT_ORDER, next_keyword

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "product_hunter.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn, table, column, definition):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            problem_score REAL,
            emotion_score REAL,
            evergreen_score REAL,
            fit35_score REAL,
            clarity_score REAL,
            value_score REAL,
            longevity_score REAL,
            ad_age_days INTEGER,
            risk_penalty REAL,
            trend_penalty REAL,
            problem_summary TEXT,
            verdict TEXT,
            raw_text TEXT,
            country TEXT,
            keyword TEXT,
            created_at TEXT NOT NULL
        )
    """)
    ensure_column(conn, "candidates", "product_name", "TEXT")
    ensure_column(conn, "candidates", "category", "TEXT")
    ensure_column(conn, "candidates", "problem_type", "TEXT")
    ensure_column(conn, "candidates", "confidence", "REAL")
    ensure_column(conn, "candidates", "fingerprint", "TEXT")
    ensure_column(conn, "candidates", "analysis_json", "TEXT")
    ensure_column(conn, "candidates", "ai_used", "INTEGER DEFAULT 0")
    ensure_column(conn, "candidates", "ai_model", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_fingerprint ON candidates(fingerprint)")
    conn.commit()
    conn.close()


def _clean_line(value):
    return re.sub(r"\s+", " ", value or "").strip()


def extract_meta_advertiser(raw_text, fallback="Okänt företag"):
    """Deterministically extract the Meta advertiser/page name.

    Claude is intentionally NOT allowed to invent this value. We prefer explicit
    Company/Page labels, then the line directly before Meta's Sponsored marker,
    then duplicated page-name lines common in Ad Library copy/paste.
    """
    raw_text = raw_text or ""

    for label in ("Company", "Företag", "Annonsör", "Page name", "Sidnamn", "Page"):
        match = re.search(rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*(.+?)\s*$", raw_text)
        if match:
            value = _clean_line(match.group(1))[:120]
            if value:
                return value

    lines = [_clean_line(x) for x in raw_text.splitlines() if _clean_line(x)]
    first = lines[:18]

    sponsored = re.compile(
        r"^(?:sponsrad|sponsras|sponsored|gesponsert|gesponsord|werbung|annonce|mainos)$",
        re.I,
    )
    bad = re.compile(
        r"(?:https?://|www\.|biblioteks?-id|library\s*id|plattform|platform|"
        r"^aktiv$|^inaktiv$|^active$|^inactive$|^details?$|^see ad details$)",
        re.I,
    )

    def valid(candidate):
        candidate = _clean_line(candidate)
        if not candidate or len(candidate) > 90 or bad.search(candidate):
            return False
        if re.search(r"\b\d{1,2}\s+[A-Za-zÅÄÖåäö]{3,10}\s+20\d{2}\b", candidate):
            return False
        if len(candidate.split()) > 8:
            return False
        return True

    # Meta Ad Library commonly pastes: PageName / PageName / Sponsored.
    for i, line in enumerate(first):
        if sponsored.match(line) and i > 0:
            candidate = first[i - 1]
            if valid(candidate):
                return candidate

    # Repeated short lines are a very strong page-name signal.
    for i in range(len(first) - 1):
        if first[i].casefold() == first[i + 1].casefold() and valid(first[i]):
            return first[i]

    # Last fallback: first plausible short line from the Meta paste.
    for line in first[:6]:
        if valid(line) and not sponsored.match(line):
            return line

    fallback = _clean_line(fallback)
    return fallback or "Okänt företag"


def row_to_item(row):
    try:
        item = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
    except Exception:
        item = {}

    # Always re-read the advertiser from the original Meta text. This also fixes
    # older saved rows without requiring the user to reset the ranking.
    detected_company = extract_meta_advertiser(row["raw_text"] or "", row["company"])
    item["company"] = detected_company
    item.setdefault("product_name", row["product_name"] or "Fysisk produkt")
    item.setdefault("category", row["category"] or "Övrig vardagsprodukt")
    item.setdefault("problem_type", row["problem_type"] or "Allmänt vardagsproblem")
    item.setdefault("problem_summary", row["problem_summary"] or "Behöver mer analys.")
    item.setdefault("base_score", row["score"] or 0)
    item.setdefault("problem_strength", row["problem_score"] or 0)
    item.setdefault("emotion_score", row["emotion_score"] or 0)
    item.setdefault("evergreen_score", row["evergreen_score"] or 0)
    item.setdefault("fit35_score", row["fit35_score"] or 0)
    item.setdefault("clarity_score", row["clarity_score"] or 0)
    item.setdefault("value_score", row["value_score"] or 0)
    item.setdefault("longevity_score", row["longevity_score"] or 0)
    item.setdefault("ad_age_days", row["ad_age_days"])
    item.setdefault("confidence_score", row["confidence"] or 4.0)
    item.setdefault("signature", [])
    item["id"] = row["id"]
    item["country"] = row["country"] or "SE"
    item["keyword"] = row["keyword"] or ""
    item["created_at"] = row["created_at"]
    item["ai_used"] = bool(row["ai_used"]) or bool(item.get("ai_analysis"))
    item["ai_model"] = row["ai_model"] or item.get("ai_model", "")
    return item


def load_all(limit=5000):
    conn = db()
    rows = conn.execute("SELECT * FROM candidates ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [row_to_item(r) for r in rows]


def _apply_hybrid_score(item):
    ai = item.get("ai_analysis") or {}
    if not ai:
        item["hybrid_final_score"] = 0.0
        item["final_score"] = 0.0
        item["decision"] = "LEGACY / EJ AI"
        return item

    semantic10 = float(ai.get("semantic_score", 0)) / 10.0
    market10 = float(item.get("market_validation_score", 0))
    longevity10 = float(item.get("longevity_score", 0))
    local_conf10 = float(item.get("confidence_score", 0))
    ai_conf10 = float(ai.get("confidence", 0))

    final10 = (
        semantic10 * 0.72 +
        market10 * 0.12 +
        longevity10 * 0.08 +
        ai_conf10 * 0.05 +
        local_conf10 * 0.03
    )

    if ai_conf10 < 4.5:
        final10 = min(final10, 6.4)
    if not ai.get("physical_product", True):
        final10 = min(final10, 3.5)

    final10 = max(0.0, min(10.0, final10))
    item["hybrid_final_score"] = round(final10 * 10, 1)
    item["final_score"] = item["hybrid_final_score"]

    item["product_name"] = ai.get("product_name") or item.get("product_name")
    item["category"] = ai.get("category") or item.get("category")
    item["problem_summary"] = ai.get("core_problem") or item.get("problem_summary")
    item["problem_strength"] = ai.get("problem_severity", item.get("problem_strength", 0))
    item["severity_score"] = ai.get("problem_severity", item.get("severity_score", 0))
    item["frequency_score"] = ai.get("problem_frequency", item.get("frequency_score", 0))
    item["emotion_score"] = ai.get("emotional_pressure", item.get("emotion_score", 0))
    item["fit35_score"] = ai.get("fit_35_plus", item.get("fit35_score", 0))
    item["evergreen_score"] = ai.get("evergreen_strength", item.get("evergreen_score", 0))
    item["clarity_score"] = ai.get("three_second_clarity", item.get("clarity_score", 0))
    item["value_score"] = ai.get("value_proposition", item.get("value_score", 0))
    item["demo_score"] = ai.get("demo_strength", item.get("demo_score", 0))
    item["broad_market_score"] = ai.get("market_breadth", item.get("broad_market_score", 0))
    item["willingness_to_pay"] = ai.get("willingness_to_pay", 0)
    item["target_customer"] = ai.get("target_customer", "")
    item["purchase_reason"] = ai.get("purchase_reason", "")
    item["why_could_win"] = ai.get("why_it_could_win", "")
    item["why_could_fail"] = ai.get("why_it_could_fail", "")
    item["red_flags"] = ai.get("red_flags", [])
    item["ai_confidence"] = ai.get("confidence", 0)
    item["ai_semantic_score"] = ai.get("semantic_score", 0)

    if (
        item["final_score"] >= 82 and
        item["problem_strength"] >= 7.0 and
        item["evergreen_score"] >= 7.0 and
        item["fit35_score"] >= 6.0 and
        item["ai_confidence"] >= 6.0
    ):
        item["decision"] = "TESTA FÖRST"
    elif (
        item["final_score"] >= 72 and
        item["problem_strength"] >= 6.0 and
        item["evergreen_score"] >= 6.0
    ):
        item["decision"] = "STARK KANDIDAT"
    elif item["final_score"] >= 62:
        item["decision"] = "BEHÅLL / MER RESEARCH"
    else:
        item["decision"] = "SVAG / SKIPPA"

    bits = []
    if item["problem_strength"] >= 7.5:
        bits.append("starkt problem")
    if item["frequency_score"] >= 7:
        bits.append("händer ofta")
    if item["fit35_score"] >= 7:
        bits.append("stark 35+ fit")
    if item["evergreen_score"] >= 8:
        bits.append("evergreen")
    if item["willingness_to_pay"] >= 7:
        bits.append("bra betalningsvilja")
    if item.get("market_validation_score", 0) >= 7.5:
        bits.append("marknadsbevis")
    item["why_short"] = ", ".join(bits[:5]) or ai.get("why_it_could_win", "behöver mer bevis")[:180]
    return item


def rank_hybrid(items, limit=5):
    ai_items = [x for x in items if x.get("ai_used") and x.get("ai_analysis")]
    if not ai_items:
        return []

    enrich_market_context(ai_items)
    for item in ai_items:
        _apply_hybrid_score(item)

    ordered = sorted(
        ai_items,
        key=lambda x: (
            x.get("final_score", 0),
            x.get("problem_strength", 0),
            x.get("evergreen_score", 0),
            x.get("ai_confidence", 0),
            x.get("longevity_score", 0),
        ),
        reverse=True,
    )

    picked = []
    for candidate in ordered:
        if any(similarity(candidate, p) >= 0.72 for p in picked):
            continue
        picked.append(candidate)
        if len(picked) >= limit:
            break
    return picked


def get_top5():
    return rank_hybrid(load_all(), 5)


@app.route("/")
def index():
    return render_template(
        "index.html",
        countries=COUNTRY_STRATEGIES,
        country_order=DEFAULT_ORDER,
        top5=get_top5(),
        claude_ready=claude_configured(),
        claude_model=claude_model_name(),
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "claude_ready": claude_configured(),
        "model": claude_model_name(),
        "ranking_mode": "Claude + objective signals",
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


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if not claude_configured():
        return jsonify({
            "error": "Claude API är inte ansluten. Lägg ANTHROPIC_API_KEY i Render Environment Variables."
        }), 503

    payload = request.get_json(silent=True) or {}
    raw = payload.get("raw", "")
    country = payload.get("country", "SE")
    keyword = (payload.get("keyword") or "").strip()

    if len(raw) > 300000:
        return jsonify({"error": "För mycket text i en körning. Dela upp den i två omgångar."}), 400

    blocks = split_ads(raw)[:100]
    if not blocks:
        return jsonify({"error": "Klistra in minst en annons."}), 400

    local_items = [analyze_ad_base(b) for b in blocks]
    for block, item in zip(blocks, local_items):
        item["company"] = extract_meta_advertiser(block, item.get("company"))

    conn = db()
    fresh = []
    duplicate_count = 0
    for block, item in zip(blocks, local_items):
        exists = conn.execute(
            "SELECT id FROM candidates WHERE fingerprint=? LIMIT 1",
            (item["fingerprint"],)
        ).fetchone()
        if exists:
            duplicate_count += 1
        else:
            fresh.append((block, item))
    conn.close()

    if not fresh:
        all_items = load_all()
        return jsonify({
            "count": 0,
            "duplicates_skipped": duplicate_count,
            "analyzed": [],
            "top5": rank_hybrid(all_items, 5),
            "library_count": len(all_items),
            "claude_model": claude_model_name(),
        })

    fresh_blocks = [x[0] for x in fresh]
    ai_results, ai_batch_errors = analyze_ads_with_claude(fresh_blocks)

    merged = []
    for (_, local), ai in zip(fresh, ai_results):
        item = dict(local)
        item["ai_used"] = True
        item["ai_model"] = claude_model_name()
        item["ai_analysis"] = ai
        item["ai_semantic_score"] = ai["semantic_score"]
        item["product_name"] = ai.get("product_name") or item.get("product_name")
        item["category"] = ai.get("category") or item.get("category")
        item["problem_summary"] = ai.get("core_problem") or item.get("problem_summary")
        merged.append(item)

    conn = db()
    inserted_ids = []
    for item in merged:
        cur = conn.execute("""
            INSERT INTO candidates (
                company, score, problem_score, emotion_score, evergreen_score,
                fit35_score, clarity_score, value_score, longevity_score,
                ad_age_days, risk_penalty, trend_penalty, problem_summary,
                verdict, raw_text, country, keyword, created_at,
                product_name, category, problem_type, confidence, fingerprint,
                analysis_json, ai_used, ai_model
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item["company"], item["base_score"], item["problem_strength"], item["emotion_score"],
            item["evergreen_score"], item["fit35_score"], item["clarity_score"], item["value_score"],
            item["longevity_score"], item["ad_age_days"], item["compliance_penalty"],
            item["trend_penalty"], item["problem_summary"], "",
            item["raw_text"], country, keyword, datetime.now().isoformat(timespec="seconds"),
            item["product_name"], item["category"], item["problem_type"],
            item["confidence_score"], item["fingerprint"], json.dumps(item, ensure_ascii=False),
            1, claude_model_name()
        ))
        inserted_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()

    all_items = load_all()
    top5 = rank_hybrid(all_items, 5)
    all_by_id = {x.get("id"): x for x in all_items}
    new_items = [all_by_id[i] for i in inserted_ids if i in all_by_id]

    return jsonify({
        "count": len(new_items),
        "duplicates_skipped": duplicate_count,
        "analyzed": new_items,
        "top5": top5,
        "library_count": len(all_items),
        "claude_model": claude_model_name(),
        "batch_warnings": ai_batch_errors,
    })


@app.route("/api/top")
def api_top():
    items = load_all()
    return jsonify({
        "top5": rank_hybrid(items, 5),
        "library_count": len(items),
        "claude_ready": claude_configured(),
    })


@app.route("/api/reset", methods=["POST"])
def api_reset():
    conn = db()
    conn.execute("DELETE FROM candidates")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "top5": []})


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "claude_configured": claude_configured(),
        "model": claude_model_name(),
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)