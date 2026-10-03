"""Does Stage B judge a candidate against the statement, or against the other candidates?

Cached harness data (2026-10-03, OpenVINO INT8) showed B's keep rate depends on list size:
    correct candidate kept:  100% alone   vs  89% with other candidates
    wrong candidate kept:     69% alone   vs  17% with other candidates
If B judged each symptom against the statement, list size would not matter. This re-runs B on
every candidate from a multi-candidate list, ONE AT A TIME, and compares with the cached
together-on-a-list result. Reads the harness caches; loads the model for the isolated calls.
Characterisation only - nothing here changes the shipped classifier.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

from harness import A_CACHE, B_CACHE, load_sets  # noqa: E402  (sets SLM_OV_DIR)
import slm_classify as SC  # noqa: E402


def main():
    a_cache = json.loads(A_CACHE.read_text(encoding="utf-8"))
    b_cache = json.loads(B_CACHE.read_text(encoding="utf-8"))
    SC._load_pipe()
    tally = {(c, m): [0, 0] for c in (True, False) for m in ("together", "alone")}
    flips = []
    for set_name, cases in load_sets().items():
        for t, want in cases:
            cand = sorted(a_cache[t])
            if len(cand) < 2:
                continue
            together = set(b_cache[t + "||" + ",".join(cand)])
            for c in cand:
                alone = bool(SC._review_list(None, t, [c]))
                correct = c in want
                tally[(correct, "together")][0] += c in together
                tally[(correct, "together")][1] += 1
                tally[(correct, "alone")][0] += alone
                tally[(correct, "alone")][1] += 1
                if alone != (c in together):
                    flips.append((set_name, c, correct, c in together, alone, t))
                print(f"  [{set_name:5}] {c:24} correct={correct!s:5} "
                      f"together={c in together!s:5} alone={alone!s:5}  {t}", flush=True)

    print("\nkeep rate, same candidates, judged together vs alone:")
    for correct in (True, False):
        for mode in ("together", "alone"):
            k, n = tally[(correct, mode)]
            print(f"  {'correct' if correct else 'wrong  '} {mode:8}: {k}/{n} = {k / n:.0%}")
    print(f"\n{len(flips)} candidates changed verdict when judged alone.")
    print(f"backend: {SC.backend_name()}")


if __name__ == "__main__":
    main()
