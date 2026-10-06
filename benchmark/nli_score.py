"""Step 5 of EXPERIMENT_GUIDE.md - score every Stage A proposal with the NLI checker.

For every case in the dev set, the 52 and the probe, and every symptom Stage A proposed for it,
ask the NLI model: does what the caller said imply this symptom's sentence? All three probabilities
(entailment / neutral / contradiction) are saved to benchmark/.nli_cache.json, so this runs once
and step 6 only reads the file.
Backend: mDeBERTa-v3-base-xnli, OpenVINO INT8 (models/nli-mdeberta-ov-int8), fixed shape 1 x 128.
"""
import json
import sys
import time
from pathlib import Path

import torch
from optimum.intel import OVModelForSequenceClassification
from transformers import AutoTokenizer

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCH))

from harness import A_CACHE, load_sets  # noqa: E402
from slm_classify import SLM_DISCARD     # noqa: E402

MODEL_DIR = ROOT / "models" / "nli-mdeberta-ov-int8"
MAX_TOKENS = 128  # see nli_sanity.py: this DeBERTa export only compiles with a fixed input size
NLI_CACHE = BENCH / ".nli_cache.json"


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = OVModelForSequenceClassification.from_pretrained(MODEL_DIR, compile=False)
    model.reshape(1, MAX_TOKENS)
    model.compile()
    return tokenizer, model


def score_pair(tokenizer, model, caller_said, hypothesis):
    """Returns {"entailment": p, "neutral": p, "contradiction": p}, summing to 1."""
    inputs = tokenizer(caller_said, hypothesis, return_tensors="pt",
                       padding="max_length", truncation=True, max_length=MAX_TOKENS)
    probs = torch.softmax(model(**inputs).logits, dim=-1)[0]
    return {model.config.id2label[i]: float(p) for i, p in enumerate(probs)}


def all_sentences():
    """Every transcript in the three sets, each once."""
    sets = load_sets()  # {"52": [(transcript, expected)], "probe": [...]}
    dev = json.loads((BENCH / "dev_set.json").read_text(encoding="utf-8"))["cases"]
    texts = [t for cases in sets.values() for t, _ in cases] + [c["transcript"] for c in dev]
    return list(dict.fromkeys(texts))  # removes duplicates, keeps the order


def main():
    hypotheses = json.loads((ROOT / "data" / "nli_hypotheses.json").read_text(encoding="utf-8"))
    stage_a = json.loads(A_CACHE.read_text(encoding="utf-8"))
    cache = json.loads(NLI_CACHE.read_text(encoding="utf-8")) if NLI_CACHE.exists() else {}

    todo = []
    for t in all_sentences():
        if t not in stage_a:
            sys.exit(f"No Stage A proposals saved for: {t!r} - run benchmark/dev_stage_a.py first")
        for symptom in stage_a[t]:
            if symptom in SLM_DISCARD:
                continue  # comes from the yes/no buttons, never judged by a checker
            key = f"{t}||{symptom}"
            if key not in cache:
                todo.append((key, t, symptom))

    print(f"{len(cache)} pairs already scored, {len(todo)} to score.")
    if todo:
        tokenizer, model = load_model()
        start = time.time()
        for key, t, symptom in todo:
            cache[key] = score_pair(tokenizer, model, t, hypotheses[symptom])
        per_pair = (time.time() - start) / len(todo)
        NLI_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Scored {len(todo)} pairs, {per_pair:.3f}s per pair. Saved to {NLI_CACHE.name}.")


if __name__ == "__main__":
    main()
