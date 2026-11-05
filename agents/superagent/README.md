# MotionCorr superagent

A GitHub-driven agent for this repository, run in T3 Code. When an allowed person asks for work on an issue or PR, it opens a ticket and gives the ticket its own worker and worktree. It answers in the same thread: with a PR, a finding, or one concrete question.

The principle comes from upstream: take as little human attention as possible, and give as much value as possible. The agent acts only when asked. It speaks only when a person must act or can use a result.

Adapted from [deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype) (MIT, Copyright (c) 2026 DeepSeek Harness Team). That project is a DeepSeek Harness bundle with its own runtime and panel. Here T3 Code provides the runtime, and only the parts T3 lacks are custom.

## Asking for work

Only logins in `config.json` `allowed_logins` can start or stop work (currently `KingAlejandro`).

| On an issue or PR | Effect |
| --- | --- |
| Add `agent:fix`, `agent:triage` or `agent:review` | Opens a ticket of that kind |
| Comment `/agent <request>` | Opens a free-text ticket, or goes to the thread's open ticket |
| Comment `/agent stop`, or remove the label | Stops the ticket. Later messages do not resume it |

Once a ticket exists, every later comment on its thread reaches its worker as context, from anyone, including bots. A person's comment on an ended ticket resumes it. Bot comments never do. A worker hands back a request that is outside its ticket, and the coordinator decides whether it becomes a new ticket.

The agent posts under `KingAlejandro`. Every text it writes starts with the hidden marker `<!-- motioncorr-superagent -->` and the visible line "_Automated agent message._". The gate uses the marker to skip the agent's own comments.

## How it runs

| Upstream concept | Here |
| --- | --- |
| GitHub Source and read position | `sa.py poll`: issue comments, review comments and label events since the last poll. It never backfills history |
| Policy gate | `sa.py` (`gate()`): allowed list, the `/agent` prefix, the agent labels, bot detection. Deterministic and unit-tested |
| Ticket, Mandate, Subscription, Report | The ledger in `~/.motioncorr-superagent/state.json`, shared by every worktree |
| Main Session (router) | A T3 coordinator thread that runs `prompts/coordinator.md` on a schedule |
| Executor Session and directory | One `delegate_task` per ticket with `isolation: "worktree"`. Its child thread is the ticket's worker, and follow-ups go to that same thread |
| Following the PR (CI, reviews) | `watch_pull_request` on the ticket's PR, aimed at the worker thread |
| Panel | The T3 thread list and PR links, plus `sa.py status` |

Worker rules are in `prompts/worker.md`. They add the agent-specific parts to `AGENTS.md` and `CLAUDE.md`: acknowledge once, work quietly, report through `sa.py report`, never merge, plus MotionCorr's evidence and shared-host rules.

## Running it

1. Start a T3 thread on this checkout for the coordinator.
2. In that thread, create an interval `schedule_task` bound to it (for example every 5 minutes) with the prompt: `Read agents/superagent/prompts/coordinator.md and run one pass.` An idle pass costs one short turn.
3. The first `sa.py poll` records the current position and starts from there.

A GitHub webhook to a T3 webhook schedule (filtered on `issue_comment`, `pull_request_review_comment` and `issues`/`pull_request` `labeled`) can replace the interval later. The coordinator pass does not change.

`python3 agents/superagent/sa.py status --all` lists every ticket. `python3 -m unittest agents/superagent/test_sa.py` runs the tests.

## Not ported

- Feishu, the web panel and the Management API: T3 and GitHub cover these.
- Proactive work (upstream's rules, `observe`/`auto` modes and model assessment of unaddressed messages): only explicit requests start work. Add it as a new decision in `gate()` when there is a concrete rule to run.
- Model-based routing of explicit requests: here a request on a thread with no open ticket always opens a ticket, and a request on a thread with an open ticket goes to that ticket's worker, which hands it back if it doesn't fit.
