"""Is Stage B earning its call?

The diagnostic probe found 7 failures, every one of them the model asserting something the
statement did not say. Stage B's entire job is to drop exactly that. So either it never saw
the fabrication, or it saw it and kept it.

Runs each case twice - Stage A alone, then Stage A + B - and reports what B actually changed.
Stage A is greedy (do_sample=False), so its output is identical across the two runs and the
difference is attributable to B alone.
"""
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

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
    rows = []

    print(f"backend: {backend_name()}   cases: {len(data['cases'])}\n", flush=True)
    t0 = time.time()
    for i, c in enumerate(data["cases"], 1):
        a = set(classify(c["t"], ont, verify=False))
        ab = set(classify(c["t"], ont, verify=True))
        want = set(c["e"])
        rows.append((c, a, ab, want))
        dropped = a - ab
        note = f"B dropped {sorted(dropped)}" if dropped else "B changed nothing"
        print(f"[{i:2}/{len(data['cases'])}] A={sorted(a)!s:34} AB={sorted(ab)!s:34} {note}",
              flush=True)

    print(f"\n{'=' * 96}\nWHAT STAGE B DID   (total {time.time() - t0:.0f}s)\n{'=' * 96}")

    a_exact = sum(a == w for _, a, _, w in rows)
    ab_exact = sum(ab == w for _, _, ab, w in rows)
    print(f"\nExact match:  Stage A alone {a_exact}/{len(rows)}   Stage A+B {ab_exact}/{len(rows)}")

    acted = [(c, a, ab, w) for c, a, ab, w in rows if a != ab]
    print(f"Stage B changed the answer in {len(acted)}/{len(rows)} cases\n")

    helped = [(c, a, ab, w) for c, a, ab, w in acted if (a - w) and not (ab - w)]
    hurt = [(c, a, ab, w) for c, a, ab, w in acted if (w - ab) and not (w - a)]
    print(f"  B FIXED a fabrication : {len(helped)}")
    for c, a, ab, w in helped:
        print(f"      {sorted(a)} -> {sorted(ab)}   {c['t'][:62]}")
    print(f"  B DELETED a correct id: {len(hurt)}")
    for c, a, ab, w in hurt:
        print(f"      {sorted(a)} -> {sorted(ab)}   {c['t'][:62]}")

    missed_by_b = [(c, a, ab, w) for c, a, ab, w in rows if (ab - w) and a == ab]
    print(f"\n  Fabrications B SAW AND KEPT: {len(missed_by_b)}")
    for c, a, ab, w in missed_by_b:
        print(f"      kept {sorted(ab - w)}   {c['t'][:62]}")


if __name__ == "__main__":
    main()
