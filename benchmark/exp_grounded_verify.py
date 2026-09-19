"""EXPERIMENT: does requiring evidence make Stage B catch single-candidate fabrications?

Finding that motivates it (benchmark/probe_stage_b.py): Stage B prunes multi-candidate lists
almost perfectly (8/9) but catches a lone wrong candidate only ~40% of the time (4/10). All six
surviving fabrications in the probe came from single-candidate lists.

Hypothesis: B's current instruction ("keep the ones the statement describes") is a judgment
with nothing to anchor it. Requiring the supporting WORDS forces an absolute check - you cannot
quote what is not there.

Two variants, because they test different things:
  V1 - same output format, stricter instruction. Cheapest; tests whether wording alone is enough.
  V2 - the model must emit the quote before the numbers. Costs tokens; tests whether the ACT of
       grounding is what matters.

Nothing in src/ is modified. The production _review_list is swapped at runtime and restored.
"""
import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
import os  # noqa: E402

_OV = _ROOT / "models" / "qwen2.5-3b-ov-int8"
if _OV.is_dir():
    os.environ.setdefault("SLM_OV_DIR", str(_OV))

import slm_classify as SC                      # noqa: E402
from ontology import load_ontology             # noqa: E402

DESCRIPTIONS = SC.DESCRIPTIONS


def _numbered(candidate_ids):
    return "\n".join(
        f"{i}. {sid}: {DESCRIPTIONS.get(sid, sid)}" for i, sid in enumerate(candidate_ids, 1)
    )


def _parse_keep(reply, candidate_ids):
    matches = re.findall(r"\[.*?\]", reply, re.DOTALL)
    if not matches:
        return list(candidate_ids)          # fail open, same as production
    try:
        nums = json.loads(matches[-1])      # LAST array: V2 emits quotes first
    except json.JSONDecodeError:
        return list(candidate_ids)
    keep = {n for n in nums if isinstance(n, int) and 1 <= n <= len(candidate_ids)}
    return [sid for i, sid in enumerate(candidate_ids, 1) if i in keep]


def review_v1(pipe, transcript, candidate_ids):
    if not candidate_ids:
        return []
    messages = [
        {"role": "system", "content": (
            "You review a numbered list of symptoms proposed for a caller's statement. "
            "Keep a symptom ONLY if the statement contains words that describe it. "
            "A symptom that is merely plausible, likely, or consistent with the statement - "
            "but not actually described in it - must be REMOVED. "
            "Judge by meaning: callers use everyday and figurative wording. "
            "Removing every item is a correct answer when nothing is described. "
            "Respond with ONLY a JSON array of the NUMBERS to keep, e.g. [1,3]. "
            "Do not write symptom names. If none apply, return []."
        )},
        {"role": "user", "content": (
            f'Statement: "{transcript}"\n\nProposed symptoms:\n'
            f'{_numbered(candidate_ids)}\n\nNumbers to keep:'
        )},
    ]
    return _parse_keep(SC._complete(messages, max_new_tokens=32), candidate_ids)


def review_v2(pipe, transcript, candidate_ids):
    if not candidate_ids:
        return []
    messages = [
        {"role": "system", "content": (
            "You review a numbered list of symptoms proposed for a caller's statement. "
            "For each one, quote the exact words from the statement that describe it. "
            "If you cannot quote any words for it, it is not described and must be removed. "
            "Then give the numbers to keep. "
            "Format:\n1: \"quoted words\" or NONE\n2: \"quoted words\" or NONE\n"
            "KEEP: [1,3]\n"
            "If nothing is described, end with KEEP: []."
        )},
        {"role": "user", "content": (
            f'Statement: "{transcript}"\n\nProposed symptoms:\n{_numbered(candidate_ids)}\n'
        )},
    ]
    return _parse_keep(SC._complete(messages, max_new_tokens=110), candidate_ids)


def run(name, review_fn, cases, ont):
    original = SC._review_list
    if review_fn is not None:
        SC._review_list = review_fn
    out, t0 = [], time.time()
    try:
        for c in cases:
            out.append(set(SC.classify(c["t"], ont)))
    finally:
        SC._review_list = original
    return name, out, time.time() - t0


def main():
    cases = json.loads((Path(__file__).resolve().parent / "diagnostic_probe.json")
                       .read_text(encoding="utf-8"))["cases"]
    ont = load_ontology()
    want = [set(c["e"]) for c in cases]

    print(f"backend: {SC.backend_name()}   cases: {len(cases)}\n", flush=True)
    results = []
    for name, fn in (("baseline", None), ("V1 stricter", review_v1), ("V2 quote-first", review_v2)):
        print(f"running {name} ...", flush=True)
        results.append(run(name, fn, cases, ont))

    print(f"\n{'=' * 92}\nRESULT\n{'=' * 92}")
    print(f"\n{'variant':16} {'exact':>8} {'fabricated':>12} {'missed':>8} {'sec/case':>10}")
    for name, got, secs in results:
        exact = sum(g == w for g, w in zip(got, want))
        fab = sum(len(g - w) for g, w in zip(got, want))
        miss = sum(len(w - g) for g, w in zip(got, want))
        print(f"{name:16} {exact:>4}/{len(cases):<3} {fab:>12} {miss:>8} {secs/len(cases):>10.1f}")

    base = results[0][1]
    for name, got, _ in results[1:]:
        print(f"\n--- {name} vs baseline ---")
        for c, b, g, w in zip(cases, base, got, want):
            if b != g:
                tag = "FIXED  " if (b != w and g == w) else "BROKE  " if (b == w and g != w) else "changed"
                print(f"  {tag} {sorted(b)} -> {sorted(g)}  (want {sorted(w)})  {c['t'][:52]}")


if __name__ == "__main__":
    main()
