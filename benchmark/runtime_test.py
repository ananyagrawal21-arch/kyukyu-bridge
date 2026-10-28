"""Runtime tests R1/R2 (EXPERIMENT_LOG.md, 2026-10-12): Stage A on llama.cpp vs OpenVINO.

Runs Stage A with EXACTLY the same messages and parser as src/slm_classify.py, but through
llama.cpp (a GGUF file) instead of OpenVINO, on the 52 + probe + dev. test2 (locked) is added ONLY
with --test2, for a pre-registered one-off run (T2-L in EXPERIMENT_LOG.md).
Then compares against the saved OpenVINO Stage A results:
  - do they propose the same symptoms?
  - Stage A recall (the ceiling for the whole pipeline)
  - the full pipeline: proposals -> fine-tuned checker (OpenVINO INT8, X = 0.30) -> P/R/F1/CPA
  - speed per call on this Mac, warm (prompt reused) and with the prompt state reset
Usage: .venv/bin/python benchmark/runtime_test.py --gguf models/gguf/<file>.gguf --tag q8
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCH))

from harness import A_CACHE, CPA_IDS, load_sets, score  # noqa: E402
from ontology import load_ontology                      # noqa: E402
import slm_classify as SC                               # noqa: E402

FT_CHECKER = ROOT / "models" / "nli-mdeberta-ft-ov-int8"
FT_SCORES = BENCH / ".nli_ft_cache.json"
X = 0.30  # the checker's line, chosen on the dev set in NLI-8


def sentences(with_test2=False):
    sets = load_sets()
    dev = json.loads((BENCH / "dev_set.json").read_text(encoding="utf-8"))["cases"]
    sets["dev"] = [(c["transcript"], c["expected"]) for c in dev]
    if with_test2:
        t2 = json.loads((BENCH / "test2_set.json").read_text(encoding="utf-8"))["cases"]
        sets["test2"] = [(c["transcript"], c["expected"]) for c in t2]
    return sets


def run_stage_a(llm, transcript, menu, valid):
    reply = llm.create_chat_completion(
        messages=SC._build_messages(transcript, menu),
        max_tokens=32, temperature=0.0, top_k=1,
    )["choices"][0]["message"]["content"]
    return SC._parse_ids(reply, valid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--test2", action="store_true", help="include the locked test2 (pre-registered runs only)")
    args = ap.parse_args()
    cache_path = BENCH / f".stage_a_llamacpp_{args.tag}.json"

    from llama_cpp import Llama
    ont = load_ontology()
    menu = SC._situation_menu(ont)
    valid = {sid for sid, _ in menu}
    sets = sentences(args.test2)
    texts = list(dict.fromkeys(t for cases in sets.values() for t, _ in cases))

    t0 = time.time()
    llm = Llama(model_path=str(args.gguf), n_ctx=2048, n_gpu_layers=-1, verbose=False)
    load_s = time.time() - t0

    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    warm = []
    for i, t in enumerate(texts, 1):
        if t in cache:
            continue
        s = time.time()
        cache[t] = run_stage_a(llm, t, menu, valid)
        warm.append(time.time() - s)
        if i % 20 == 0:
            print(f"  {i}/{len(texts)}", flush=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

    cold = []  # the prompt state thrown away before each call: no prefix reuse
    for t in texts[:8]:
        llm.reset()
        s = time.time()
        run_stage_a(llm, t, menu, valid)
        cold.append(time.time() - s)

    # Checker scores for any (sentence, symptom) pair the OpenVINO run never proposed.
    hyp = {k: v for k, v in json.loads((ROOT / "data" / "nli_hypotheses.json").read_text()).items()
           if not k.startswith("_")}
    nli = json.loads(FT_SCORES.read_text())
    todo = [(t, s) for t in texts for s in cache[t]
            if s not in SC.SLM_DISCARD and f"{t}||{s}" not in nli]
    if todo:
        from nli_score import load_model, score_pair
        tok, model = load_model(FT_CHECKER)
        for t, s in todo:
            nli[f"{t}||{s}"] = score_pair(tok, model, t, hyp[s])
        FT_SCORES.write_text(json.dumps(nli, ensure_ascii=False, indent=1))

    ov = json.loads(A_CACHE.read_text())
    drop = SC.SLM_DISCARD

    def a_props(src, t):
        return set(src[t]) - drop

    def pipeline(src, t):
        return {s for s in a_props(src, t) if nli[f"{t}||{s}"]["entailment"] >= X}

    print(f"\n=== {args.tag}: {args.gguf.name} ===")
    print(f"load {load_s:.1f}s | Stage A per call, warm (prompt reused): median "
          f"{statistics.median(warm) if warm else float('nan'):.2f}s | prompt reset each call: "
          f"median {statistics.median(cold):.2f}s")
    same = sum(a_props(ov, t) == a_props(cache, t) for t in texts)
    print(f"Stage A proposes exactly the same symptoms as OpenVINO: {same}/{len(texts)}")
    for name, cases in sets.items():
        for label, src in (("OpenVINO INT8", ov), (f"llama.cpp {args.tag}", cache)):
            want = [set(w) - drop for _, w in cases]
            exp = sum(len(w) for w in want)
            found = sum(len(w & a_props(src, t)) for (t, _), w in zip(cases, want))
            r = score([(pipeline(src, t), w) for (t, _), w in zip(cases, want)])
            cpa_a = sum(len((a_props(src, t) - w) & CPA_IDS) for (t, _), w in zip(cases, want))
            print(f"{name:6} {label:18} Stage A recall {found}/{exp} = {found/exp:.3f} | "
                  f"pipeline P {r['precision']:.3f} R {r['recall']:.3f} F1 {r['f1']:.3f} "
                  f"exact {r['exact']}/{r['n']} CPA {r['cpa_fp']} | CPA proposed by A: {cpa_a}")
    diffs = [(t, sorted(a_props(ov, t)), sorted(a_props(cache, t))) for t in texts
             if a_props(ov, t) != a_props(cache, t)]
    print(f"\nSentences where Stage A differs ({len(diffs)}):")
    for t, a, b in diffs:
        print(f"  OV {a}  vs  llama {b}   {t!r}")


if __name__ == "__main__":
    main()
