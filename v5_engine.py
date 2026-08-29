import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select

from analyzer import analyze_ad_base, similarity, STOPWORDS
from database import Ad, Cluster, ClusterMembership, Top5Snapshot

GENERIC_PRODUCT_NAMES = {
    "fysisk produkt", "sömnprodukt", "komfortprodukt", "städprodukt",
    "förvaringsprodukt", "köksprodukt", "bilprodukt", "trädgårdsprodukt",
    "husdjursprodukt", "badrumsprodukt", "kläd-/skoprodukt", "hemmaprodukt",
}

MARKETING_WORDS = {
    "sponsrad", "sponsras", "sponsored", "gesponsert", "gesponsord", "werbung", "annonce", "mainos",
    "aktiv", "active", "inaktiv", "inactive", "plattformar", "platforms", "biblioteks", "library",
    "köp", "buy", "shop", "order", "beställ", "rabatt", "discount", "sale", "gratis", "free",
    "today", "idag", "nu", "now", "official", "www", "http", "https",
}

CATEGORY_WTP = {
    "Sömn": 7.2, "Rygg & komfort": 7.6, "Städning": 5.8,
    "Förvaring & ordning": 5.7, "Kök": 5.9, "Bil": 6.4,
    "Trädgård": 6.3, "Husdjur": 6.4, "Badrum": 5.8,
    "Kläder & skor": 4.8, "Hem & vardag": 5.8,
    "Övrig vardagsprodukt": 5.0,
}

PAIN_PHRASES = (
    "ont", "smärta", "värk", "stel", "öm", "obehag", "kan inte", "svårt att", "jobbigt",
    "krångel", "läcker", "spill", "stök", "röra", "smuts", "lukt", "tungt", "besvär",
    "pain", "ache", "stiff", "sore", "uncomfortable", "can't", "cannot", "struggle", "difficult",
    "vondt", "vanskelig", "svært ved", "müde von", "schwer zu", "moeilijk om",
    "kipu", "vaikea", "sattuu",
)

RECURRING_PHRASES = (
    "varje dag", "varje natt", "varje morgon", "hela tiden", "varje gång", "ofta", "ständigt",
    "every day", "every night", "every morning", "every time", "constantly", "often",
    "hver dag", "hver natt", "hver morgen", "jeden tag", "jede nacht", "jeden morgen",
    "elke dag", "elke nacht", "elke ochtend", "joka päivä", "joka yö", "joka aamu",
)

CONSEQUENCE_PHRASES = (
    "kan inte sova", "svårt att sova", "vaknar med", "undviker", "orkar inte", "hindrar mig",
    "kan inte böja", "kan inte lyfta", "pinsamt", "skäms", "orolig", "rädd", "stressad",
    "can't sleep", "cannot sleep", "wake up with", "avoid", "stops me", "embarrassing", "ashamed",
    "worried", "afraid", "anxious", "keeps me awake", "can't bend", "can't lift",
    "våkner med", "kan ikke sove", "vågner med", "wache mit", "kann nicht schlafen",
    "word wakker met", "kan niet slapen", "herään", "en voi nukkua",
)

FRUSTRATION_PHRASES = (
    "trött på", "frustrerad", "irriterande", "hatar", "aldrig mer", "less på", "stress",
    "tired of", "fed up", "frustrated", "annoying", "hate", "never again",
    "lei av", "irriterende", "træt af", "irriterende", "müde von", "genervt", "nie wieder",
    "moe van", "irritant", "nooit meer", "kyllästynyt", "ärsyttävä",
)

RELIEF_PHRASES = (
    "slipp", "äntligen", "lättnad", "bekvämare", "tryggare", "utan att behöva", "spara tid",
    "mindre krångel", "frihet", "smidigt", "finally", "relief", "peace of mind", "easier", "comfort",
    "without having to", "save time", "endelig", "slipp", "endlich", "ohne", "eindelijk", "zonder gedoe",
    "vihdoin", "helpompi", "vähemmän vaivaa",
)

DEMO_PHRASES = (
    "före och efter", "se skillnaden", "så fungerar", "på sekunder", "ett tryck", "med ett drag",
    "utan verktyg", "direkt", "automatiskt", "before and after", "see the difference", "how it works",
    "in seconds", "one press", "one move", "without tools", "instantly", "automatic",
    "før og etter", "før og efter", "vorher nachher", "in sekunden", "voor en na", "in seconden",
)

NICE_TO_HAVE_PHRASES = (
    "viral", "trending", "tiktok", "aesthetic", "cute gadget", "must have", "limited drop", "collectible",
    "snygg pryl", "cool pryl", "trend", "hype",
)


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def clamp10(v):
    return max(0.0, min(10.0, float(v)))


def norm_text(value):
    value = (value or "").casefold()
    value = re.sub(r"https?://\S+|www\.\S+", " ", value)
    value = re.sub(r"[^a-z0-9åäöæøüéèàáíóúß\s-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_company(value):
    return re.sub(r"[^a-z0-9åäöæøüéß]+", " ", (value or "").casefold()).strip()[:180]


def _phrase_hits(text, phrases):
    low = (text or "").casefold()
    return sum(1 for phrase in phrases if phrase in low)


def _upgrade_problem_emotion(item, raw):
    pain_hits = _phrase_hits(raw, PAIN_PHRASES)
    recurring_hits = _phrase_hits(raw, RECURRING_PHRASES)
    consequence_hits = _phrase_hits(raw, CONSEQUENCE_PHRASES)
    frustration_hits = _phrase_hits(raw, FRUSTRATION_PHRASES)
    relief_hits = _phrase_hits(raw, RELIEF_PHRASES)
    demo_hits = _phrase_hits(raw, DEMO_PHRASES)
    nice_hits = _phrase_hits(raw, NICE_TO_HAVE_PHRASES)

    base_problem = float(item.get("problem_strength") or 0)
    base_severity = float(item.get("severity_score") or 0)
    base_frequency = float(item.get("frequency_score") or 0)
    base_emotion = float(item.get("emotion_score") or 0)
    base_clarity = float(item.get("clarity_score") or 0)
    base_demo = float(item.get("demo_score") or 0)
    base_direct = float(item.get("direct_response_score") or 0)

    has_problem_anchor = (pain_hits + consequence_hits) > 0 or base_problem >= 4.5
    has_recurring_context = recurring_hits > 0 or base_frequency >= 5.5
    has_emotional_context = (frustration_hits + consequence_hits + relief_hits) > 0

    phrase_problem = 0.0
    if has_problem_anchor:
        phrase_problem = clamp10(
            3.0 + min(3.2, pain_hits * 0.9) + min(2.0, consequence_hits * 1.0)
            + min(1.5, recurring_hits * 0.75) + min(0.8, frustration_hits * 0.4)
        )

    severity_phrase = 0.0
    if has_problem_anchor:
        severity_phrase = clamp10(2.2 + min(3.6, pain_hits * 1.0) + min(3.0, consequence_hits * 1.2))

    frequency_phrase = 0.0
    if has_problem_anchor and has_recurring_context:
        frequency_phrase = clamp10(4.2 + min(4.8, recurring_hits * 1.35))

    emotion_phrase = 0.0
    if has_problem_anchor and has_emotional_context:
        emotion_phrase = clamp10(
            2.0 + min(2.8, consequence_hits * 1.0) + min(2.0, frustration_hits * 0.8)
            + min(1.7, relief_hits * 0.55) + (0.8 if has_recurring_context else 0)
        )

    demo_phrase = clamp10(2.5 + demo_hits * 1.3) if demo_hits else 0.0

    if nice_hits and not has_problem_anchor:
        emotion_phrase = min(emotion_phrase, 2.5)
        phrase_problem = min(phrase_problem, 2.5)

    item["problem_strength"] = round(max(base_problem, 0.60 * base_problem + 0.20 * phrase_problem + 0.12 * base_severity + 0.08 * base_frequency, phrase_problem), 1)
    item["severity_score"] = round(max(base_severity, 0.68 * base_severity + 0.32 * severity_phrase, severity_phrase), 1)
    item["frequency_score"] = round(max(base_frequency, 0.72 * base_frequency + 0.28 * frequency_phrase, frequency_phrase), 1)
    item["emotion_score"] = round(max(base_emotion, 0.62 * base_emotion + 0.38 * emotion_phrase, emotion_phrase), 1)
    item["demo_score"] = round(max(base_demo, 0.68 * base_demo + 0.32 * demo_phrase, demo_phrase), 1)
    if demo_hits:
        item["clarity_score"] = round(max(base_clarity, clamp10(base_clarity * 0.7 + demo_phrase * 0.3)), 1)
        item["direct_response_score"] = round(max(base_direct, clamp10(base_direct * 0.75 + demo_phrase * 0.25)), 1)

    item["emotion_context"] = {
        "pain_hits": pain_hits,
        "recurring_hits": recurring_hits,
        "consequence_hits": consequence_hits,
        "frustration_hits": frustration_hits,
        "relief_hits": relief_hits,
        "demo_hits": demo_hits,
        "nice_to_have_hits": nice_hits,
    }
    return item


def extract_meta_advertiser(raw_text, fallback="Okänt företag"):
    raw_text = raw_text or ""
    for label in ("Company", "Företag", "Annonsör", "Page name", "Sidnamn", "Page"):
        m = re.search(rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*(.+?)\s*$", raw_text)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
            if value:
                return value

    lines = [re.sub(r"\s+", " ", x).strip() for x in raw_text.splitlines() if x.strip()][:20]
    sponsored = re.compile(r"^(?:sponsrad|sponsras|sponsored|gesponsert|gesponsord|werbung|annonce|mainos)$", re.I)
    bad = re.compile(r"(?:https?://|www\.|biblioteks?-id|library\s*id|plattform|platform|^aktiv$|^inaktiv$|^active$|^inactive$)", re.I)

    def valid(x):
        return bool(x and len(x) <= 90 and len(x.split()) <= 8 and not bad.search(x))

    for i, line in enumerate(lines):
        if sponsored.match(line) and i > 0 and valid(lines[i - 1]):
            return lines[i - 1]
    for i in range(len(lines) - 1):
        if lines[i].casefold() == lines[i + 1].casefold() and valid(lines[i]):
            return lines[i]
    for line in lines[:6]:
        if valid(line) and not sponsored.match(line):
            return line
    return (fallback or "Okänt företag").strip() or "Okänt företag"


def simhash64(text):
    tokens = [t for t in norm_text(text).split() if len(t) >= 3 and t not in STOPWORDS and t not in MARKETING_WORDS]
    if not tokens:
        return "0"
    vector = [0] * 64
    for token in tokens:
        h = int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for i in range(64):
            vector[i] += 1 if ((h >> i) & 1) else -1
    out = 0
    for i, score in enumerate(vector):
        if score >= 0:
            out |= (1 << i)
    return str(out)


def hamming_distance(a, b):
    try:
        return (int(a) ^ int(b)).bit_count()
    except Exception:
        return 64


def _domain(raw):
    m = re.search(r"(?i)https?://(?:www\.)?([a-z0-9.-]+)|\bwww\.([a-z0-9.-]+)", raw or "")
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").lower().split("/")[0]


def _identity_tokens(raw, company):
    cleaned = norm_text(raw[:2500])
    company_tokens = set(norm_text(company).split())
    words = []
    for token in cleaned.split():
        if len(token) < 4 or token in STOPWORDS or token in MARKETING_WORDS or token in company_tokens:
            continue
        if token.isdigit() or re.fullmatch(r"20\d{2}", token):
            continue
        words.append(token)
    counts = Counter(words)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in ranked[:8]]


def data_quality(item, raw):
    score = 0
    score += 30 if item.get("meta_library_id") else 0
    score += 20 if item.get("ad_status") in {"active", "inactive"} else 0
    score += 20 if item.get("ad_start_date") else 0
    score += 10 if item.get("company") and item.get("company") != "Okänt företag" else 0
    score += 20 if len((raw or "").strip()) >= 180 else 10 if len((raw or "").strip()) >= 80 else 0
    return clamp(score)


def age_status(days):
    if days is None:
        return "UNKNOWN"
    if days < 14:
        return "NEW"
    if days < 30:
        return "EARLY_SIGNAL"
    if days < 90:
        return "EMERGING"
    if days < 180:
        return "VALIDATED"
    if days < 365:
        return "STRONG"
    return "PROVEN"


def _piecewise_age_score(days):
    if days is None or days <= 0:
        return 0.0
    d = min(int(days), 365)
    anchors = [(0, 0), (14, 10), (30, 25), (90, 55), (180, 80), (365, 100)]
    for (x1, y1), (x2, y2) in zip(anchors, anchors[1:]):
        if x1 <= d <= x2:
            ratio = (d - x1) / max(1, x2 - x1)
            return y1 + ratio * (y2 - y1)
    return 100.0


def _log_score(value, cap):
    value = max(0, min(int(value or 0), cap))
    if value <= 0:
        return 0.0
    return 100.0 * math.log1p(value) / math.log1p(cap)


def _generic_product(name):
    return norm_text(name) in GENERIC_PRODUCT_NAMES


def prepare_ad(raw, country="SE", keyword=""):
    item = analyze_ad_base(raw)
    item = _upgrade_problem_emotion(item, raw)
    item["company"] = extract_meta_advertiser(raw, item.get("company"))
    item["company_normalized"] = normalize_company(item["company"])
    item["country"] = country or "SE"
    item["keyword"] = keyword or ""
    item["simhash"] = simhash64(raw)
    item["data_quality"] = data_quality(item, raw)
    item["domain"] = _domain(raw)
    item["identity_tokens"] = _identity_tokens(raw, item["company"])
    item["age_status"] = age_status(item.get("ad_age_days"))
    item["willingness_to_pay"] = round(
        max(0.0, min(10.0, CATEGORY_WTP.get(item.get("category"), 5.0) * 0.8 + float(item.get("value_score", 5)) * 0.2)), 1
    )
    return item


def _cluster_seed_key(item):
    product = norm_text(item.get("product_name"))
    if product and not _generic_product(product):
        basis = f"{item.get('category')}|{item.get('problem_type')}|{product}"
    else:
        tokens = "|".join(item.get("identity_tokens", [])[:4])
        basis = f"{item.get('category')}|{item.get('problem_type')}|{tokens}|{item.get('company_normalized')}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:32]


def _signature_payload(item):
    return {
        "signature": item.get("signature", []),
        "category": item.get("category"),
        "problem_type": item.get("problem_type"),
        "company": item.get("company"),
        "product_name": item.get("product_name"),
        "identity_tokens": item.get("identity_tokens", []),
    }


def choose_or_create_cluster(session, item, ad_id):
    product = norm_text(item.get("product_name"))
    candidates = session.execute(
        select(Cluster).where(
            Cluster.category == item.get("category"),
            Cluster.problem_type == item.get("problem_type"),
        ).order_by(Cluster.updated_at.desc()).limit(300)
    ).scalars().all()

    best_cluster = None
    best_similarity = 0.0
    for cluster in candidates:
        try:
            rep = json.loads(cluster.signature_json or "{}")
        except Exception:
            rep = {}

        exact_product = product and not _generic_product(product) and norm_text(cluster.name) == product
        if exact_product:
            best_cluster, best_similarity = cluster, 1.0
            break

        sim = similarity(item, rep)
        token_a = set(item.get("identity_tokens", [])[:6])
        token_b = set(rep.get("identity_tokens", [])[:6])
        token_jaccard = len(token_a & token_b) / max(1, len(token_a | token_b)) if token_a and token_b else 0.0
        combined = max(sim, token_jaccard * 0.9)
        if combined > best_similarity:
            best_cluster, best_similarity = cluster, combined

    if best_cluster is None or best_similarity < 0.74:
        key = _cluster_seed_key(item)
        existing = session.execute(select(Cluster).where(Cluster.cluster_key == key)).scalar_one_or_none()
        if existing:
            best_cluster = existing
            best_similarity = 1.0
        else:
            best_cluster = Cluster(
                cluster_key=key,
                name=item.get("product_name") or "Fysisk produkt",
                category=item.get("category") or "Övrig vardagsprodukt",
                problem_type=item.get("problem_type") or "Allmänt vardagsproblem",
                representative_ad_id=ad_id,
                signature_json=json.dumps(_signature_payload(item), ensure_ascii=False),
            )
            session.add(best_cluster)
            session.flush()
            best_similarity = 1.0

    session.add(ClusterMembership(cluster_id=best_cluster.id, ad_id=ad_id, similarity=round(best_similarity, 4)))
    session.flush()
    return best_cluster.id


def _distinct_creatives(ads):
    by_company = defaultdict(list)
    for ad in ads:
        by_company[ad.company_normalized or ad.company].append(ad)
    total = 0
    concurrent = False
    for group in by_company.values():
        kept = []
        for ad in group:
            if not any(hamming_distance(ad.simhash, x) <= 3 for x in kept):
                kept.append(ad.simhash)
        total += len(kept)
        if sum(1 for ad in group if ad.ad_status == "active") >= 2 and len(kept) >= 2:
            concurrent = True
    return total, concurrent


def _cross_market_count(ads):
    company_countries = defaultdict(set)
    country_companies = defaultdict(set)
    for ad in ads:
        company = ad.company_normalized or ad.company
        if company and company != "okänt företag":
            company_countries[company].add(ad.country)
            country_companies[ad.country].add(company)
    count = 0
    for country, companies in country_companies.items():
        if any(len(company_countries[c]) == 1 for c in companies):
            count += 1
    return count


def _cluster_soft_scores(metrics):
    if not metrics:
        return {"problem_solving": 0.0, "emotional_pressure": 0.0, "purchase_urgency": 0.0, "demo_wow": 0.0}

    def avg(key, default=0.0):
        return statistics.mean([float(m.get(key, default) or 0) for m in metrics])

    problem = avg("problem_strength")
    severity = avg("severity_score")
    frequency = avg("frequency_score")
    emotion = avg("emotion_score")
    clarity = avg("clarity_score")
    demo = avg("demo_score")
    direct = avg("direct_response_score")

    return {
        "problem_solving": clamp10(0.42 * problem + 0.28 * severity + 0.18 * frequency + 0.12 * clarity),
        "emotional_pressure": clamp10(0.52 * emotion + 0.25 * severity + 0.15 * frequency + 0.08 * problem),
        "purchase_urgency": clamp10(0.34 * severity + 0.27 * frequency + 0.24 * emotion + 0.15 * direct),
        "demo_wow": clamp10(0.55 * demo + 0.30 * clarity + 0.15 * direct),
    }


def recompute_cluster(session, cluster_id):
    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        return None

    ads = session.execute(
        select(Ad).join(ClusterMembership, ClusterMembership.ad_id == Ad.id)
        .where(ClusterMembership.cluster_id == cluster_id)
    ).scalars().all()
    if not ads:
        return cluster

    companies = {a.company_normalized or a.company for a in ads if a.company and a.company != "Okänt företag"}
    ages = [a.ad_age_days for a in ads if a.ad_age_days is not None]
    active_ages = [a.ad_age_days for a in ads if a.ad_status == "active" and a.ad_age_days is not None]
    median_age = statistics.median(ages) if ages else None
    distinct_creatives, concurrent = _distinct_creatives(ads)
    cross_markets = _cross_market_count(ads)

    advertiser_score = _log_score(len(companies), 15)
    age_score = _piecewise_age_score(median_age)
    creative_score = _log_score(distinct_creatives, 10)
    if concurrent:
        creative_score = min(100.0, creative_score * 1.15)

    per_company_quality = []
    for company in companies:
        grp = [a for a in ads if (a.company_normalized or a.company) == company]
        max_age = max((a.ad_age_days or 0 for a in grp), default=0)
        unique_creatives, _ = _distinct_creatives(grp)
        q = 0.65 * _piecewise_age_score(max_age) + 0.35 * _log_score(unique_creatives, 5)
        per_company_quality.append(q)
    advertiser_quality = statistics.mean(per_company_quality) if per_company_quality else 0.0

    market_proof = clamp(
        0.38 * advertiser_score + 0.30 * age_score
        + 0.20 * creative_score + 0.12 * advertiser_quality
    )

    metrics = [json.loads(a.metrics_json or "{}") for a in ads]
    avg = lambda key, default=0.0: statistics.mean([float(m.get(key, default) or 0) for m in metrics]) if metrics else default
    problem = avg("problem_strength")
    severity = avg("severity_score")
    frequency = avg("frequency_score")
    emotion = avg("emotion_score")
    fit35 = avg("fit35_score")
    evergreen = avg("evergreen_score")
    clarity = avg("clarity_score")
    demo = avg("demo_score")
    direct = avg("direct_response_score")
    broad = avg("broad_market_score")
    wtp = avg("willingness_to_pay", 5.0)

    soft = _cluster_soft_scores(metrics)
    problem_solving = soft["problem_solving"]
    emotional_pressure = soft["emotional_pressure"]
    purchase_urgency = soft["purchase_urgency"]
    demo_wow = soft["demo_wow"]

    opportunity = (
        0.20 * market_proof
        + 0.20 * problem_solving * 10
        + 0.13 * emotional_pressure * 10
        + 0.10 * purchase_urgency * 10
        + 0.08 * fit35 * 10
        + 0.10 * evergreen * 10
        + 0.08 * wtp * 10
        + 0.06 * demo_wow * 10
        + 0.05 * broad * 10
    )

    commodity = avg("commodity_penalty")
    trend = avg("trend_penalty")
    compliance = avg("compliance_penalty")
    penalty_points = commodity * 5.0 + trend * 5.0 + compliance * 7.0
    opportunity = clamp(opportunity - penalty_points)
    if compliance >= 1.5:
        opportunity = min(opportunity, 30.0)

    avg_dq = statistics.mean([a.data_quality or 0 for a in ads])
    session_ids = {a.search_session_id for a in ads if a.search_session_id}
    evidence_depth = min(1.0, math.log1p(len(ads)) / math.log1p(20))
    session_depth = min(1.0, len(session_ids) / 3.0)
    confidence = clamp(0.55 * avg_dq + 25 * evidence_depth + 20 * session_depth)

    stage_days = statistics.median(active_ages) if active_ages else median_age
    stage = age_status(stage_days)

    if opportunity >= 82 and problem_solving >= 7 and evergreen >= 7 and confidence >= 60:
        decision = "TESTA FÖRST"
    elif opportunity >= 72 and problem_solving >= 6 and evergreen >= 6:
        decision = "STARK KANDIDAT"
    elif opportunity >= 62:
        decision = "BEHÅLL / MER RESEARCH"
    else:
        decision = "SVAG / SKIPPA"

    signal_labels = []
    if problem_solving >= 7.2:
        signal_labels.append("STRONG PROBLEM PRODUCT")
    if emotional_pressure >= 7.0:
        signal_labels.append("HIGH EMOTIONAL BUYING MOTIVE")
    if purchase_urgency >= 7.0:
        signal_labels.append("HIGH PURCHASE URGENCY")
    if demo_wow >= 7.0:
        signal_labels.append("STRONG DEMO PRODUCT")
    if problem_solving < 4.0 and emotional_pressure < 4.0:
        signal_labels.append("NICE-TO-HAVE RISK")

    breakdown = {
        "market_proof": {
            "independent_advertisers": len(companies), "advertiser_score": round(advertiser_score, 1),
            "median_runtime_days": median_age, "age_score": round(age_score, 1),
            "cross_market_countries": cross_markets,
            "cross_market_score": None,
            "cross_market_note": "Visas som evidens men påverkar aldrig score eller rank.",
            "distinct_creatives": distinct_creatives, "creative_iteration_score": round(creative_score, 1),
            "advertiser_quality_score": round(advertiser_quality, 1),
        },
        "opportunity": {
            "problem_solving": round(problem_solving, 1),
            "emotional_pressure": round(emotional_pressure, 1),
            "purchase_urgency": round(purchase_urgency, 1),
            "demo_wow": round(demo_wow, 1),
            "signal_labels": signal_labels,
            "problem_severity": round(problem, 1), "raw_emotion": round(emotion, 1),
            "severity": round(severity, 1), "frequency": round(frequency, 1),
            "fit_35plus": round(fit35, 1), "evergreen": round(evergreen, 1),
            "willingness_to_pay": round(wtp, 1), "clarity": round(clarity, 1),
            "demo": round(demo, 1), "direct_response": round(direct, 1),
            "market_breadth": round(broad, 1),
        },
        "penalties": {
            "commodity": round(commodity * 5.0, 1), "trend": round(trend * 5.0, 1),
            "compliance": round(compliance * 7.0, 1), "observed_saturation": None,
        },
        "data": {
            "ads": len(ads), "search_sessions": len(session_ids), "data_quality": round(avg_dq, 1),
            "sampling_note": "Market proof bygger bara på annonser som har samlats in i Product Hunter.",
        },
    }

    named = [a.product_name for a in ads if a.product_name and not _generic_product(a.product_name)]
    if named:
        cluster.name = Counter(named).most_common(1)[0][0]
    cluster.market_proof = round(market_proof, 1)
    cluster.opportunity_score = round(opportunity, 1)
    cluster.confidence = round(confidence, 1)
    cluster.age_status = stage
    cluster.data_quality = round(avg_dq, 1)
    cluster.decision = decision
    cluster.breakdown_json = json.dumps(breakdown, ensure_ascii=False)
    cluster.updated_at = datetime.utcnow()
    session.flush()
    return cluster


def _load_json(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _why_short(cluster, breakdown):
    mp = breakdown.get("market_proof", {}) if isinstance(breakdown, dict) else {}
    opp = breakdown.get("opportunity", {}) if isinstance(breakdown, dict) else {}
    bits = []
    if opp.get("problem_solving", 0) >= 7.2:
        bits.append("starkt verkligt problem")
    if opp.get("emotional_pressure", 0) >= 7.0:
        bits.append("högt emotionellt köp-motiv")
    if opp.get("purchase_urgency", 0) >= 7.0:
        bits.append("hög köp-urgency")
    if opp.get("demo_wow", 0) >= 7.0:
        bits.append("stark demo")
    if mp.get("independent_advertisers", 0) >= 2:
        bits.append(f"{mp['independent_advertisers']} oberoende företag")
    if (mp.get("median_runtime_days") or 0) >= 180:
        bits.append("lång annonslivslängd")
    if opp.get("evergreen", 0) >= 7:
        bits.append("evergreen")
    if opp.get("fit_35plus", 0) >= 7:
        bits.append("35+ fit")
    return ", ".join(bits[:4]) or "behöver mer bevis"


def serialize_cluster(session, cluster):
    if not cluster:
        return None
    ads = session.execute(
        select(Ad).join(ClusterMembership, ClusterMembership.ad_id == Ad.id)
        .where(ClusterMembership.cluster_id == cluster.id)
        .order_by(Ad.created_at.desc())
    ).scalars().all()
    try:
        breakdown = json.loads(cluster.breakdown_json or "{}")
    except Exception:
        breakdown = {}
    companies = sorted({a.company for a in ads if a.company and a.company != "Okänt företag"})
    countries = sorted({a.country for a in ads if a.country})
    representative = ads[0] if ads else None
    opp = breakdown.get("opportunity", {}) if isinstance(breakdown, dict) else {}
    return {
        "id": cluster.id, "product_name": cluster.name, "category": cluster.category,
        "problem_type": cluster.problem_type,
        "problem_summary": representative.problem_summary if representative else "",
        "market_proof": cluster.market_proof or 0, "opportunity_score": cluster.opportunity_score or 0,
        "final_score": cluster.opportunity_score or 0, "confidence": cluster.confidence or 0,
        "problem_solving_score": opp.get("problem_solving", 0),
        "emotional_pressure_score": opp.get("emotional_pressure", 0),
        "purchase_urgency_score": opp.get("purchase_urgency", 0),
        "demo_wow_score": opp.get("demo_wow", 0),
        "signal_labels": opp.get("signal_labels", []),
        "data_quality": cluster.data_quality or 0, "age_status": cluster.age_status,
        "decision": cluster.decision, "ad_count": len(ads),
        "independent_advertisers": len(companies), "companies": companies[:12],
        "company": companies[0] if companies else "Okänt företag", "countries": countries,
        "country": countries[0] if len(countries) == 1 else "MULTI" if countries else "",
        "why_short": _why_short(cluster, breakdown), "breakdown": breakdown,
        "deep_review": _load_json(cluster.deep_review_json),
    }


def top5(session, limit=5):
    clusters = session.execute(
        select(Cluster).where(Cluster.age_status != "NEW")
        .order_by(Cluster.opportunity_score.desc(), Cluster.market_proof.desc(), Cluster.confidence.desc())
        .limit(limit)
    ).scalars().all()
    return [serialize_cluster(session, c) for c in clusters]


def watchlist(session, limit=5):
    clusters = session.execute(
        select(Cluster).where(Cluster.age_status == "NEW")
        .order_by(Cluster.opportunity_score.desc(), Cluster.confidence.desc()).limit(limit)
    ).scalars().all()
    return [serialize_cluster(session, c) for c in clusters]


def snapshot_top5(session):
    items = session.execute(
        select(Cluster).where(Cluster.age_status != "NEW")
        .order_by(Cluster.opportunity_score.desc(), Cluster.market_proof.desc()).limit(5)
    ).scalars().all()
    now = datetime.utcnow()
    for rank, c in enumerate(items, 1):
        session.add(Top5Snapshot(snapshot_at=now, rank=rank, cluster_id=c.id,
                                 opportunity_score=c.opportunity_score or 0,
                                 evidence_delta_json="{}"))
    session.flush()


def deep_review_prompt(cluster_payload, ads):
    ad_samples = []
    for ad in ads[:4]:
        ad_samples.append({
            "company": ad.company, "country": ad.country, "status": ad.ad_status,
            "runtime_days": ad.ad_age_days, "text": ad.raw_text[:3500],
        })
    return f"""Du djupgranskar EN produktmöjlighet för ecommerce research. Du får INTE påstå lönsamhet som fakta.\n\nProduktcluster:\n{json.dumps(cluster_payload, ensure_ascii=False)}\n\nObserverade annonser:\n{json.dumps(ad_samples, ensure_ascii=False)}\n\nReturnera ENDAST JSON med fälten: problem_severity (0-10), emotional_pressure (0-10), purchase_urgency (0-10), demo_wow (0-10), fit_35plus (0-10), evergreen_strength (0-10), willingness_to_pay (0-10), commodity_risk (0-10), seasonality_risk (0-10), confidence (0-10), summary_sv (max 3 korta meningar), strongest_reason_sv, biggest_risk_sv. Var skeptisk och basera dig bara på materialet ovan."""
