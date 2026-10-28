"""Runtime test R3 (EXPERIMENT_LOG.md, 2026-10-12): the fine-tuned checker on ONNX Runtime.

ONNX Runtime Mobile is the candidate runtime for the checker on phones. This exports the trained
checker (models/nli-mdeberta-ft) to ONNX, compresses it to INT8 (dynamic quantization), and scores
every (sentence, symptom) pair already scored by the OpenVINO INT8 checker. Pass bar, set before
running: 0 decisions flipped at X = 0.30 (the same bar as the INT8 vs fp32 test).
"""
import json
import statistics
import time
from pathlib import Path

import numpy as np

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
FT = ROOT / "models" / "nli-mdeberta-ft"
OUT = ROOT / "models" / "nli-mdeberta-ft-onnx"
X = 0.30
MAX_TOKENS = 128


def main():
    from onnxruntime import InferenceSession
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    fp32 = OUT / "model.onnx"
    int8 = OUT / "model_int8.onnx"
    if not fp32.exists():
        ORTModelForSequenceClassification.from_pretrained(FT, export=True).save_pretrained(OUT)
    if not int8.exists():
        quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    print(f"ONNX INT8 size: {int8.stat().st_size / 1e6:.0f} MB")

    tok = AutoTokenizer.from_pretrained(FT)
    sess = InferenceSession(str(int8), providers=["CPUExecutionProvider"])
    input_names = {i.name for i in sess.get_inputs()}
    entail_id = 0  # config id2label: {0: entailment, 1: neutral, 2: contradiction}

    hyp = {k: v for k, v in json.loads((ROOT / "data" / "nli_hypotheses.json").read_text()).items()
           if not k.startswith("_")}
    ov = json.loads((BENCH / ".nli_ft_cache.json").read_text())

    flips, diffs, times = [], [], []
    for key, ov_scores in ov.items():
        sentence, symptom = key.rsplit("||", 1)
        enc = tok(sentence, hyp[symptom], return_tensors="np", padding="max_length",
                  truncation=True, max_length=MAX_TOKENS)
        feed = {k: v for k, v in enc.items() if k in input_names}
        s = time.time()
        logits = sess.run(None, feed)[0][0]
        times.append(time.time() - s)
        p = np.exp(logits - logits.max()); p /= p.sum()
        onnx_e, ov_e = float(p[entail_id]), ov_scores["entailment"]
        diffs.append(abs(onnx_e - ov_e))
        if (onnx_e >= X) != (ov_e >= X):
            flips.append((round(ov_e, 3), round(onnx_e, 3), key))

    print(f"pairs compared: {len(ov)} | decisions flipped at X={X}: {len(flips)} | "
          f"largest score difference: {max(diffs):.3f} | median {statistics.median(times)*1000:.1f} ms/pair (Mac CPU)")
    for f in flips:
        print("  flipped (OpenVINO, ONNX):", f)


if __name__ == "__main__":
    main()
