"""NLI-8 step B - prove the training sentences cannot leak into any test.

Checks data/nli_train_sentences.json against every sentence in the 52, the probe, the dev set and
test2, and checks its labels. Prints "none" for each check when the file is clean. Training must not
start until all checks say "none".

  exact copies  - a training sentence identical to a test sentence
  near-copies   - more than half of the words shared (word-set overlap > 0.5), the same check used
                  when test2 was written
  bad labels    - an id that has no hypothesis sentence, a button-only id (conscious, unconscious,
                  not_breathing), or the same id in both "expected" and "denied"
  duplicates    - the same training sentence twice
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
BUTTON_ONLY = {"conscious", "unconscious", "not_breathing"}
NEAR = 0.5


def words(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def overlap(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / max(1, len(wa | wb))


def test_sentences():
    out = [(f"52", c["transcript"]) for c in
           json.loads((BENCH / "slm_testset.json").read_text(encoding="utf-8"))["cases"]]
    out += [("probe", c["t"]) for c in
            json.loads((BENCH / "diagnostic_probe.json").read_text(encoding="utf-8"))["cases"]]
    for name, f in (("dev", "dev_set.json"), ("test2", "test2_set.json")):
        out += [(name, c["transcript"]) for c in
                json.loads((BENCH / f).read_text(encoding="utf-8"))["cases"]]
    return out


def main():
    train = json.loads((ROOT / "data" / "nli_train_sentences.json").read_text(encoding="utf-8"))
    sentences = train["sentences"]
    hypotheses = {k for k in json.loads((ROOT / "data" / "nli_hypotheses.json")
                                        .read_text(encoding="utf-8")) if not k.startswith("_")}
    tests = test_sentences()
    test_texts = {t for _, t in tests}

    exact = [(s["n"], s["transcript"]) for s in sentences if s["transcript"] in test_texts]
    near = [(s["n"], s["transcript"], name, t, round(overlap(s["transcript"], t), 2))
            for s in sentences for name, t in tests
            if s["transcript"] not in test_texts and overlap(s["transcript"], t) > NEAR]
    bad = []
    for s in sentences:
        for field in ("expected", "denied"):
            for i in s[field]:
                if i in BUTTON_ONLY:
                    bad.append((s["n"], field, i, "button-only id"))
                elif i not in hypotheses:
                    bad.append((s["n"], field, i, "no hypothesis sentence"))
        for i in set(s["expected"]) & set(s["denied"]):
            bad.append((s["n"], "both", i, "in expected AND denied"))
    dupes = [t for t, k in Counter(s["transcript"] for s in sentences).items() if k > 1]

    print(f"{len(sentences)} training sentences checked against {len(tests)} test sentences.\n")
    print("exact copies:", exact or "none")
    print("near-copies: ", "none" if not near else "")
    for n, t, name, other, o in near:
        print(f"   #{n} {t!r}\n        ~ [{name}] {other!r}  (overlap {o})")
    print("bad labels:  ", bad or "none")
    print("duplicates:  ", dupes or "none")

    print("\nsentences per group:", dict(Counter(s["group"] for s in sentences)))
    used = Counter(i for s in sentences for i in s["expected"])
    print("times each symptom is EXPECTED:", dict(sorted(used.items())))
    missing = sorted(hypotheses - set(used))
    print("symptoms never expected:", missing or "none")
    if exact or near or bad or dupes:
        sys.exit("\nNOT CLEAN - fix the items above before training.")
    print("\nCLEAN - ready for training.")


if __name__ == "__main__":
    main()
