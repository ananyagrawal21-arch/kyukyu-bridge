# 2-Minute Video — Strategy & Script

120 seconds ≈ 300 spoken words. Every line below is a cut decision.

## The governing principle

**Time budget mirrors the rubric's point budget** (Stage 2: Impact 30 / AI Innovation 30 /
Intel 15). Do not spend half the video on a demo worth a fraction of the score.

    0:00-0:45   Problem & impact        (40% of points)
    0:45-1:30   Solution & safety       (40% of points)
    1:30-1:55   Intel results           (20% of points)
    1:55-2:00   Honest scope

## The three things a judge must remember

1. The ambulance is dispatched in ~15 seconds, **before any AI runs**.
2. **No AI ever writes the Japanese a dispatcher hears** — a human verified all 31 terms in
   advance; the model only selects between them.
3. On Intel hardware, OpenVINO is the difference between **working and not working**.

## Draft script (~300 words)

**[0:00-0:15] — the hook. Do not bury this.**
> "In Japan, an ambulance arrives in 9.8 minutes. But if you don't speak Japanese, the crew
> spends three to six extra minutes on scene just working out what's wrong. That delay is
> measured by Japan's own Fire and Disaster Management Agency."

**[0:15-0:30] — the insight that separates this from a translation app.**
> "You might think the answer is translation. It isn't. The real problem is that a panicking
> person cannot produce structured information at all — in any language. Japan already has
> live interpreters on 119. What it doesn't have is your address, your age, and your heart
> condition, ready before you speak."

**[0:30-0:45] — why the obvious alternatives don't close it.**
> "Japan's own emergency service for people who can't speak — NET119 — is a text chat in
> Japanese. But 13% of foreign residents can barely read Japanese at all."

**[0:45-1:10] — THE DEMO. Screen recording, no narration over the audio itself.**
> "One button. The ambulance is already being dispatched — location and emergency type need
> no AI, so they go out first, in about fifteen seconds."
> *(let the Japanese audio play)*

**[1:10-1:30] — safety, said plainly.**
> "Then it listens, and shows the caller what it understood — in their language — before it
> says anything. Every Japanese sentence comes from 31 terms verified by a human in advance.
> The AI chooses between them. It never writes Japanese."

**[1:30-1:55] — Intel. Feasibility framing, not a percentage.**
> "All of this runs on-device, offline. On this Intel laptop, one classification took 511
> seconds through PyTorch. Through OpenVINO, 73. Then we measured where the time went — the
> model was re-reading the same 800-token menu on every call. OpenVINO's prefix caching
> stopped that: ten times faster, identical output."

**[1:55-2:00] — close. Honesty as strength.**
> "It won't help someone alone outdoors. It's built for one situation — an emergency indoors,
> at a registered address, where nobody present speaks Japanese."

## SHOW vs SAY

    SHOW (screen recording)              SAY (voice over slides/stills)
    the EMERGENCY button                 the problem statement
    救急です + address playing             the safety architecture
    the confirmation screen              the Intel numbers
    the handoff screen, English ON       scope and limits

**Do not film:** setup/registration (one-time, slow), the map picker, or the classification
wait. Cut to the result.

## For a judge who knows nothing about Japan

One line each, unmissable:
- **119 is not 911** — in Japan 119 is fire+ambulance, 110 is police.
- **Japanese addresses have no street names** — prefecture → ward → district → block, numbered
  by registration order. This is *why* the address problem is hard.
- Turn the handoff English toggle ON so the crew screen is readable.

## Assets to build

1. **Workflow diagram** — button press → dispatch → listen → confirm → briefing → handoff.
2. **Benchmark chart** — 511s → 73s → 4.2s.
3. **Sourced-numbers slide** — 9.8 min / 44.6 min / 3–6 min / 23.9% / 13.3%, each with source.

## Traps

- **Never restart the app before recording** — ~60s model load.
- Don't claim the 10× carries to mobile; paged attention is x64-only.
- Don't overstate the GenAI position — DISCLOSURE.md is the honest version.
- Don't spend seconds on competitor comparison. Scored nowhere.

## Open question that changes the plan

Whether judges receive a repo link or run anything themselves. If Stage 1 is video-only, the
video must be fully self-sufficient. **Check the submission form.**
