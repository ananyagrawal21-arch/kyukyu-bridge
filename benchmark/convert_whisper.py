"""Convert Whisper to OpenVINO IR with INT8 weight quantization. One-time and slow.
Saves to models/whisper-small-ov-int8 so the runtime just loads it (no re-conversion).

    python benchmark/convert_whisper.py

WHY THIS EXISTS
    Until now OpenVINO ran the SLM and nothing else, so Intel technology touched exactly ONE
    stage of the pipeline. Speech recognition is the other model in the emergency path and the
    first thing that runs after the caller speaks - converting it means the whole inference
    path is Intel-optimized rather than half of it.

    It is also the larger share of the wait than people expect: the SLM's 16s is measured, but
    Whisper runs BEFORE it on every call, on CPU, through plain transformers.

MIRRORS convert_slm.py deliberately - same INT8 weight quantization, same output convention,
same low-memory loading path that a 16GB Windows machine needed.
"""
import os
from pathlib import Path

from optimum.intel import OVModelForSpeechSeq2Seq, OVWeightQuantizationConfig
from transformers import AutoProcessor

MODEL_ID = os.environ.get("WHISPER_MODEL", "openai/whisper-small")
OUT = Path(__file__).resolve().parent.parent / "models" / os.environ.get(
    "WHISPER_OUT_NAME", "whisper-small-ov-int8"
)
OUT.mkdir(parents=True, exist_ok=True)

print(f"Converting {MODEL_ID} -> OpenVINO INT8", flush=True)
print(f"Output: {OUT}", flush=True)

quant = OVWeightQuantizationConfig(bits=8)
model = OVModelForSpeechSeq2Seq.from_pretrained(
    MODEL_ID,
    export=True,
    quantization_config=quant,
    compile=False,          # compiling here would target THIS machine; the runtime compiles
                            # for whatever it actually runs on (CPU / GPU / NPU).
    load_in_8bit=False,     # quantization_config above already covers it; setting both warns.
)
model.save_pretrained(OUT)

# The processor (feature extractor + tokenizer) must travel with the model - without it the
# runtime falls back to downloading from the Hub, which breaks the offline guarantee.
AutoProcessor.from_pretrained(MODEL_ID).save_pretrained(OUT)

print(f"\nDone. Set WHISPER_OV_DIR={OUT} or let src/stt.py autodetect it.", flush=True)
