---
name: handoff
description: End-of-session routine for Kyūkyū-Bridge — save everything the next session needs before this one ends or is cleared. Use when the founder says /handoff, "wrap up", or "new session".
---

Save this session's state so the next session continues with no loss. Do these in order:

1. **PROJECT_CONTEXT.md** (local, gitignored): add a dated section "Session <N> (<date>): <title>" with:
   decisions made and WHY (including the founder's pushbacks in a sentence each), new research facts with
   sources, corrections you made, open questions, and the exact next step. Update older sections that changed.
2. **FOUNDER_VOICE.md** (local, gitignored): append every message the founder wrote in this session, verbatim,
   with timestamps, from this session's transcript in ~/.claude/projects/-Users-User-Desktop-kyukyu-bridge/.
3. **EXPERIMENT_LOG.md / OPEN_DECISIONS.md / HANDOFF.md** (tracked, PUBLIC repo): log experiments and decisions —
   no personal details or competition strategy.
4. List the files changed in this session and give the founder explained git commands to commit the tracked
   ones (never run git yourself; never include PROJECT_CONTEXT.md, FOUNDER_VOICE.md, COMPETITIONS.md, data/profile.json).
5. Suggest the next session's title in the form "KB-<NN> · <task>" and give the founder a ready-to-paste first
   message for it (it should say: run /kickoff, then the task).
