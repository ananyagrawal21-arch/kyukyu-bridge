"""SLM classification latency: plain PyTorch vs OpenVINO INT8, same machine.

    python benchmark/bench_slm_backends.py

Mirrors bench_stt_backends.py: one variable changed (the runtime), everything else identical -
same model, same prompts, same verification pass - so any difference is attributable to
OpenVINO and nothing else.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CASE = "My grandfather suddenly collapsed in the living room and he's not responding to me."


def timed(label):
    import slm_classify as sc
    ont_local = sc.load_ontology()
    sc.classify(CASE, ont_local)  # warm - first call pays graph build / weight materialisation
    best, result = float("inf"), None
    for _ in range(3):
        t0 = time.perf_counter()
        result = sc.classify(CASE, ont_local)
        best = min(best, time.perf_counter() - t0)
    print(f"{label:24} : {best:6.2f}s   -> {result}")
    return best, result


def main():
    import slm_classify as sc

    print("PyTorch (unoptimized baseline):")
    os.environ.pop("SLM_OV_DIR", None)
    sc._pipe = None
    t_pt, r_pt = timed("  plain PyTorch")

    ov_dir = ROOT / "models" / "qwen2.5-3b-ov-int8"
    if not ov_dir.is_dir():
        print("\nNo OpenVINO IR found - run benchmark/convert_slm.py first.")
        return

    print("\nOpenVINO INT8:")
    os.environ["SLM_OV_DIR"] = str(ov_dir)
    sc._pipe = None
    t_ov, r_ov = timed("  OpenVINO INT8")

    print(f"\nspeedup: {t_pt / t_ov:.2f}x")
    print(f"same result: {set(r_pt) == set(r_ov)}")


if __name__ == "__main__":
    main()
