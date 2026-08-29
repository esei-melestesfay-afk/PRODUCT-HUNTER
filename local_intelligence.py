import json
import math
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TAXONOMY_PATH = BASE_DIR / "taxonomy.json"
DEFAULT_MODEL = os.environ.get("LOCAL_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")


def load_taxonomy(path=TAXONOMY_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    categories = data.get("categories") or []
    if not categories:
        raise RuntimeError("taxonomy.json saknar kategorier")
    return data


def _clean(value):
    value = re.sub(r"https?://\S+", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()


def evidence_text(ad):
    metrics = {}
    try:
        metrics = json.loads(getattr(ad, "metrics_json", "{}") or "{}")
    except Exception:
        pass
    domain = metrics.get("domain") or ""
    raw = _clean((getattr(ad, "raw_text", "") or "")[:1800])
    parts = [
        getattr(ad, "product_name", "") or "",
        getattr(ad, "category", "") or "",
        getattr(ad, "problem_summary", "") or "",
        domain,
        raw,
    ]
    return _clean(" | ".join(x for x in parts if x))[:2400]


def problem_text(ad):
    return _clean(" | ".join([
        getattr(ad, "problem_type", "") or "",
        getattr(ad, "problem_summary", "") or "",
        (getattr(ad, "raw_text", "") or "")[:900],
    ]))[:1400]


def _prefix(text, model_name, query=False):
    name = (model_name or "").lower()
    if "e5" in name:
        return ("query: " if query else "passage: ") + text
    return text


def cosine(a, b):
    if a is None or b is None:
        return 0.0
    try:
        return float(sum(float(x) * float(y) for x, y in zip(a, b)))
    except Exception:
        return 0.0


def normalize(vector):
    norm = math.sqrt(sum(float(x) * float(x) for x in vector)) or 1.0
    return [float(x) / norm for x in vector]


class LocalIntelligence:
    def __init__(self, model_name=DEFAULT_MODEL, taxonomy_path=TAXONOMY_PATH):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Lokal ML saknas. Installera requirements-local.txt på Windows-datorn."
            ) from exc

        self.model_name = model_name
        self.taxonomy = load_taxonomy(taxonomy_path)
        self.categories = self.taxonomy["categories"]
        self.model = SentenceTransformer(model_name)
        anchors = [_prefix(c["anchor"], model_name, query=False) for c in self.categories]
        vectors = self.model.encode(anchors, normalize_embeddings=True, show_progress_bar=False)
        self.anchor_vectors = [list(map(float, v)) for v in vectors]

    def encode_product(self, text):
        vec = self.model.encode(
            [_prefix(_clean(text), self.model_name, query=True)],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return list(map(float, vec))

    def encode_problem(self, text):
        vec = self.model.encode(
            [_prefix(_clean(text), self.model_name, query=True)],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return list(map(float, vec))

    def classify_product(self, text, vector=None):
        vector = vector or self.encode_product(text)
        scored = [
            (cosine(vector, anchor), category)
            for category, anchor in zip(self.categories, self.anchor_vectors)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        threshold = float(os.environ.get("TAXONOMY_MIN_SIMILARITY", "0.66"))
        margin = float(os.environ.get("TAXONOMY_MIN_MARGIN", "0.025"))
        accepted = best_score >= threshold and (best_score - second_score) >= margin
        if not accepted:
            unknown = next((x for x in self.categories if x.get("key") == "unknown"), best)
            best = unknown
        return {
            "key": best["key"],
            "label_sv": best["label_sv"],
            "score": round(float(best_score), 4),
            "second_score": round(float(second_score), 4),
            "accepted": bool(accepted),
        }
