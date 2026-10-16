# Motion, corrected.

Three-minute narration, 379 words. No voiceover has been generated.

## 00:00:00–00:00:10 · Motion, corrected.

We came to STFC to make scientific software faster. Then we asked the agents to make the presentation. Naturally.

## 00:00:10–00:00:22 · Tiny particles. Big workload.

In cryo-electron microscopy, tiny movements can blur the picture. RELION's motion correction aligns movie frames so the useful signal adds up.

## 00:00:22–00:00:34 · Find the drift. Undo the drift.

Estimate the motion, shift the frames, then combine them with dose weighting. Simple to say. Rather less simple when there are millions of pixels.

## 00:00:34–00:00:46 · One challenge. Three routes.

We took a standalone RELION-derived engine and explored three acceleration routes: CUDA, JAX and Metal. Different hardware. One very demanding scientific reference.

## 00:00:46–00:01:00 · Antigravity. Very down-to-earth work.

At this STFC, Google and PA hackathon, Antigravity became our workshop. We used it heavily to investigate code, develop changes and iterate. There was still plenty of debugging. Gravity, apparently, still works.

## 00:01:00–00:01:15 · We built a team of agents.

We created specialist agents for our Gemini Enterprise workflow. An architect proposes. A critic challenges. Review and testing agents check. Basically, a very productive meeting where everyone has actually read the code.

## 00:01:15–00:01:28 · Automation. With a human merge button.

On Google Cloud, Gemini-powered workers triage issues, propose fixes and review pull requests. Small scopes, explicit checks, and humans making the final call. No automatic victory lap.

## 00:01:28–00:01:40 · Make it repeatable first.

We tackled thread-dependent randomness and built reproducible comparisons. The fixed CPU matched across one and four threads on all twenty-four tutorial movies.

## 00:01:40–00:01:53 · The tests had notes.

CUDA passed the small synthetic global-alignment tests. Real movies revealed image differences. So we kept the numerical gates, recorded the failures and traced the pipeline. Science, not vibes.

## 00:01:53–00:02:04 · Fast kernel. Same queue.

Then came the classic twist: faster GPU kernels, but no whole-movie speedup yet. The CPU was still doing the expensive reconstruction. We had accelerated the wrong queue.

## 00:02:04–00:02:17 · Follow the bottleneck.

The newest CUDA pull request moves that reconstruction work onto the GPU, with streaming buffers. Its early report is promising. Stage timings are not whole-pipeline speedups. The asterisk stays.

## 00:02:17–00:02:29 · Three routes. Different milestones.

Metal now has a global-alignment implementation proposed for Apple silicon. JAX is an exploration track. Different stages of progress, shared reference tests. We are building evidence, not just backends.

## 00:02:29–00:02:43 · Faster iteration. Better questions.

Our biggest lesson: agents help most when the task and the test are both clear. Antigravity helped us iterate. Independent checks challenged our assumptions. The humans supplied the scientific judgment. And the snacks.

## 00:02:43–00:02:55 · And yes. We delegated the video.

We leave with GPU prototypes, reusable agents, tougher tests and a much clearer next step. Then we gave the agents one final issue: make this look good in three minutes.

## 00:02:55–00:03:00 · Motion, corrected.

Motion, corrected. Hype, tested.
