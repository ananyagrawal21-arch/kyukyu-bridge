"""B1 - where does each classifier error come from? (BUILD_PLAN.md, Track B)

The harness says HOW MANY errors there are. This says WHERE each one happened, case by case,
so a fix can be aimed at a cause instead of at a score:

  never_proposed  - expected id, Stage A never suggested it        -> a recall problem in A
  removed_by_B    - Stage A suggested it, Stage B threw it away    -> B is too strict
  fabricated      - not expected, A suggested it and B kept it     -> B is too lenient
  saved_by_B      - not expected, A suggested it and B removed it  -> B doing its job

Reads the harness's Stage A / Stage B caches only - no model is loaded. If the caches are missing
or the menu has changed, run benchmark/harness.py first to rebuild them.

Not covered here: Whisper's translation step (both test sets are English text), and anything in
SLM_DISCARD (removed from both the output and the labels, exactly as the harness does).
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

from harness import A_CACHE, B_CACHE, CPA_IDS, load_sets  # noqa: E402
from slm_classify import SLM_DISCARD  # noqa: E402


def analyse():
    a_cache = json.loads(A_CACHE.read_text(encoding="utf-8"))
    b_cache = json.loads(B_CACHE.read_text(encoding="utf-8"))
    rows = []
    for set_name, cases in load_sets().items():
        for t, want in cases:
            if t not in a_cache:
                raise SystemExit(f"Stage A cache missing for: {t!r} - run benchmark/harness.py")
            a_raw = set(a_cache[t])
            key = t + "||" + ",".join(sorted(a_raw))
            if key not in b_cache:
                raise SystemExit(f"Stage B cache missing for: {t!r} - run benchmark/harness.py")
            a = a_raw - SLM_DISCARD
            ab = set(b_cache[key]) - SLM_DISCARD
            want = want - SLM_DISCARD
            for i in sorted(want - a):
                rows.append((set_name, "never_proposed", i, t))
            for i in sorted((want & a) - ab):
                rows.append((set_name, "removed_by_B", i, t))
            for i in sorted(ab - want):
                rows.append((set_name, "fabricated", i, t))
            for i in sorted((a - want) - ab):
                rows.append((set_name, "saved_by_B", i, t))
    return rows


def main():
    rows = analyse()
    order = ["never_proposed", "removed_by_B", "fabricated", "saved_by_B"]
    for cause in order:
        hits = [r for r in rows if r[1] == cause]
        print(f"\n=== {cause}  ({len(hits)}) ===")
        for set_name, _, i, t in hits:
            flag = "  [CPA]" if i in CPA_IDS else ""
            print(f"  [{set_name:5}] {i:24}{flag}  {t}")

    print("\n=== summary ===")
    counts = Counter((r[0], r[1]) for r in rows)
    print(f"{'cause':16} {'52':>4} {'probe':>6}")
    for cause in order:
        print(f"{cause:16} {counts[('52', cause)]:>4} {counts[('probe', cause)]:>6}")
    print("\nnever_proposed + removed_by_B = misses. fabricated = wrong things that reached the "
          "caller's confirm screen.")


if __name__ == "__main__":
    main()
