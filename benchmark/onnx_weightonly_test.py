"""Runtime test R3b (EXPERIMENT_LOG.md, 2026-10-12): the checker as a weight-only 8-bit ONNX file.

R3 showed ONNX Runtime runs the checker exactly at fp32, but its default INT8 broke it (20-23 of
215 decisions flipped) because it also squeezes the CALCULATION. This tries the method OpenVINO
used, which changed nothing: only the STORED numbers become 8-bit; the maths stays full precision.

Needs ONNX Runtime >= 1.2x for 8-bit MatMulNBits / GatherBlockQuantized, which needs Python >= 3.10:
    .venv311/bin/python benchmark/onnx_weightonly_test.py
Step 1 re-checks the fp32 file in this environment (different tokenizer/runtime versions).
Step 2 builds and checks the 8-bit file. Pass line, set before running: 0 flipped decisions at
X = 0.30 against the OpenVINO INT8 checker's saved scores.
"""
import json
import statistics
import time
from pathlib import Path

import numpy as np
from onnxruntime import InferenceSession
from transformers import AutoTokenizer

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
FT = ROOT / "models" / "nli-mdeberta-ft"          # the trained checker (tokenizer files)
OUT = ROOT / "models" / "nli-mdeberta-ft-onnx"
FP32 = OUT / "model.onnx"                          # exported in R3, 0 flips there
W8 = OUT / "model_w8.onnx"                         # this test's output
X = 0.30
MAX_TOKENS = 128
ENTAILMENT = 0  # config id2label: {0: entailment, 1: neutral, 2: contradiction}


def build_w8():
    """Weight-only 8-bit: MatMul weights and the embedding table (Gather), stored as 8-bit
    numbers in blocks of 128, each block with its own scale and zero point (asymmetric, like
    OpenVINO's int8_asym). accuracy_level unset = the calculation itself stays fp32."""
    import onnx
    from onnxruntime.quantization.matmul_nbits_quantizer import (
        DefaultWeightOnlyQuantConfig, MatMulNBitsQuantizer)
    config = DefaultWeightOnlyQuantConfig(
        block_size=128, is_symmetric=False, bits=8,
        op_types_to_quantize=("MatMul", "Gather"),
        quant_axes=(("MatMul", 0), ("Gather", 1)),
    )
    q = MatMulNBitsQuantizer(onnx.load(str(FP32)), algo_config=config)
    q.process()
    q.model.save_model_to_file(str(W8), use_external_data_format=False)


def compare(path, tok, hyp, ov):
    sess = InferenceSession(str(path), providers=["CPUExecutionProvider"])
    names = {i.name for i in sess.get_inputs()}
    flips, diffs, times = [], [], []
    for key, ov_scores in ov.items():
        sentence, symptom = key.rsplit("||", 1)
        enc = tok(sentence, hyp[symptom], return_tensors="np", padding="max_length",
                  truncation=True, max_length=MAX_TOKENS)
        feed = {k: v for k, v in enc.items() if k in names}
        s = time.time()
        logits = sess.run(None, feed)[0][0]
        times.append(time.time() - s)
        p = np.exp(logits - logits.max())
        p /= p.sum()
        mine, theirs = float(p[ENTAILMENT]), ov_scores["entailment"]
        diffs.append(abs(mine - theirs))
        if (mine >= X) != (theirs >= X):
            flips.append((round(theirs, 3), round(mine, 3), key))
    print(f"{path.name}: {path.stat().st_size / 1e6:.0f} MB | pairs {len(ov)} | flipped at X={X}: "
          f"{len(flips)} | largest score difference {max(diffs):.3f} | "
          f"median {statistics.median(times) * 1000:.1f} ms/pair (Mac CPU)")
    for f in flips:
        print("  flipped (OpenVINO, ONNX):", f)
    return len(flips)


def main():
    tok = AutoTokenizer.from_pretrained(FT)
    hyp = {k: v for k, v in json.loads((ROOT / "data" / "nli_hypotheses.json").read_text()).items()
           if not k.startswith("_")}
    ov = json.loads((BENCH / ".nli_ft_cache.json").read_text())

    print("Step 1 - fp32 file in this environment (must be 0):")
    if compare(FP32, tok, hyp, ov):
        raise SystemExit("Environment does not reproduce the checker - stop, step 2 would be meaningless.")
    print("\nStep 2 - weight-only 8-bit:")
    if not W8.exists():
        build_w8()
    compare(W8, tok, hyp, ov)


if __name__ == "__main__":
    main()
