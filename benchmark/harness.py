"""E0 - the shared harness. Every experiment reports through this or its numbers are not comparable.

WHY IT EXISTS. Exact-match was hiding the thing that matters: one no_pulse false positive and one
missed lower_back_pain both cost "1 case", and only one of them can start telephone CPR.

Rules this enforces:
  - Stage A is computed ONCE and cached. It is greedy (do_sample=False), so it is identical
    across any variant that does not touch the menu or the few-shots. Re-running it per variant
    burns ~20 minutes to reproduce the same bytes, and makes runs look different when they are not.
    A variant that DOES change the prefix (SLM_EXCLUDE, new few-shots) must pass rebuild_a=True.
  - Stage A and Stage A+B are scored separately, so a change can be attributed to the stage it hit.
  - Four numbers, not one: precision, recall, F1, and CPA false positives.
  - CPA-FP is its own gate. A single one fails the run whatever F1 does.
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

import slm_classify as SC          # noqa: E402
from ontology import load_ontology  # noqa: E402

HERE = Path(__file__).resolve().parent
A_CACHE = HERE / ".stage_a_cache.json"
B_CACHE = HERE / ".stage_b_cache.json"

# Anything whose false presence changes the DISPATCH, not just the wording. not_breathing is
# here even though SLM_DISCARD strips it - we count it in Stage A output, where displacement
# shows up first.
CPA_IDS = {"no_pulse", "not_breathing", "choking", "body_cold"}


def load_sets():
    fifty2 = json.loads((HERE / "slm_testset.json").read_text(encoding="utf-8"))["cases"]
    probe = json.loads((HERE / "diagnostic_probe.json").read_text(encoding="utf-8"))["cases"]
    return {
        "52": [(c["transcript"], set(c["expected"])) for c in fifty2],
        "probe": [(c["t"], set(c["e"])) for c in probe],
    }


def stage_a(texts, ont, rebuild=False):
    """Cached Stage A. Key is the transcript; the cache is invalid if the prefix changes."""
    cache = json.loads(A_CACHE.read_text(encoding="utf-8")) if A_CACHE.exists() and not rebuild else {}
    todo = [t for t in texts if t not in cache]
    if todo:
        print(f"  computing Stage A for {len(todo)} uncached cases ...", flush=True)
        menu = SC._situation_menu(ont)
        valid = {sid for sid, _ in menu}
        for i, t in enumerate(todo, 1):
            reply = SC._complete(SC._build_messages(t, menu), max_new_tokens=32)
            cache[t] = SC._parse_ids(reply, valid)
            if i % 10 == 0:
                print(f"    {i}/{len(todo)}", flush=True)
        A_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return {t: set(cache[t]) for t in texts}


def score(pairs):
    """pairs: list of (got, want). Returns precision, recall, F1, cpa_fp, exact."""
    tp = sum(len(g & w) for g, w in pairs)
    fp = sum(len(g - w) for g, w in pairs)
    fn = sum(len(w - g) for g, w in pairs)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    cpa_fp = sum(len((g - w) & CPA_IDS) for g, w in pairs)
    return dict(precision=p, recall=r, f1=f1, cpa_fp=cpa_fp,
                exact=sum(g == w for g, w in pairs), n=len(pairs))


def run_variant(name, *, review=None, gate=None, discard=None, rebuild_a=False):
    """review: replacement for _review_list. gate: (transcript, ids) -> ids, run after B.
    discard: extra ids stripped at the end (the SLM_DISCARD pattern)."""
    ont = load_ontology()
    sets = load_sets()
    texts = [t for cases in sets.values() for t, _ in cases]
    a_out = stage_a(texts, ont, rebuild=rebuild_a)

    # RELABEL, not just filter. If an id is discarded, the expected sets must lose it too -
    # otherwise the score drops because the label is now unreachable, which measures our
    # bookkeeping rather than the model. The 52 contains "I can't find a pulse on him".
    # Stage B is cached too, keyed by (transcript, candidate list). A gate runs AFTER B and
    # cannot change what B was asked, so every gate-only variant reuses the same B output.
    # Without this, comparing four gates costs four identical passes over the model.
    b_cache = json.loads(B_CACHE.read_text(encoding="utf-8")) if B_CACHE.exists() and review is None else {}

    drop = SC.SLM_DISCARD | set(discard or ())
    review_fn = review or SC._review_list
    rows = {}
    for set_name, cases in sets.items():
        a_pairs, ab_pairs = [], []
        for t, want in cases:
            a = a_out[t]
            want = {i for i in want if i not in drop}
            a_pairs.append(({i for i in a if i not in drop}, want))
            key = t + "||" + ",".join(sorted(a))
            if review is None and key in b_cache:
                kept = set(b_cache[key])
            else:
                kept = set(review_fn(None, t, sorted(a)))
                if review is None:
                    b_cache[key] = sorted(kept)
            if gate:
                kept = set(gate(t, kept))
            ab_pairs.append(({i for i in kept if i not in drop}, want))
        rows[set_name] = (score(a_pairs), score(ab_pairs))
    if review is None:
        B_CACHE.write_text(json.dumps(b_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return name, rows


def report(results):
    print(f"\n{'=' * 104}")
    print(f"{'variant':22} {'set':7} {'stage':5} {'P':>6} {'R':>6} {'F1':>6} {'exact':>8} {'CPA-FP':>8}")
    print("=" * 104)
    for name, rows in results:
        for set_name, (a, ab) in rows.items():
            for label, s in (("A", a), ("A+B", ab)):
                flag = "  <-- FAIL" if s["cpa_fp"] else ""
                print(f"{name:22} {set_name:7} {label:5} {s['precision']:6.3f} {s['recall']:6.3f} "
                      f"{s['f1']:6.3f} {s['exact']:4}/{s['n']:<3} {s['cpa_fp']:>8}{flag}")
    print(f"\nbackend: {SC.backend_name()}    CPA-FP ids: {sorted(CPA_IDS)}")
    print("Ship rule: any CPA-FP > 0 is a revert, whatever F1 does.\n")
