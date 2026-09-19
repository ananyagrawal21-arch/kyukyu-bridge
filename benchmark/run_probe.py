"""Diagnostic probe over the SLM. Reports PER CATEGORY, not one blended score.

A single accuracy number hides the distinction that matters: abstaining on a vague
statement is CORRECT, while dropping a clear one is a recognition gap. Both look like
[] in an aggregate score, so the categories exist to keep them apart.

Not a replacement for eval_slm.py - that one's 52 cases back published figures and
must stay untouched.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# Same as app.py: point the classifier at the converted INT8 model if it exists. Without this
# slm_classify falls back to plain PyTorch - same answers, but ~15x slower per call.
import os  # noqa: E402

_OV = _ROOT / "models" / "qwen2.5-3b-ov-int8"
if _OV.is_dir():
    os.environ.setdefault("SLM_OV_DIR", str(_OV))

from ontology import load_ontology              # noqa: E402
from slm_classify import classify, backend_name  # noqa: E402

PROBE = Path(__file__).resolve().parent / "diagnostic_probe.json"


def main():
    data = json.loads(PROBE.read_text(encoding="utf-8"))
    ont = load_ontology()
    by_cat = defaultdict(list)

    print(f"backend: {backend_name()}   cases: {len(data['cases'])}\n", flush=True)
    t0 = time.time()
    for i, c in enumerate(data["cases"], 1):
        got = set(classify(c["t"], ont))
        want = set(c["e"])
        by_cat[c["cat"]].append((c, got, want))
        mark = "OK  " if got == want else "DIFF"
        print(f"[{i:2}/{len(data['cases'])}] {mark} {c['cat']:15} {sorted(got)!s:40} <- {c['t'][:60]}",
              flush=True)

    print(f"\n{'=' * 100}\nRESULTS BY CATEGORY   (total {time.time() - t0:.0f}s)\n{'=' * 100}")
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        exact = sum(g == w for _, g, w in rows)
        missed = [(c, g, w) for c, g, w in rows if w - g]
        extra = [(c, g, w) for c, g, w in rows if g - w]
        print(f"\n{cat}   {exact}/{len(rows)} exact")
        print(f"   {data['categories'][cat]}")
        for c, g, w in missed:
            print(f"   MISSED   {sorted(w - g)}  in: {c['t']}")
        for c, g, w in extra:
            print(f"   EXTRA    {sorted(g - w)}  in: {c['t']}")
    print()


if __name__ == "__main__":
    main()
