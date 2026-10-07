"""Step 4b of EXPERIMENT_GUIDE.md - Stage A's proposals for the dev set.

The checker only judges what Stage A proposed, and Stage A has never seen the dev cases. This runs
Stage A on them ONCE and saves the result into the same cache file the harness uses, so every later
step reads it instead of running Qwen again.
Backend: Qwen2.5-3B, OpenVINO INT8 (models/qwen2.5-3b-ov-int8). Slow on Apple Silicon: ~10-25 min.
"""
import argparse
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent / "src"))
sys.path.insert(0, str(BENCH))

from harness import stage_a          # noqa: E402  (importing harness also selects the INT8 model)
from ontology import load_ontology   # noqa: E402
from slm_classify import SLM_DISCARD  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--set", choices=["dev", "test2"], default="dev")
args = parser.parse_args()
filename = "dev_set.json" if args.set == "dev" else "test2_set.json"
cases = json.loads((BENCH / filename).read_text(encoding="utf-8"))["cases"]
texts = [c["transcript"] for c in cases]

proposals = stage_a(texts, load_ontology())

never_proposed = 0
for c in cases:
    expected = set(c["expected"])
    got = proposals[c["transcript"]] - SLM_DISCARD
    missing = expected - got
    never_proposed += len(missing)
    flag = f"   <- Stage A never proposed {sorted(missing)}" if missing else ""
    print(f"{c['group']:13} expected {sorted(expected)!s:36} Stage A {sorted(got)}{flag}")
    print(f"{'':13} {c['transcript']!r}")

print(f"\n{len(cases)} cases. Expected symptoms Stage A never proposed: {never_proposed}.")
print("No checker can bring those back - it can only keep or remove what Stage A proposed.")
