"""NLI-7, step 2 - the hybrid checker: Stage B decides, NLI may only RESCUE.

Rule: keep everything Stage B kept. Also keep a symptom Stage B REMOVED if
  (a) its NLI entailment probability is >= R, and
  (b) it is NOT a cardiac-arrest id - those stay entirely with Stage B, which got every one right.
So the hybrid can only ADD symptoms Stage B threw away; it can never raise a cardiac-arrest alarm.

Two method fixes from NLI-6, decided BEFORE any hybrid result was seen:
  - R is chosen by the best F1 on the dev set (balance of right and wrong), not by recall alone.
  - Safety comes from the design (rule b), not from where the line happens to fall.

Run benchmark/dev_stage_b.py first. Reads saved results only - no model is loaded.
"""
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))

from nli_threshold import (  # noqa: E402  reuse, so both experiments score identically
    CPA_IDS, THRESHOLDS, entail, evaluate, load_sets, nli_keeps, proposals, row, stage_b_keeps,
)


def hybrid_keeps(t, r):
    kept = stage_b_keeps(t)
    removed = proposals(t) - kept
    rescued = {s for s in removed if s not in CPA_IDS and entail(t, s) >= r}
    return kept | rescued


def choose_r(dev):
    """Best F1 on the dev set; if several R tie, the middle of the tied range."""
    results = {r: evaluate(dev, lambda t, r=r: hybrid_keeps(t, r)) for r in THRESHOLDS}
    for r, res in results.items():
        print(row(f"dev  hybrid R = {r:.2f}", res))
    best = max(res["f1"] for res in results.values())
    tied = [r for r, res in results.items() if res["f1"] == best]
    return tied[len(tied) // 2], tied


def main():
    dev_cases = json.loads((BENCH / "dev_set.json").read_text(encoding="utf-8"))["cases"]
    dev = [(c["transcript"], c["expected"]) for c in dev_cases]
    tests = load_sets()

    # Fail with a plain message, not a KeyError, if step 1 has not been run.
    try:
        for t, _ in dev:
            stage_b_keeps(t)
    except KeyError:
        sys.exit("No Stage B decisions saved for the dev set - run benchmark/dev_stage_b.py first.")

    print("PART 1 - choosing R on the dev set only\n")
    print(row("dev  Stage B alone", evaluate(dev, stage_b_keeps)))
    print(row("dev  NLI alone, X = 0.05", evaluate(dev, lambda t: nli_keeps(t, 0.05))))
    print()
    r, tied = choose_r(dev)
    print(f"\nChosen R = {r:.2f}   (tied range: {tied[0]:.2f}-{tied[-1]:.2f})")

    print("\nPART 2 - the comparison, once\n")
    for name, cases in tests.items():
        print(row(f"{name:5} Stage B alone", evaluate(cases, stage_b_keeps)))
        print(row(f"{name:5} hybrid, R = {r:.2f}", evaluate(cases, lambda t: hybrid_keeps(t, r))))
        print()

    print("PART 3 - every rescue, in every set: was it right?\n")
    for name, cases in [("dev", dev)] + list(tests.items()):
        for t, want in cases:
            rescued = hybrid_keeps(t, r) - stage_b_keeps(t)
            for s in sorted(rescued):
                verdict = "RIGHT - Stage B had wrongly removed it" if s in want else "WRONG - added an error"
                print(f"[{name:5}] rescued {s:22} ({entail(t, s):.2f})  {verdict}")
                print(f"         {t!r}")


if __name__ == "__main__":
    main()
