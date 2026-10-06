"""Step 2 of EXPERIMENT_GUIDE.md - does the NLI model load, and do its answers make sense?

A KaiGo-style standalone check: four sentence pairs, printed scores and timing. It proves the
model works. It proves nothing about accuracy - that is steps 5 and 6.
Backend: OpenVINO INT8 (models/nli-mdeberta-ov-int8), converted 2026-10-05.
"""
import time
from pathlib import Path

import torch
from optimum.intel import OVModelForSequenceClassification
from transformers import AutoTokenizer

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "nli-mdeberta-ov-int8"
# Fixed input size. This DeBERTa export contains an "If" step whose data size is unknown until it
# runs, and OpenVINO's CPU engine refuses to compile that ("If operation with dynamic rank").
# Fixing the size up front - 1 sentence pair, 128 pieces - removes the unknown. Both the reshape
# and the tokenizer below use this one number, so they can never disagree.
MAX_TOKENS = 128

# (what the caller said, the symptom sentence, what we expect a good model to say)
PAIRS = [
    ("he collapsed and now he's convulsing on the floor", "The person is having a seizure.",
     "entailment"),
    ("she feels boiling hot to the touch", "The person has a high fever.",
     "entailment"),
    ("he had a seizure last month but nothing today", "The person is having a seizure.",
     "NOT entailment"),
    ("he did not hit his head", "The person has a head injury.",
     "contradiction"),
]

load_start = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = OVModelForSequenceClassification.from_pretrained(MODEL_DIR, compile=False)
model.reshape(1, MAX_TOKENS)
model.compile()
print(f"model loaded in {time.time() - load_start:.1f}s")
print("label order:", model.config.id2label)

for caller_said, symptom, expected in PAIRS:
    start = time.time()
    inputs = tokenizer(caller_said, symptom, return_tensors="pt",
                       padding="max_length", truncation=True, max_length=MAX_TOKENS)
    logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    elapsed = time.time() - start

    scores = {model.config.id2label[i]: round(float(p), 3) for i, p in enumerate(probs)}
    top = max(scores, key=scores.get)
    print(f"\n{caller_said!r}\n  -> {symptom!r}")
    print(f"  {scores}   top: {top}   expected: {expected}   ({elapsed:.3f}s)")
