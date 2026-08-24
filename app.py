from flask import Flask, render_template, request, jsonify
import sqlite3, json, os
from pathlib import Path
from datetime import datetime
from analyzer import analyze_ad_base, split_ads, enrich_market_context, top_unique
from keywords import COUNTRY_STRATEGIES, DEFAULT_ORDER, next_keyword

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "product_hunter.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

def db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()

def row_to_item(row):
    if row["analysis_json"]:
        try:
            item = json.loads(row["analysis_json"])
        except Exception:
            item = {}
    else:
        item = {}

    # Backward compatibility with V1/V2 DB rows.
    item.setdefault("company", row["company"])
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
    return item

def load_all(limit=3000):
    conn = db()
    rows = conn.execute("SELECT * FROM candidates ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [row_to_item(r) for r in rows]

def get_top5():
    return top_unique(load_all(), 5)

@app.route("/")
def index():
    return render_template(
        "index.html",
        countries=COUNTRY_STRATEGIES,
        country_order=DEFAULT_ORDER,
        top5=get_top5()
    )

@app.route("/api/keyword")
def api_keyword():
    country = request.args.get("country","SE")
    try:
        idx = int(request.args.get("index",0))
    except ValueError:
        idx = 0
    strategy = COUNTRY_STRATEGIES.get(country, COUNTRY_STRATEGIES["SE"])
    return jsonify({
        "country": country,
        "country_name": strategy["name"],
        "keyword": next_keyword(country, idx),
        "index": idx
    })

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    payload = request.get_json(silent=True) or {}
    raw = payload.get("raw","")
    country = payload.get("country","SE")
    keyword = (payload.get("keyword") or "").strip()

    if len(raw) > 300000:
        return jsonify({"error":"För mycket text i en körning. Dela upp den i två omgångar."}), 400

    blocks = split_ads(raw)
    if not blocks:
        return jsonify({"error":"Klistra in minst en annons."}), 400

    analyzed = [analyze_ad_base(b) for b in blocks[:100]]

    conn = db()
    inserted_ids = []
    duplicate_count = 0

    for item in analyzed:
        existing = conn.execute(
            "SELECT id FROM candidates WHERE fingerprint=? LIMIT 1",
            (item["fingerprint"],)
        ).fetchone()

        if existing:
            duplicate_count += 1
            continue

        cur = conn.execute("""
            INSERT INTO candidates (
                company, score, problem_score, emotion_score, evergreen_score,
                fit35_score, clarity_score, value_score, longevity_score,
                ad_age_days, risk_penalty, trend_penalty, problem_summary,
                verdict, raw_text, country, keyword, created_at,
                product_name, category, problem_type, confidence, fingerprint, analysis_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item["company"], item["base_score"], item["problem_strength"], item["emotion_score"],
            item["evergreen_score"], item["fit35_score"], item["clarity_score"], item["value_score"],
            item["longevity_score"], item["ad_age_days"], item["compliance_penalty"],
            item["trend_penalty"], item["problem_summary"], "",
            item["raw_text"], country, keyword, datetime.now().isoformat(timespec="seconds"),
            item["product_name"], item["category"], item["problem_type"],
            item["confidence_score"], item["fingerprint"], json.dumps(item, ensure_ascii=False)
        ))
        inserted_ids.append(cur.lastrowid)

    conn.commit()
    conn.close()

    all_items = load_all()
    enrich_market_context(all_items)
    by_id = {x.get("id"): x for x in all_items}
    new_items = [by_id[i] for i in inserted_ids if i in by_id]

    return jsonify({
        "count": len(new_items),
        "duplicates_skipped": duplicate_count,
        "analyzed": new_items,
        "top5": top_unique(all_items, 5),
        "library_count": len(all_items)
    })

@app.route("/api/top")
def api_top():
    items = load_all()
    return jsonify({"top5": top_unique(items,5), "library_count":len(items)})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    conn = db()
    conn.execute("DELETE FROM candidates")
    conn.commit()
    conn.close()
    return jsonify({"ok":True,"top5":[]})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# Important for production servers such as Gunicorn/Render:
# initialize the SQLite schema when the module is imported.
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
