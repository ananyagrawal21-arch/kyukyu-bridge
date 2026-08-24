# 2-Minute Video — Plan

## Hard requirements (from the submission form)

Six sections are MANDATORY. A judge is looking for each one:
1. Self introduction  2. Problem statement  3. Solution description
4. Demonstration      5. Technology used    6. Future scope

    Length      120s (penalty if over)      File      ≤60 MB, MP4/WMV/FLV/AVI
    On camera   REQUIRED - team speaking directly to camera
    Voice       YOUR voice. AI-generated voiceover is NOT ALLOWED.
    Subtitles   English subtitles required if not in English

**No repository link is part of the submission.** Title (≤10 words), 150-word description,
video, consent forms. Assume judges NEVER RUN THE APP and never see the README.
=> Every claim must be spoken or visible on screen. Nothing can be "they'll look it up."

## The core technique: SPEAK the argument, SHOW the evidence

120 seconds ≈ 300 spoken words. That is nowhere near enough for the numbers this project has.
But **judges can pause**. So:

    SPOKEN  = the argument. Narrative, causation, the "why". Cannot be paused into existence.
    ON SCREEN = the evidence. Sources, tables, benchmarks, diagrams. Dense on purpose.

A citation read aloud costs 4 seconds and sounds laboured. The same citation on screen costs
zero speaking time and is *more* credible because it can be checked. **Never read out a number
that is already legible on screen** - say what it MEANS instead.

## Timing

    0:00-0:08   1. Self introduction      ON CAMERA (satisfies the requirement immediately)
    0:08-0:33   2. Problem statement      + SLIDE A (sourced numbers)
    0:33-0:55   3. Solution description   + SLIDE B (workflow diagram)
    0:55-1:25   4. Demonstration          screen recording, let audio play
    1:25-1:50   5. Technology used        + SLIDE C (benchmarks)
    1:50-2:00   6. Future scope           + SLIDE D (roadmap)

## Script (~295 words)

**[1. SELF INTRODUCTION — 0:00-0:08, on camera]**
> "I'm [name], a grade 11 student in Tokyo. I built Kyūkyū-Bridge — an offline assistant for
> people who have to call 119 in Japan but don't speak Japanese."

**[2. PROBLEM — 0:08-0:33, over SLIDE A]**
> "In Japan an ambulance arrives in 9.8 minutes. But if you don't speak Japanese, the crew
> spends three to six extra minutes on scene just working out what's wrong. That's measured by
> Japan's own Fire and Disaster Management Agency.
> You'd think the fix is translation. It isn't. The real problem is that a panicking person
> can't produce structured information at all — in any language.
> And Japan's own emergency service for people who can't speak, NET119, is a text chat in
> Japanese. Thirteen percent of foreign residents can barely read Japanese."

**[3. SOLUTION — 0:33-0:55, over SLIDE B]**
> "So the app doesn't translate. It prepares. Your address, your age, your heart condition are
> registered in advance, in verified Japanese.
> One button starts the call. Location and emergency type need no AI at all — so they go out
> first, in about fifteen seconds, while everything else is still being worked out."

**[4. DEMONSTRATION — 0:55-1:25, screen recording]**
> "Press once."
> *(let 救急です + the address play — no narration over the Japanese)*
> "The ambulance is already being dispatched. Now it listens, and shows the caller what it
> understood, in their own language, before it says anything.
> Every Japanese sentence comes from thirty-one terms a human verified in advance. The AI only
> chooses between them — it never writes Japanese."
> *(cut to handoff screen, English toggle ON)*
> "And this is what the crew reads when they arrive."

**[5. TECHNOLOGY — 1:25-1:50, over SLIDE C]**
> "Everything runs on the device. No internet, no cloud, no data leaving the room.
> On this Intel laptop one classification took 511 seconds in PyTorch. With OpenVINO, 73.
> Then we measured where the time was going — the model was re-reading the same 800-token menu
> on every call. OpenVINO's prefix caching stopped that. Ten times faster, identical output."

**[6. FUTURE SCOPE — 1:50-2:00, over SLIDE D]**
> "Next: guided CPR in the caller's language, and a phone version. It won't help someone alone
> outdoors — it's built for an emergency indoors, where nobody present speaks Japanese."

## The four slides (dense on purpose — judges can pause)

**SLIDE A — the problem, with sources**

    9.8 min      ambulance to scene            FDMA, 救急・救助の現況 2026
    44.6 min     119 call to hospital handover FDMA, same
    +3-6 min     extra on-scene time, foreign patients   Sapporo City Fire Bureau
    23.9%        residents who converse freely in Japanese   MOJ survey, n=40,000
    13.3%        who can barely or not at all READ Japanese  MOJ survey, n=40,000

**SLIDE B — workflow**

    EMERGENCY → 救急です + address (~15s, NO AI) → listen → confirm with caller
              → verified Japanese briefing → handoff screen for the crew
    Closed ontology: 31 human-verified terms. Model SELECTS, never WRITES.

**SLIDE C — benchmarks**

    SLM classification   PyTorch 511s → OpenVINO 73s → + prefix caching 4.2s
    Speech recognition   transformers 15.7s → OpenVINO 10.5s
    Accuracy             92% exact match · precision 0.98 · F1 0.96 · 52-case test set
    Panic-perturbed      F1 0.98 (repetition, false starts, filler)
    Footprint            3.9 GB on-device · ¥0 per call · fully offline

**SLIDE D — roadmap**

    Now      indoor, registered address, 9 languages
    Next     guided CPR audio in the caller's language (fixed protocol, not generated)
    Then     iOS/Android port · accent-aware Japanese TTS · clinician review

## Traps

- **Never restart the app before recording** — ~60s model load.
- Don't read numbers aloud that are already on screen. Say what they mean.
- Don't claim the 10x carries to mobile — paged attention is x64-only.
- Don't film setup/registration, the map picker, or the classification wait.
- Say "119 is not 911" somewhere — a judge outside Japan will not know.
