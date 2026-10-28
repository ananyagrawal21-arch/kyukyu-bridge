"""The checker: Stage A's second pass, replacing Stage B (decided after NLI-8, wired 2026-10-12).

Stage A's job is recall (miss nothing). The checker's job is precision: for each symptom Stage A
proposed, it asks one yes/no-style question - does what the caller said IMPLY this symptom's
sentence? - and keeps the symptom only if the answer is "yes" with probability >= X.

Model: mDeBERTa-v3 NLI, fine-tuned on our 287 approved sentences, OpenVINO INT8
(models/nli-mdeberta-ft-ov-int8). Each symptom is judged ALONE, never next to the others - Stage B's
root problem was judging the list as a whole (B1b in EXPERIMENT_LOG.md).
Loading and scoring are exactly benchmark/nli_score.py's, so the app runs what was measured.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("KYUKYU_CHECKER_DIR", ROOT / "models" / "nli-mdeberta-ft-ov-int8"))
HYPOTHESES = ROOT / "data" / "nli_hypotheses.json"
X = 0.30         # chosen on the dev set only (NLI-8); test2 F1 0.883 / 0.900 with it
MAX_TOKENS = 128  # this DeBERTa export only compiles with a fixed input size (nli_sanity.py)

_tokenizer = None
_model = None
_hypotheses = None


def available():
    """True if the checker's model files are on this machine."""
    return (MODEL_DIR / "openvino_model.xml").exists()


def _load():
    global _tokenizer, _model, _hypotheses
    if _model is None:
        from optimum.intel import OVModelForSequenceClassification
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        _model = OVModelForSequenceClassification.from_pretrained(MODEL_DIR, compile=False)
        _model.reshape(1, MAX_TOKENS)
        _model.compile()
        _hypotheses = {k: v for k, v in json.loads(HYPOTHESES.read_text(encoding="utf-8")).items()
                       if not k.startswith("_")}
        print(f"[nli_checker] {MODEL_DIR.name}, keep if entailment >= {X}", flush=True)


def entailment(transcript, symptom_id):
    """Probability that what the caller said implies this symptom's sentence (0 to 1)."""
    import torch
    _load()
    inputs = _tokenizer(transcript, _hypotheses[symptom_id], return_tensors="pt",
                        padding="max_length", truncation=True, max_length=MAX_TOKENS)
    probs = torch.softmax(_model(**inputs).logits, dim=-1)[0]
    return float(probs[_model.config.label2id["entailment"]])


def keep(transcript, candidate_ids, skip=()):
    """The symptoms that survive the checker, in Stage A's order.
    `skip` = ids that are never judged here (the button-only statuses); they pass through untouched
    and the caller discards them."""
    _load()
    kept = []
    for sid in candidate_ids:
        if sid in skip:
            kept.append(sid)
        elif sid not in _hypotheses:
            # Every menu symptom has a hypothesis (checked 2026-10-12). If the ontology grows and
            # one is missing, keep the symptom rather than silently dropping it: Stage A is the
            # recall stage, and a missed symptom is the more dangerous error.
            print(f"[nli_checker] no hypothesis for {sid!r} - kept unchecked", flush=True)
            kept.append(sid)
        elif entailment(transcript, sid) >= X:
            kept.append(sid)
    return kept
