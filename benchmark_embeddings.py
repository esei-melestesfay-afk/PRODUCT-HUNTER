import argparse
import csv
import json
import time
from pathlib import Path

MODELS = [
    "intfloat/multilingual-e5-small",
    "intfloat/multilingual-e5-base",
    "BAAI/bge-m3",
    "google/embeddinggemma-300m",
]


def prefix(text, model, query=False):
    if "e5" in model.lower():
        return ("query: " if query else "passage: ") + text
    return text


def load_pairs(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("text_a") or not row.get("text_b"):
                continue
            rows.append({
                "text_a": row["text_a"],
                "text_b": row["text_b"],
                "label": int(row.get("same_product", "0")),
                "language_pair": row.get("language_pair", "unknown"),
                "case_type": row.get("case_type", "unknown"),
            })
    return rows


def metrics_at_threshold(scores, threshold):
    tp=fp=tn=fn=0
    for score, label in scores:
        pred = score >= threshold
        if pred and label: tp += 1
        elif pred and not label: fp += 1
        elif not pred and label: fn += 1
        else: tn += 1
    precision = tp / max(1, tp+fp)
    recall = tp / max(1, tp+fn)
    f1 = 2*precision*recall/max(1e-12,precision+recall)
    return {"threshold":threshold,"precision":precision,"recall":recall,"f1":f1,"tp":tp,"fp":fp,"fn":fn,"tn":tn}


def choose_threshold(scores, target_precision=0.95):
    candidates=[]
    for i in range(50, 96):
        t=i/100
        m=metrics_at_threshold(scores,t)
        if m["precision"] >= target_precision:
            candidates.append(m)
    if candidates:
        candidates.sort(key=lambda x:(x["recall"],x["f1"]),reverse=True)
        return candidates[0]
    allm=[metrics_at_threshold(scores,i/100) for i in range(50,96)]
    allm.sort(key=lambda x:(x["precision"],x["f1"]),reverse=True)
    return allm[0]


def run_model(model_name, rows):
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer(model_name)
    a=[prefix(r["text_a"],model_name,query=True) for r in rows]
    b=[prefix(r["text_b"],model_name,query=False) for r in rows]
    start=time.perf_counter()
    va=model.encode(a,normalize_embeddings=True,show_progress_bar=False)
    vb=model.encode(b,normalize_embeddings=True,show_progress_bar=False)
    elapsed=time.perf_counter()-start
    scores=[]
    cross=[]
    for r,x,y in zip(rows,va,vb):
        score=float((x*y).sum())
        scores.append((score,r["label"]))
        if "-" in r["language_pair"] and len(set(r["language_pair"].split("-")))>1:
            cross.append((score,r["label"]))
    best=choose_threshold(scores)
    cross_best=choose_threshold(cross) if cross else None
    return {
        "model":model_name,
        "pairs":len(rows),
        "seconds":round(elapsed,3),
        "ms_per_pair":round((elapsed/max(1,len(rows)))*1000,2),
        "threshold":best,
        "cross_lingual_threshold":cross_best,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("csv",help="CSV med text_a,text_b,same_product,language_pair,case_type")
    p.add_argument("--model",action="append",dest="models",help="Kör bara vald modell; kan anges flera gånger")
    p.add_argument("--out",default="embedding_benchmark_results.json")
    args=p.parse_args()
    rows=load_pairs(args.csv)
    if not rows:
        raise SystemExit("Ingen benchmark-data hittades.")
    results=[]
    for model in (args.models or MODELS):
        print(f"Kör {model}...")
        try:
            results.append(run_model(model,rows))
        except Exception as exc:
            results.append({"model":model,"error":str(exc)})
    Path(args.out).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
