import re
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone

STOPWORDS = {
    "och","att","det","den","som","för","med","på","en","ett","är","du","din","ditt","dina",
    "vi","vår","har","kan","till","av","om","inte","bara","nu","eller","från","så",
    "the","and","that","this","with","for","you","your","our","are","can","from","not","just",
    "der","die","das","und","mit","für","ein","eine","ist","sie","von","auf","nicht",
    "og","for","til","ikke","er","ja","että","se","on","kun","tai","ei",
    "de","het","een","en","van","voor","met","is","je","jouw","niet"
}

LEX = {
    "pain": ["ont","smärta","stel","öm","värk","obekväm","svårt","jobbigt","krångel","läcker",
             "spill","stök","röra","lukt","smuts","tungt","trött på","vaknar med","kan inte",
             "problem","besvär","stress","pain","ache","stiff","sore","uncomfortable","struggle",
             "annoying","mess","leak","difficult","tired of","wake up with","vondt","vanskelig",
             "lei av","træt af","svært ved","müde von","schwer zu","moe van"],
    "severity": ["varje dag","varje natt","varje morgon","hela tiden","kan inte","gör ont",
                 "svårt att sova","hindrar","orkar inte","every day","every night","can't",
                 "cannot","losing sleep","jeden tag","hver dag","dagelijks"],
    "frequency": ["varje dag","dagligen","varje natt","varje morgon","varje gång","hela tiden",
                  "ofta","ständigt","återkommande","every day","daily","every night","every time",
                  "constantly","often","hver dag","daglig","jeden tag","dagelijks"],
    "relief": ["slipp","äntligen","aldrig mer","lättare","enklare","bekvämare","tryggare",
               "utan att behöva","spara tid","mindre krångel","frihet","smidigt","finally",
               "never again","easier","comfort","peace of mind","without having to","endelig",
               "slip for","endlich","eindelijk"],
    "clarity": ["på sekunder","enkelt","direkt","automatiskt","med ett tryck","utan verktyg",
                "one step","in seconds","instantly","easy","simply","automatic","without tools"],
    "evergreen": ["hem","hemma","kök","badrum","sovrum","bil","trädgård","sömn","städ","förvaring",
                  "ordning","komfort","arbete","vardag","rygg","nacke","knä","axel","leder","husdjur",
                  "home","kitchen","bathroom","bedroom","car","garden","sleep","cleaning","storage",
                  "comfort","back","neck","knee","joint","pet","daily"],
    "age35": ["rygg","nacke","knä","axel","leder","stel","sömn","hemmet","trädgård","bil","förvaring",
              "städ","ergonom","bekväm","grepp","lyfta","böja","back","neck","knee","shoulder","joint",
              "stiff","sleep","home","garden","storage","ergonomic","comfort","grip","lifting","bending"],
    "trend": ["tiktok","viral","trend","trending","hype","meme","fidget","collectible","samlarobjekt",
              "limited drop","aesthetic","cute gadget","must have tiktok"],
    "claims": ["botar","bota","behandlar","läker","garanterat resultat","mirakel","medicinskt bevisad",
               "cure","cures","treats","heals","guaranteed results","miracle","clinically proven",
               "diagnos","diabetes","cancer","arthritis cure"],
    "value": ["sparar tid","sparar pengar","återanvänd","hållbar","ersätter","slipp köpa",
              "save time","save money","reusable","durable","replace","lasts for years"],
    "demo": ["före och efter","before and after","se skillnaden","så fungerar","på sekunder",
             "in seconds","one move","ett tryck","med ett drag","utan verktyg","how it works"],
    "broad": ["hem","sömn","städ","kök","bil","trädgård","förvaring","komfort","rygg","nacke",
              "home","sleep","cleaning","kitchen","car","garden","storage","comfort","back","neck"],
    "commodity": ["usb cable","phone case","mobilskal","led strip","led-ljus","water bottle",
                  "vattenflaska","charger","laddare","sunglasses","solglasögon"]
}

CATEGORIES = [
    ("Sömn", ["sömn","sover","sova","kudde","madrass","snark","sleep","pillow","mattress","snore"]),
    ("Rygg & komfort", ["rygg","nacke","knä","axel","leder","stel","ergonom","back","neck","knee","joint"]),
    ("Städning", ["städ","smuts","damm","mopp","borste","clean","dirt","dust","mop","brush"]),
    ("Förvaring & ordning", ["förvaring","ordning","röra","organis","storage","organizer","mess"]),
    ("Kök", ["kök","mat","spill","disk","skär","kitchen","food","spill","dish","cut"]),
    ("Bil", ["bil","bilen","säte","vindruta","car","vehicle","seat","windshield"]),
    ("Trädgård", ["trädgård","gräsmatta","växt","garden","lawn","plant"]),
    ("Husdjur", ["hund","katt","husdjur","pet","dog","cat"]),
    ("Badrum", ["badrum","dusch","toalett","bathroom","shower","toilet"]),
    ("Kläder & skor", ["sko","skor","kläder","shoe","shoes","clothes","sock"]),
    ("Hem & vardag", ["hem","hemma","vardag","home","daily"]),
]

PROBLEMS = [
    ("Smärta/obehag", ["ont","smärta","stel","värk","obekväm","pain","stiff","ache","uncomfortable"]),
    ("Sömnproblem", ["sömn","sova","vaknar","snark","sleep","wake up","snore"]),
    ("Stök/ordning", ["röra","förvaring","ordning","storage","mess","organizer"]),
    ("Tidskrävande vardag", ["tar tid","spara tid","krångel","jobbigt","save time","hassle"]),
    ("Städ/smuts", ["städ","smuts","damm","clean","dirt","dust"]),
    ("Spill/läckage", ["spill","läck","leak"]),
    ("Lyft/böj/rörelse", ["böja","lyfta","grepp","bending","lifting","grip"]),
    ("Husdjur", ["hund","katt","husdjur","pet","dog","cat"]),
]

def bounded(value, lo=0.0, hi=10.0):
    return max(lo, min(hi, float(value)))

def hit_count(text, terms):
    low = text.lower()
    return sum(1 for term in terms if term in low)

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def field(block, names):
    for name in names:
        m = re.search(rf"(?im)^\s*{re.escape(name)}\s*[:\-]\s*(.+?)\s*$", block)
        if m:
            return clean(m.group(1))[:180]
    return ""

def company_name(block):
    value = field(block, ["Company","Företag","Annonsör","Page name","Sidnamn","Page"])
    if value:
        return value
    for line in [clean(x) for x in block.splitlines() if clean(x)][:5]:
        if len(line) <= 90 and not re.search(r"https?://|www\.|sponsored|sponsrad|library id", line, re.I):
            return line
    return "Okänt företag"

def best_rule(text, rules, fallback):
    low = text.lower()
    scores = [(sum(1 for w in words if w in low), label) for label, words in rules]
    score, label = max(scores, default=(0, fallback))
    return label if score else fallback

def product_name(block, category):
    explicit = field(block, ["Product","Produkt","Item","Produktnamn"])
    if explicit:
        return explicit[:90]
    headline = field(block, ["Headline","Rubrik","Title","Titel"])
    if headline and len(headline.split()) <= 7 and not any(
        x in headline.lower() for x in ["slipp","trött","äntligen","spara","upptäck","discover","finally"]
    ):
        return headline[:90]
    return {
        "Sömn":"Sömnprodukt","Rygg & komfort":"Komfortprodukt","Städning":"Städprodukt",
        "Förvaring & ordning":"Förvaringsprodukt","Kök":"Köksprodukt","Bil":"Bilprodukt",
        "Trädgård":"Trädgårdsprodukt","Husdjur":"Husdjursprodukt","Badrum":"Badrumsprodukt",
        "Kläder & skor":"Kläd-/skoprodukt","Hem & vardag":"Hemmaprodukt"
    }.get(category, "Fysisk produkt")

def ad_age_days(text):
    today = datetime.now(timezone.utc).date()
    found = []
    for y,m,d in re.findall(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text):
        try: found.append(datetime(int(y),int(m),int(d)).date())
        except ValueError: pass
    for d,m,y in re.findall(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", text):
        try: found.append(datetime(int(y),int(m),int(d)).date())
        except ValueError: pass
    months = {"jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,
              "may":5,"jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,
              "september":9,"oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12}
    for d,mon,y in re.findall(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b", text):
        if mon.lower() in months:
            try: found.append(datetime(int(y),months[mon.lower()],int(d)).date())
            except ValueError: pass
    if not found:
        return None
    start = min(found)
    return None if start > today else (today-start).days

def longevity_score(days):
    if days is None: return 4.0
    if days >= 365: return 10.0
    if days >= 270: return 9.5
    if days >= 180: return 9.0
    if days >= 120: return 8.0
    if days >= 90: return 7.2
    if days >= 60: return 6.4
    if days >= 30: return 5.5
    if days >= 14: return 4.5
    return 3.2

def signature(text):
    words = re.findall(r"[a-zåäöüßéáàèøæ]{3,}", text.lower())
    c = Counter(w for w in words if w not in STOPWORDS)
    generic = {"köp","beställ","rabatt","gratis","frakt","idag","produkt","produkten",
               "buy","order","discount","free","shipping","today","product","products"}
    return sorted(w for w,_ in c.most_common(30) if w not in generic)

def problem_summary(problem, category):
    return {
        "Smärta/obehag":"Tar sikte på återkommande smärta eller obehag i vardagen.",
        "Sömnproblem":"Tar sikte på ett återkommande sömn- eller nattproblem.",
        "Stök/ordning":"Minskar irritation kring röra, förvaring eller ordning.",
        "Tidskrävande vardag":"Tar bort tid och krångel från en återkommande uppgift.",
        "Städ/smuts":"Gör ett återkommande städ- eller smutsproblem enklare.",
        "Spill/läckage":"Minskar återkommande spill eller läckage.",
        "Lyft/böj/rörelse":"Gör en fysisk vardagsrörelse lättare och mindre jobbig.",
        "Husdjur":"Löser ett återkommande problem för husdjursägare."
    }.get(problem, f"Löser ett återkommande problem inom {category.lower()}.")

def analyze_ad_base(block):
    text = clean(block)
    company = company_name(block)
    headline = field(block, ["Headline","Rubrik","Title","Titel"])
    category = best_rule(text, CATEGORIES, "Övrig vardagsprodukt")
    problem = best_rule(text, PROBLEMS, "Allmänt vardagsproblem")
    product = product_name(block, category)
    days = ad_age_days(text)

    pain = hit_count(text, LEX["pain"])
    sev = hit_count(text, LEX["severity"])
    freq = hit_count(text, LEX["frequency"])
    relief = hit_count(text, LEX["relief"])
    clarity_h = hit_count(text, LEX["clarity"])
    evergreen_h = hit_count(text, LEX["evergreen"])
    age_h = hit_count(text, LEX["age35"])
    value_h = hit_count(text, LEX["value"])
    demo_h = hit_count(text, LEX["demo"])
    broad_h = hit_count(text, LEX["broad"])
    trend_h = hit_count(text, LEX["trend"])
    claim_h = hit_count(text, LEX["claims"])
    commodity_h = hit_count(text, LEX["commodity"])

    problem_strength = bounded(2.0 + pain*.9 + sev*1.25 + freq*.65)
    severity = bounded(1.8 + sev*1.55 + pain*.35)
    frequency = bounded(2.2 + freq*1.45 + pain*.20)
    emotion = bounded(2.0 + relief*1.05 + sev*.55 + pain*.25)
    fit35 = bounded(2.8 + age_h*.95 + evergreen_h*.18 + sev*.20)
    evergreen = bounded(4.2 + evergreen_h*.58 - trend_h*1.7)
    clarity = bounded(3.2 + clarity_h*.95 + (1 if headline else 0) + min(pain,3)*.22)
    value = bounded(3.2 + value_h*1.05 + sev*.35 + freq*.25)
    demo = bounded(3.0 + demo_h*1.25 + clarity_h*.35)
    broad = bounded(4.2 + broad_h*.45 + age_h*.15)
    direct = bounded(3.0 + pain*.35 + relief*.50 + clarity_h*.45 + sev*.25)
    longevity = longevity_score(days)

    trend_penalty = min(3.5, trend_h*1.15)
    compliance_penalty = min(4.5, claim_h*1.30)
    commodity_penalty = min(2.0, commodity_h*.90)

    evidence = (2 if company != "Okänt företag" else 0) + (2 if headline else 0)
    evidence += 3 if days is not None else 0
    evidence += 2 if len(text) >= 180 else (1 if len(text) >= 80 else 0)
    evidence += 1 if pain + sev + relief >= 2 else 0
    confidence = bounded(3.0 + evidence*.65)

    base = (
        problem_strength*.19 + severity*.08 + frequency*.08 + emotion*.09 +
        fit35*.12 + evergreen*.12 + clarity*.08 + value*.06 + demo*.05 +
        broad*.06 + direct*.03 + longevity*.04
    )
    if problem_strength < 4.2: base -= 1.0
    if evergreen < 5.0: base -= .6
    base -= trend_penalty + compliance_penalty + commodity_penalty
    base = bounded(base)

    strengths = []
    if problem_strength >= 7.5: strengths.append("starkt problem")
    if frequency >= 7: strengths.append("återkommer ofta")
    if emotion >= 7: strengths.append("stark lättnad")
    if fit35 >= 7: strengths.append("bra 35+ fit")
    if evergreen >= 8: strengths.append("evergreen")
    if longevity >= 8.5: strengths.append("lång annonslivslängd")
    if demo >= 7: strengths.append("lätt att demonstrera")
    if broad >= 7: strengths.append("bred målgrupp")

    warnings = []
    if trend_penalty: warnings.append("trend-risk")
    if compliance_penalty: warnings.append("claim-risk")
    if commodity_penalty: warnings.append("commodity-risk")
    if days is None: warnings.append("saknar startdatum")

    return {
        "company": company, "product_name": product, "headline": headline,
        "category": category, "problem_type": problem,
        "problem_summary": problem_summary(problem, category),
        "problem_strength": round(problem_strength,1), "severity_score": round(severity,1),
        "frequency_score": round(frequency,1), "emotion_score": round(emotion,1),
        "fit35_score": round(fit35,1), "evergreen_score": round(evergreen,1),
        "clarity_score": round(clarity,1), "value_score": round(value,1),
        "demo_score": round(demo,1), "broad_market_score": round(broad,1),
        "direct_response_score": round(direct,1), "longevity_score": round(longevity,1),
        "ad_age_days": days, "trend_penalty": round(trend_penalty,1),
        "compliance_penalty": round(compliance_penalty,1), "commodity_penalty": round(commodity_penalty,1),
        "confidence_score": round(confidence,1), "base_score": round(base*10,1),
        "signature": signature(f"{product} {category} {problem} {text[:1200]}"),
        "fingerprint": hashlib.sha1((company+"|"+text).lower().encode("utf-8")).hexdigest(),
        "strength_reasons": strengths, "warnings": warnings, "raw_text": block[:20000],
    }

def similarity(a, b):
    sa, sb = set(a.get("signature", [])), set(b.get("signature", []))
    if not sa or not sb: return 0.0
    jac = len(sa & sb) / max(1, len(sa | sb))
    if a.get("category") == b.get("category"): jac += .05
    if a.get("problem_type") == b.get("problem_type"): jac += .05
    return min(1.0, jac)

def enrich_market_context(items):
    buckets = defaultdict(list)
    for i,item in enumerate(items):
        buckets[(item.get("category"), item.get("problem_type"))].append(i)

    for i,item in enumerate(items):
        sellers, similar_count, very_similar = set(), 0, 0
        for j in buckets[(item.get("category"), item.get("problem_type"))][-500:]:
            if i == j: continue
            s = similarity(item, items[j])
            if s >= .34:
                similar_count += 1
                if items[j].get("company") not in ("", "Okänt företag"):
                    sellers.add(items[j].get("company"))
            if s >= .68:
                very_similar += 1

        independent = len(sellers)
        market = bounded(item.get("longevity_score",4)*.62 + min(independent,4)*.65 + min(similar_count,5)*.18)
        saturation = 1.3 if independent >= 8 else .8 if independent >= 5 else .35 if independent >= 3 else 0
        duplicate_penalty = .4 if very_similar >= 4 else 0

        final10 = (
            item.get("base_score",50)/10*.77 +
            market*.15 +
            item.get("confidence_score",5)*.08 -
            saturation - duplicate_penalty
        )
        final10 = bounded(final10)

        item["market_validation_score"] = round(market,1)
        item["similar_ads"] = similar_count
        item["independent_sellers"] = independent
        item["saturation_penalty"] = round(saturation,1)
        item["final_score"] = round(final10*10,1)

        if item["final_score"] >= 82 and item.get("problem_strength",0) >= 7 and item.get("evergreen_score",0) >= 6.8 and item.get("confidence_score",0) >= 6:
            item["decision"] = "TESTA FÖRST"
        elif item["final_score"] >= 72 and item.get("problem_strength",0) >= 6:
            item["decision"] = "STARK KANDIDAT"
        elif item["final_score"] >= 62:
            item["decision"] = "BEHÅLL / MER RESEARCH"
        else:
            item["decision"] = "SVAG / SKIPPA"

        why = list(item.get("strength_reasons", []))[:4]
        if market >= 7.5: why.append("marknadsbevis")
        if independent >= 2: why.append(f"{independent} liknande säljare")
        item["why_short"] = ", ".join(why[:5]) if why else "behöver starkare bevis"
    return items

def top_unique(items, limit=5):
    enrich_market_context(items)
    ordered = sorted(items, key=lambda x: (
        x.get("final_score",0), x.get("problem_strength",0),
        x.get("evergreen_score",0), x.get("longevity_score",0),
        x.get("confidence_score",0)
    ), reverse=True)
    picked = []
    for candidate in ordered:
        if any(similarity(candidate, p) >= .72 for p in picked):
            continue
        picked.append(candidate)
        if len(picked) >= limit:
            break
    return picked

def split_ads(raw):
    raw = (raw or "").strip()
    if not raw: return []
    chunks = [c.strip() for c in re.split(r"\n\s*(?:-{3,}|={3,}|#{3,}\s*AD\s*#{3,})\s*\n", raw, flags=re.I) if c.strip()]
    if len(chunks) > 1: return chunks[:100]
    matches = list(re.finditer(r"(?im)^(?:Company|Företag|Annonsör)\s*[:\-]\s*", raw))
    if len(matches) > 1:
        return [raw[m.start():(matches[i+1].start() if i+1 < len(matches) else len(raw))].strip()
                for i,m in enumerate(matches)][:100]
    return [raw[:200000]]
