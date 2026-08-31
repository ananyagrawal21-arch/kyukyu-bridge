"""Convert the SLM to OpenVINO IR with INT8 weight quantization. One-time and slow.
Saves to models/<name>-ov-int8 so the runtime just loads it (no re-conversion).

    python convert_slm.py
"""
import os
from pathlib import Path

from optimum.intel import OVModelForCausalLM, OVWeightQuantizationConfig
from transformers import AutoTokenizer

MODEL_ID = os.environ.get("SLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")
# SLM_OUT_NAME lets a different model (e.g. the smaller 1.5B, used on machines that can't
# fit the 3B model's memory footprint - confirmed 2026-08-11 on a 16GB Windows laptop) save
# to its own clearly-named folder instead of silently overwriting/mislabeling the 3B one.
OUT = Path(__file__).resolve().parent.parent / "models" / os.environ.get("SLM_OUT_NAME", "qwen2.5-3b-ov-int8")
OUT.mkdir(parents=True, exist_ok=True)

print(f"Converting {MODEL_ID} -> OpenVINO INT8", flush=True)
print(f"Output: {OUT}", flush=True)

quant = OVWeightQuantizationConfig(bits=8)
# low_cpu_mem_usage: loads the checkpoint gradually instead of fully materializing it in
# memory first, then converting. Lowers PEAK RAM during exactly the "Loading checkpoint
# shards" step, which is where a 16GB Windows machine was silently OOM-killed (2026-08-11).
model = OVModelForCausalLM.from_pretrained(
    MODEL_ID, export=True, quantization_config=quant, low_cpu_mem_usage=True
)
model.save_pretrained(OUT)
AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(OUT)

print("Done. INT8 OpenVINO model saved.", flush=True)
