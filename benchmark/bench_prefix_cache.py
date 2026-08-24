"""Does OpenVINO prefix caching remove the fixed-prompt cost? INTEL/x64 ONLY.

    python benchmark/bench_prefix_cache.py

WHY THIS EXISTS
    Measured 2026-08-24: Stage A's cost is ~100% PREFILL, not generation. A prompt of 884
    tokens takes ~7.9s to read before a single output token exists; generating 32 tokens after
    that adds almost nothing. And ~800 of those 884 tokens are IDENTICAL on every call - the
    system prompt, the few-shot examples and the 31-entry menu. Only the caller's transcript
    changes.

    So the whole optimisation problem is: stop re-reading the same 800 tokens every call.
    That is exactly what prefix caching does.

WHY IT IS INTEL-ONLY, WHICH IS THE INTERESTING PART
    Prefix caching runs on OpenVINO's paged-attention executor, which requires x64 (or ARM with
    SVE). On the Apple-Silicon dev Mac it refuses to initialise:
        make_pa_executor: only support x64 platform or ARM with SVE support
    It therefore CANNOT be developed or verified on the Mac - it is a genuine Intel-hardware
    optimisation, not a portable one.

This script only MEASURES. It does not touch the app. Safe to run and re-run.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OV = str(ROOT / "models" / "qwen2.5-3b-ov-int8")

# Different transcripts, IDENTICAL fixed prefix - the realistic pattern for this app, where
# every emergency call re-reads the same menu with a different caller statement.
CASES = [
    "he collapsed and is not breathing",
    "she is clutching her chest and sweating badly",
    "my father fell down the stairs and hit his head",
    "my wife is having trouble breathing and turning pale",
]


def build_prompts():
    from ontology import load_ontology
    from transformers import AutoTokenizer
    import slm_classify as sc

    ont = load_ontology()
    menu = sc._situation_menu(ont)
    tok = AutoTokenizer.from_pretrained(OV)
    prompts = [
        tok.apply_chat_template(sc._build_messages(c, menu), tokenize=False,
                                add_generation_prompt=True)
        for c in CASES
    ]
    n = len(tok(prompts[0]).input_ids)
    print(f"prompt size: {n} tokens (~800 of them identical every call)\n")
    return prompts


def ensure_ov_tokenizer():
    """OpenVINO GenAI needs the tokenizer as its OWN IR, not the HuggingFace files.

    convert_slm.py saves the HF tokenizer (which optimum-intel's OVModelForCausalLM uses
    happily), but LLMPipeline requires openvino_tokenizer.xml / openvino_detokenizer.xml and
    fails with:
        Check 'm_ireq_queue_tokenizer' failed ... Tokenizer::encode is not available
    Generated here rather than in convert_slm.py so this stays a measurement-only script that
    changes nothing about how the app loads its model.
    """
    if (Path(OV) / "openvino_tokenizer.xml").exists():
        return
    print("generating OpenVINO tokenizer IR (one-time)...")
    import openvino as ov
    from openvino_tokenizers import convert_tokenizer
    from transformers import AutoTokenizer

    hf = AutoTokenizer.from_pretrained(OV)
    ov_tok, ov_detok = convert_tokenizer(hf, with_detokenizer=True)
    ov.save_model(ov_tok, str(Path(OV) / "openvino_tokenizer.xml"))
    ov.save_model(ov_detok, str(Path(OV) / "openvino_detokenizer.xml"))
    print("done.\n")


def run(prompts, enable_prefix_caching):
    import openvino_genai as og

    sched = og.SchedulerConfig()
    sched.enable_prefix_caching = enable_prefix_caching
    sched.cache_size = 2  # GB reserved for KV cache
    pipe = og.LLMPipeline(OV, "CPU", scheduler_config=sched)

    cfg = og.GenerationConfig()
    cfg.max_new_tokens = 32
    cfg.do_sample = False

    pipe.generate(prompts[0], cfg)  # warm: first call populates the shared prefix
    times = []
    for p in prompts:
        t0 = time.perf_counter()
        out = pipe.generate(p, cfg)
        times.append(time.perf_counter() - t0)
    label = "prefix caching ON " if enable_prefix_caching else "prefix caching OFF"
    print(f"{label}: " + "  ".join(f"{t:5.2f}s" for t in times)
          + f"   | mean {sum(times)/len(times):.2f}s")
    return sum(times) / len(times), str(out)


def main():
    try:
        import openvino_genai  # noqa: F401
    except ImportError:
        sys.exit("openvino-genai not installed:  pip install openvino-genai==2025.3.0")

    prompts = build_prompts()
    ensure_ov_tokenizer()
    try:
        off, out_off = run(prompts, False)
        on, out_on = run(prompts, True)
    except RuntimeError as exc:
        if "x64" in str(exc) or "pa_executor" in str(exc):
            sys.exit(f"\nPrefix caching is unavailable on this CPU (x64/SVE required):\n  {exc}")
        raise

    print(f"\nspeedup: {off / on:.2f}x")
    print(f"same output: {out_off.strip() == out_on.strip()}")
    print("\nNOTE: identical output is REQUIRED, not a bonus. Prefix caching must be a pure")
    print("performance change - if the text differs, something is wrong and it must not ship.")


if __name__ == "__main__":
    main()
