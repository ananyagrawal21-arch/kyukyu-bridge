"""Which device + caching combination is fastest? INTEL ONLY (needs x64 / a real Intel GPU).

    python benchmark/bench_device_matrix.py

WHY
    Two independent levers were found, and neither has been tested TOGETHER:
      1. prefix caching  - stops re-reading the ~800 fixed prompt tokens every call (10.94x)
      2. the integrated GPU - never tried at all; the dev Mac exposes CPU only, so this could
         not be explored during development
    They may stack, or the GPU may not support paged attention (prefix caching), in which case
    there is a real trade to make rather than a free win. This measures all four combinations
    so the choice is made on numbers.

Measurement only. Does not touch the app.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OV = str(ROOT / "models" / "qwen2.5-3b-ov-int8")

CASES = [
    "he collapsed and is not breathing",
    "she is clutching her chest and sweating badly",
    "my father fell down the stairs and hit his head",
]


def build_prompts():
    from ontology import load_ontology
    from transformers import AutoTokenizer
    import slm_classify as sc
    ont = load_ontology()
    menu = sc._situation_menu(ont)
    tok = AutoTokenizer.from_pretrained(OV)
    return [
        tok.apply_chat_template(sc._build_messages(c, menu), tokenize=False,
                                add_generation_prompt=True)
        for c in CASES
    ]


def ensure_ov_tokenizer():
    if (Path(OV) / "openvino_tokenizer.xml").exists():
        return
    print("generating OpenVINO tokenizer IR (one-time)...")
    import openvino as ov
    from openvino_tokenizers import convert_tokenizer
    from transformers import AutoTokenizer
    hf = AutoTokenizer.from_pretrained(OV)
    t, d = convert_tokenizer(hf, with_detokenizer=True)
    ov.save_model(t, str(Path(OV) / "openvino_tokenizer.xml"))
    ov.save_model(d, str(Path(OV) / "openvino_detokenizer.xml"))
    print("done.\n")


def trial(prompts, device, prefix_caching):
    import openvino_genai as og
    label = f"{device:3} | prefix caching {'ON ' if prefix_caching else 'OFF'}"
    try:
        sched = og.SchedulerConfig()
        sched.enable_prefix_caching = prefix_caching
        sched.cache_size = 2
        pipe = og.LLMPipeline(OV, device, scheduler_config=sched)
        cfg = og.GenerationConfig()
        cfg.max_new_tokens = 32
        cfg.do_sample = False

        pipe.generate(prompts[0], cfg)  # warm / populate prefix
        times = []
        for p in prompts:
            t0 = time.perf_counter()
            out = pipe.generate(p, cfg)
            times.append(time.perf_counter() - t0)
        mean = sum(times) / len(times)
        print(f"  {label} : mean {mean:6.2f}s   ({'  '.join(f'{t:.2f}' for t in times)})")
        return mean, str(out).strip()
    except Exception as exc:
        print(f"  {label} : UNAVAILABLE - {type(exc).__name__}: {str(exc)[:90]}")
        return None, None


def main():
    try:
        import openvino as ov
        import openvino_genai  # noqa: F401
    except ImportError:
        sys.exit("need: pip install openvino-genai==2025.3.0")

    devices = ov.Core().available_devices
    print("devices:", devices, "\n")
    prompts = build_prompts()
    ensure_ov_tokenizer()

    results = {}
    for device in ("CPU", "GPU"):
        if device not in devices:
            print(f"  {device}: not present on this machine")
            continue
        for pc in (False, True):
            mean, out = trial(prompts, device, pc)
            if mean:
                results[(device, pc)] = (mean, out)

    if not results:
        sys.exit("\nno configuration ran")

    best = min(results, key=lambda k: results[k][0])
    base = results.get(("CPU", False), (None, None))[0]
    print(f"\nFASTEST: {best[0]} with prefix caching "
          f"{'ON' if best[1] else 'OFF'} - {results[best][0]:.2f}s")
    if base:
        print(f"vs CPU baseline ({base:.2f}s): {base / results[best][0]:.2f}x")

    outs = {v[1] for v in results.values()}
    print(f"all configurations produced identical output: {len(outs) == 1}")
    if len(outs) != 1:
        print("  *** OUTPUT DIFFERS BETWEEN CONFIGURATIONS - investigate before shipping ***")
        for k, v in results.items():
            print(f"    {k}: {v[1][:70]}")


if __name__ == "__main__":
    main()
