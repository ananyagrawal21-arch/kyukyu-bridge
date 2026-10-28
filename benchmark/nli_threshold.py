"""Step 6 of EXPERIMENT_GUIDE.md - choose the cut-off on the dev set, then compare once.

Rule being tested: keep a Stage A proposal if its NLI entailment probability >= X.

Part 1  try X = 0.05 ... 0.95 on the DEV SET ONLY, and choose X there.
Part 2  apply that one X to the 52 and the probe, ONCE, next to today's Stage B.
Part 3  show every sentence where the two checkers disagree, and every cardiac-arrest proposal,
        so each disagreement can be read before anyone is called wrong (founder's rule).

Reads saved results only (Stage A, Stage B, NLI scores) - no model is loaded.
Backend of the scores: Stage A/B Qwen2.5-3B OpenVINO INT8; NLI mDeBERTa OpenVINO INT8; Apple Silicon.
"""
import argparse
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent / "src"))
sys.path.insert(0, str(BENCH))

from harness import A_CACHE, B_CACHE, CPA_IDS, load_sets, score  # noqa: E402
from slm_classify import SLM_DISCARD                              # noqa: E402

# The original checker's scores. hybrid_threshold.py imports from this file and needs these loaded
# at import time; running this file with --cache replaces them (see main).
NLI_CACHE = BENCH / ".nli_cache.json"
NLI = json.loads(NLI_CACHE.read_text(encoding="utf-8"))
STAGE_A = json.loads(A_CACHE.read_text(encoding="utf-8"))
STAGE_B = json.loads(B_CACHE.read_text(encoding="utf-8"))
THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05, 0.10, ... 0.95


def proposals(t):
    """What Stage A proposed for this sentence, minus the three button-only symptoms."""
    return set(STAGE_A[t]) - SLM_DISCARD


def entail(t, symptom):
    return NLI[f"{t}||{symptom}"]["entailment"]


def nli_keeps(t, x):
    """The new checker: keep a proposal if its entailment probability is at least x."""
    return {s for s in proposals(t) if entail(t, s) >= x}


def stage_b_keeps(t):
    """Today's checker, from its saved decisions (keyed exactly as harness.py keys them)."""
    key = t + "||" + ",".join(sorted(STAGE_A[t]))
    return set(STAGE_B[key]) - SLM_DISCARD


def evaluate(cases, checker):
    """Score a checker on a list of (sentence, expected). Same scoring as the baseline."""
    pairs = [(checker(t), set(want) - SLM_DISCARD) for t, want in cases]
    return score(pairs)


def row(label, r):
    return (f"{label:26} P {r['precision']:.3f}  R {r['recall']:.3f}  F1 {r['f1']:.3f}  "
            f"exact {r['exact']:>2}/{r['n']}  CPA {r['cpa_fp']}")


def choose_x(dev):
    """Zero CPA false alarms first, then the best F1 (the balance of right and wrong).
    If several X tie, take the middle one - the furthest from both edges of the tied range.
    Was "best recall" until NLI-8: that rule always pushed X to the most lenient line (NLI-6)."""
    results = {x: evaluate(dev, lambda t, x=x: nli_keeps(t, x)) for x in THRESHOLDS}
    for x, r in results.items():
        print(row(f"dev  X = {x:.2f}", r))
    safe = [x for x, r in results.items() if r["cpa_fp"] == 0]
    if not safe:
        sys.exit("\nNo X avoids every cardiac-arrest false alarm on the dev set. That is the result.")
    best = max(results[x]["f1"] for x in safe)
    tied = [x for x in safe if results[x]["f1"] == best]
    return tied[len(tied) // 2], tied


def main():
    # Which checker's saved scores to judge. Default = the original checker, as before.
    global NLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=NLI_CACHE)
    args = parser.parse_args()
    NLI = json.loads(args.cache.read_text(encoding="utf-8"))
    print(f"Scores from: {args.cache.name}\n")

    dev_cases = json.loads((BENCH / "dev_set.json").read_text(encoding="utf-8"))["cases"]
    dev = [(c["transcript"], c["expected"]) for c in dev_cases]
    tests = load_sets()  # {"52": [...], "probe": [...]}
    # test2: the locked set, written before any training. The headline comparison.
    test2_cases = json.loads((BENCH / "test2_set.json").read_text(encoding="utf-8"))["cases"]
    tests["test2"] = [(c["transcript"], c["expected"]) for c in test2_cases]

    print("PART 1 - choosing X on the dev set only\n")
    x, tied = choose_x(dev)
    print(f"\nChosen X = {x:.2f}   (tied range: {tied[0]:.2f}-{tied[-1]:.2f})")
    print("Chosen BEFORE looking at the 52, the probe or test2. Changing it afterwards is a new, logged run.")

    print("\nPART 2 - the comparison, once\n")
    for name, cases in tests.items():
        print(row(f"{name:5} today's Stage B", evaluate(cases, stage_b_keeps)))
        print(row(f"{name:5} NLI at X = {x:.2f}", evaluate(cases, lambda t: nli_keeps(t, x))))
        print()

    print("PART 3 - read before judging\n")
    print("Every sentence where the two checkers disagree. Scores are entailment probabilities.\n")
    for name, cases in list(tests.items()) + [("dev", dev)]:
        for t, want in cases:
            b = stage_b_keeps(t) if name != "dev" else None
            n = nli_keeps(t, x)
            want = set(want) - SLM_DISCARD
            if name != "dev" and b == n:
                continue
            if name == "dev" and n == want:
                continue  # Stage B never ran on the dev set; show dev cases the NLI gets wrong
            scores = ", ".join(f"{s} {entail(t, s):.2f}" for s in sorted(proposals(t)))
            print(f"[{name}] {t!r}")
            print(f"    expected {sorted(want)}   Stage A proposed: {scores or 'nothing'}")
            if b is not None:
                print(f"    Stage B kept {sorted(b)}   NLI kept {sorted(n)}")
            else:
                print(f"    NLI kept {sorted(n)}")

    print("\nCardiac-arrest proposals - every one Stage A made, and what each checker did:\n")
    for name, cases in list(tests.items()) + [("dev", dev)]:
        for t, want in cases:
            for s in sorted(proposals(t) & CPA_IDS):
                b = "n/a" if name == "dev" else ("KEPT" if s in stage_b_keeps(t) else "removed")
                n = "KEPT" if s in nli_keeps(t, x) else "removed"
                ok = "correct" if s in want else "FALSE ALARM if kept"
                print(f"[{name}] {s:10} {ok:20} Stage B {b:8} NLI {n:8} "
                      f"({entail(t, s):.2f})  {t!r}")


if __name__ == "__main__":
    main()
