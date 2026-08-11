"""
Evaluate SLM classification against a labeled test set.

Reports per-sample errors (fabrications = false positives, misses = false negatives)
and aggregate precision / recall / exact-match. Fabrications matter most - they
violate the "never invent a symptom" rule.

    SLM_MODEL="Qwen/Qwen2.5-3B-Instruct" python eval_slm.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ontology import load_ontology
from slm_classify import classify, MODEL_ID

DEFAULT_TESTSET = Path(__file__).resolve().parent / "slm_testset.json"


def main():
    testset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TESTSET
    cases = json.loads(testset.read_text(encoding="utf-8"))["cases"]  # see ontology.py note
    print(f"Test set: {testset.name}")
    ont = load_ontology()

    print(f"Model: {MODEL_ID}   Cases: {len(cases)}\n")

    tp = fp = fn = exact = 0
    fabrications = []  # (transcript, invented ids)
    misses = []        # (transcript, missed ids)

    import os
    verify = os.environ.get("SLM_VERIFY", "1") != "0"
    print(f"Verification pass: {'ON' if verify else 'OFF (stage-A only)'}")

    per_case_times = []
    for idx, c in enumerate(cases, 1):
        expected = set(c["expected"])
        t0 = time.perf_counter()
        pred = set(classify(c["transcript"], ont, verify=verify))
        dt = time.perf_counter() - t0
        per_case_times.append(dt)
        print(f"[{idx}/{len(cases)}] {dt:.1f}s", flush=True)

        # 'acceptable' = genuinely ambiguous labels (e.g. does "fell backwards" count as
        # collapsed?). Both readings are defensible, so predicting one is neither right nor
        # wrong - it is excluded from scoring entirely. Otherwise we would be measuring
        # agreement with an arbitrary judgement call rather than real accuracy, and tuning
        # toward it would be chasing noise.
        ambiguous = set(c.get("acceptable", []))
        pred = pred - ambiguous
        s_tp = pred & expected
        s_fp = pred - expected
        s_fn = expected - pred
        tp += len(s_tp); fp += len(s_fp); fn += len(s_fn)
        if pred == expected:
            exact += 1
        else:
            mark = []
            if s_fp:
                mark.append(f"FABRICATED {sorted(s_fp)}")
                fabrications.append((c["transcript"], sorted(s_fp)))
            if s_fn:
                mark.append(f"MISSED {sorted(s_fn)}")
                misses.append((c["transcript"], sorted(s_fn)))
            print(f"  x {c['transcript']!r}")
            print(f"      expected {sorted(expected)}  got {sorted(pred)}  -> {'; '.join(mark)}")

    n = len(cases)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    print(f"\n--- Aggregate over {n} cases ---")
    print(f"  Exact-match cases : {exact}/{n}  ({100*exact/n:.0f}%)")
    print(f"  Precision         : {prec:.2f}   (of predicted labels, how many were right)")
    print(f"  Recall            : {rec:.2f}   (of true labels, how many were found)")
    print(f"  F1                : {f1:.2f}")
    print(f"  Fabrications (FP) : {fp}   <- most safety-critical")
    print(f"  Misses (FN)       : {fn}")
    import statistics
    print(f"\n--- SLM latency (Mac CPU, plain PyTorch - UNoptimized baseline) ---")
    print(f"  per classification: median {statistics.median(per_case_times):.1f}s  "
          f"mean {statistics.mean(per_case_times):.1f}s  max {max(per_case_times):.1f}s")


if __name__ == "__main__":
    main()
