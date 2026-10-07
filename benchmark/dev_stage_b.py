"""NLI-7, step 1 - today's Stage B on the dev set.

The hybrid is "Stage B decides; NLI may rescue what Stage B removed". To choose the rescue line on
the dev set, Stage B's dev-set decisions must exist - until now it had only ever run on the 52 and
the probe. This runs Stage B once per dev case, in EXACTLY the way harness.py does (same input
order, same cache key), and saves into the same cache file.
Backend: Qwen2.5-3B, OpenVINO INT8. A few minutes on Apple Silicon.
"""
import argparse
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent / "src"))
sys.path.insert(0, str(BENCH))

from harness import A_CACHE, B_CACHE  # noqa: E402  (importing harness also selects the INT8 model)
import slm_classify as SC             # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--set", choices=["dev", "test2"], default="dev")
args = parser.parse_args()
filename = "dev_set.json" if args.set == "dev" else "test2_set.json"
cases = json.loads((BENCH / filename).read_text(encoding="utf-8"))["cases"]
stage_a = json.loads(A_CACHE.read_text(encoding="utf-8"))
stage_b = json.loads(B_CACHE.read_text(encoding="utf-8"))

todo = []
for c in cases:
    t = c["transcript"]
    candidates = sorted(stage_a[t])               # harness.py passes Stage A's list sorted
    key = t + "||" + ",".join(candidates)         # ...and saves it under this key
    if key not in stage_b:
        todo.append((key, t, candidates))

print(f"{len(cases) - len(todo)} dev cases already have Stage B decisions, {len(todo)} to run.")
for i, (key, t, candidates) in enumerate(todo, 1):
    stage_b[key] = sorted(SC._review_list(None, t, candidates))
    print(f"  {i}/{len(todo)}  {candidates} -> kept {stage_b[key]}   {t!r}", flush=True)

B_CACHE.write_text(json.dumps(stage_b, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Saved. Backend: {SC.backend_name()}")
