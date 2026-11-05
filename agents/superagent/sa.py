#!/usr/bin/env python3
"""Gate and ticket ledger for the MotionCorr superagent (see README.md).

T3 Code runs the sessions, worktrees and PR watches. This script owns only what
T3 has no concept of: which GitHub messages may start work (the gate), which
ticket a GitHub thread belongs to, and each ticket's mandate, reports and
replies. State lives outside the repository so every worktree shares it.
Standard library only.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TERMINAL_REPORTS = {"waiting", "ready", "blocked", "failed", "dropped"}
PERSON_REPORTS = {"ready", "blocked", "failed"}
LOG_CAP = 300
SEEN_CAP = 5000


# --------------------------------------------------------------------------- config and state


def load_config(path: Path | None = None) -> dict:
    path = path or Path(os.environ.get("SUPERAGENT_CONFIG", HERE / "config.json"))
    cfg = json.loads(Path(path).read_text())
    cfg["state_dir"] = os.path.expanduser(os.environ.get("SUPERAGENT_STATE_DIR", cfg["state_dir"]))
    return cfg


def policy_version(cfg: dict) -> str:
    basis = json.dumps([sorted(cfg["allowed_logins"]), cfg["labels"], cfg["trigger_prefix"]], sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:12]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def empty_state() -> dict:
    return {"version": 1, "cursor": None, "seen": [], "tickets": {}, "next_id": 1, "candidates": [], "log": []}


@contextlib.contextmanager
def store(cfg: dict, write: bool = True):
    """Exclusive, atomic access to state.json; nothing is written if the body raises."""
    root = Path(cfg["state_dir"])
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / "state.json"
        state = json.loads(path.read_text()) if path.exists() else empty_state()
        yield state
        if write:
            state["seen"] = state["seen"][-SEEN_CAP:]
            state["log"] = state["log"][-LOG_CAP:]
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
            os.replace(tmp, path)


# --------------------------------------------------------------------------- gate


def is_bot(login: str, user_type: str | None = None) -> bool:
    return login.endswith("[bot]") or user_type == "Bot"


def parse_command(body: str, prefix: str) -> str | None:
    """`/agent stop` -> "stop"; `/agent <text>` -> text; anything else -> None."""
    first = body.lstrip()
    if not re.match(re.escape(prefix) + r"(\s|$)", first):
        return None
    rest = first[len(prefix):].strip()
    return "stop" if rest.split("\n", 1)[0].strip().lower() == "stop" else (rest or "")


def gate(trig: dict, state: dict, cfg: dict) -> dict:
    """Decide what one trigger does. Pure: reads state, never changes it."""
    if cfg["marker"] in (trig.get("body") or ""):
        return {"action": "drop", "reason": "agent's own message"}
    allowed = trig["actor"] in cfg["allowed_logins"] and not trig["bot"]
    on_thread = [t for t in state["tickets"].values() if trig["number"] in thread_numbers(t)]
    live = [t for t in on_thread if t["status"] == "open"]
    ended = [t for t in on_thread if t["status"] == "ended"]

    if trig["kind"] in ("labeled", "unlabeled"):
        kind = cfg["labels"].get(trig.get("label") or "")
        if kind is None:
            return {"action": "ignore", "reason": "not an agent label"}
        if not allowed:
            return {"action": "ignore", "reason": f"label changed by unlisted {trig['actor']}"}
        same = [t["id"] for t in live if t["kind"] == kind]
        if trig["kind"] == "unlabeled":
            if same:
                return {"action": "stop", "tickets": same, "reason": f"{trig['label']} removed"}
            return {"action": "ignore", "reason": "label removed with no live ticket"}
        if same:
            return {"action": "ignore", "reason": f"duplicate: {same[0]} is already open"}
        return {"action": "accept", "kind": kind, "reason": f"{trig['label']} added"}

    command = parse_command(trig.get("body") or "", cfg["trigger_prefix"])
    if command is not None and not allowed:
        return {"action": "ignore", "reason": f"request from unlisted {trig['actor']}"}
    if command == "stop":  # also withdraws ended tickets, so a later message cannot resume them
        if live or ended:
            return {"action": "stop", "tickets": [t["id"] for t in live + ended], "reason": "stop requested"}
        return {"action": "ignore", "reason": "stop with no ticket on this thread"}

    # A PR that T3 watches for a live ticket already wakes that worker on new comments.
    deliver = [t["id"] for t in live if not (t.get("watched") and t.get("pr") == trig["number"])]
    if live:
        if deliver:
            return {"action": "deliver", "tickets": deliver, "reason": "follow-up on ticket thread"}
        return {"action": "drop", "reason": "delivered by the PR watch"}
    if ended and not trig["bot"]:
        valid = [t["id"] for t in ended if t["mandate"]["actor"] in cfg["allowed_logins"]]
        if valid:
            return {"action": "resume", "tickets": valid, "reason": "person's message on ended ticket"}
        if command is None:
            return {"action": "ignore", "reason": "mandate revoked: requester no longer allowed"}
    if command is not None:
        return {"action": "accept", "kind": "request", "reason": "explicit /agent request"}
    return {"action": "ignore", "reason": "not addressed to the agent"}


def thread_numbers(ticket: dict) -> set:
    nums = {ticket["number"]}
    if ticket.get("pr"):
        nums.add(ticket["pr"])
    return nums


def new_ticket(trig: dict, kind: str, state: dict, cfg: dict) -> dict:
    tid = f"T{state['next_id']}"
    state["next_id"] += 1
    base = f"{kind}-{trig['number']}"
    names = {t["name"] for t in state["tickets"].values()}
    name, n = base, 2
    while name in names:
        name, n = f"{base}-{n}", n + 1
    ticket = {
        "id": tid, "name": name, "kind": kind, "number": trig["number"], "is_pr": trig["is_pr"],
        "branch": cfg["branch_prefix"] + name, "status": "open", "created": now_iso(),
        "mandate": {"strength": "explicit", "actor": trig["actor"], "trigger_id": trig["id"],
                    "url": trig["url"], "label": trig.get("label"), "policy": policy_version(cfg),
                    "accepted_at": now_iso()},
        "source": trig, "inbox": [], "history": [], "reports": [], "relayed": 0, "acked": [],
        "pr": trig["number"] if (kind == "review" and trig["is_pr"]) else None, "watched": False,
        "worker_thread": None, "task_id": None, "assignment": None, "needs_cancel": False,
    }
    state["tickets"][tid] = ticket
    return ticket


def apply(trig: dict, decision: dict, state: dict, cfg: dict) -> dict:
    act = decision["action"]
    if act == "accept":
        decision = dict(decision, tickets=[new_ticket(trig, decision["kind"], state, cfg)["id"]])
    elif act in ("deliver", "resume"):
        for tid in decision["tickets"]:
            t = state["tickets"][tid]
            t["inbox"].append(trig)
            if act == "resume":
                t["status"], t["ended_reason"] = "open", None
    elif act == "stop":
        for tid in decision["tickets"]:
            t = state["tickets"][tid]
            t["status"], t["ended_reason"] = "stopped", f"stopped by {trig['actor']}"
            t["inbox"] = []
            t["needs_cancel"] = bool(t.get("assignment") and t["assignment"]["state"] == "running")
    state["log"].append({"at": now_iso(), "trigger": trig["id"], "url": trig.get("url"),
                         "actor": trig["actor"], "action": act, "tickets": decision.get("tickets", []),
                         "reason": decision["reason"]})
    return decision


def process(trig: dict, state: dict, cfg: dict) -> dict | None:
    if trig["id"] in state["seen"]:
        return None
    state["seen"].append(trig["id"])
    return apply(trig, gate(trig, state, cfg), state, cfg)


# --------------------------------------------------------------------------- GitHub source


def gh_json(args: list[str]):
    out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else None


def gh_list(path: str) -> list:
    pages = gh_json(["--paginate", "--slurp", path]) or []
    return [item for page in pages for item in page]


def number_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[1])


def comment_trigger(c: dict, kind: str) -> dict:
    if kind == "review_comment":
        number, is_pr, prefix = number_from_url(c["pull_request_url"]), True, "rc"
    else:
        number, is_pr, prefix = number_from_url(c["issue_url"]), "/pull/" in c["html_url"], "ic"
    return {"id": f"{prefix}:{c['id']}", "kind": kind, "number": number, "is_pr": is_pr,
            "actor": c["user"]["login"], "bot": is_bot(c["user"]["login"], c["user"].get("type")),
            "body": c.get("body") or "", "label": None, "url": c["html_url"],
            "created_at": c["created_at"], "comment_id": c["id"]}


def fetch_triggers(cfg: dict, cursor: dict | None) -> tuple[list, dict]:
    repo = cfg["repository"]
    started = now_iso()
    events = gh_json([f"repos/{repo}/issues/events?per_page=100"]) or []
    if cursor is None:  # first run: start from now, never backfill history
        return [], {"since": started, "event_id": max((e["id"] for e in events), default=0)}
    triggers = []
    since = cursor["since"]
    for c in gh_list(f"repos/{repo}/issues/comments?since={since}&sort=updated&direction=asc&per_page=100"):
        if c["created_at"] >= since:
            triggers.append(comment_trigger(c, "comment"))
    for c in gh_list(f"repos/{repo}/pulls/comments?since={since}&sort=updated&direction=asc&per_page=100"):
        if c["created_at"] >= since:
            triggers.append(comment_trigger(c, "review_comment"))
    page, newest = 1, cursor["event_id"]
    while True:
        fresh = [e for e in events if e["id"] > cursor["event_id"]]
        for e in fresh:
            newest = max(newest, e["id"])
            if e["event"] in ("labeled", "unlabeled") and e.get("label") and e.get("issue"):
                actor = (e.get("actor") or {}).get("login", "")
                triggers.append({"id": f"ev:{e['id']}", "kind": e["event"], "number": e["issue"]["number"],
                                 "is_pr": "pull_request" in e["issue"], "actor": actor, "bot": is_bot(actor),
                                 "body": "", "label": e["label"]["name"], "url": e["issue"]["html_url"],
                                 "created_at": e["created_at"], "comment_id": None})
        if len(fresh) < len(events) or len(events) < 100 or page >= 5:
            break
        page += 1
        events = gh_json([f"repos/{repo}/issues/events?per_page=100&page={page}"]) or []
    triggers.sort(key=lambda t: (t["created_at"], t["id"]))
    return triggers, {"since": started, "event_id": newest}


def check_prs(state: dict, cfg: dict) -> None:
    """End open tickets whose PR has merged or closed; the T3 link settles the thread too."""
    for t in state["tickets"].values():
        if t["status"] != "open" or not t.get("pr") or t["kind"] == "review" or t["inbox"]:
            continue
        if t["reports"] and t["reports"][-1]["state"] != "ready":
            continue  # resumed work not yet ready keeps the ticket open
        pr = gh_json([f"repos/{cfg['repository']}/pulls/{t['pr']}"])
        if pr["state"] == "closed":
            t["status"], t["ended_reason"] = "ended", "PR merged" if pr.get("merged") else "PR closed"
            state["log"].append({"at": now_iso(), "trigger": None, "action": "end", "tickets": [t["id"]],
                                 "reason": t["ended_reason"]})


# --------------------------------------------------------------------------- work list for the coordinator


def running(t: dict) -> bool:
    return bool(t.get("assignment") and t["assignment"]["state"] == "running")


def work_list(state: dict, cfg: dict) -> dict:
    tickets = sorted(state["tickets"].values(), key=lambda t: int(t["id"][1:]))
    slots = cfg["max_running"] - sum(running(t) for t in tickets)
    out = {"dispatch": [], "deliver": [], "cancel": [], "watch": [], "relay": [], "stale": [],
           "candidates": state["candidates"]}
    for t in tickets:
        if t.get("needs_cancel"):
            out["cancel"].append({"ticket": t["id"], "task_id": t["task_id"]})
        if t["status"] != "open":
            continue
        if t["worker_thread"] is None and not running(t):
            if slots > 0:
                out["dispatch"].append({"ticket": t["id"], "name": t["name"], "url": t["mandate"]["url"]})
                slots -= 1
        elif t["inbox"]:  # a person's message takes no slot, as upstream's extra slot
            out["deliver"].append({"ticket": t["id"], "thread": t["worker_thread"], "count": len(t["inbox"])})
        if t.get("pr") and not t.get("watched") and t["worker_thread"]:
            out["watch"].append({"ticket": t["id"], "pr": t["pr"], "thread": t["worker_thread"]})
        unrelayed = t["reports"][t["relayed"]:]
        if any(r["state"] in PERSON_REPORTS or r.get("question") for r in unrelayed):
            out["relay"].append({"ticket": t["id"], "report": t["reports"][-1]})
        a = t.get("assignment")
        if running(t):
            age = dt.datetime.now(dt.timezone.utc) - parse_iso(a["started"])
            if age > dt.timedelta(hours=cfg["stale_assignment_hours"]):
                out["stale"].append({"ticket": t["id"], "task_id": t["task_id"], "started": a["started"]})
    return out


# --------------------------------------------------------------------------- briefs and replies


def quote(text: str, limit: int = 4000) -> str:
    text = text if len(text) <= limit else text[:limit] + f"\n[... cut at {limit} of {len(text)} chars; read the URL]"
    return "\n".join("> " + line for line in text.splitlines()) or "> (no text)"


def trigger_card(trig: dict) -> str:
    what = {"labeled": f"added label `{trig.get('label')}`", "unlabeled": f"removed label `{trig.get('label')}`",
            "review_comment": "review comment", "comment": "comment"}[trig["kind"]]
    head = f"- `{trig['id']}` {trig['actor']}{' (bot)' if trig['bot'] else ''}, {what}, {trig['created_at']}: {trig['url']}"
    return head + ("\n" + quote(trig["body"]) if trig.get("body") else "")


def brief(t: dict, cfg: dict) -> str:
    sa = f"python3 {HERE / 'sa.py'}"
    inputs = "\n".join(trigger_card(x) for x in t["inbox"]) or "(none)"
    if t["worker_thread"]:
        return (f"New input for ticket {t['id']} ({t['name']}). Decide each message under the rules you were "
                f"given; finish with `{sa} report {t['id']} ...`.\n\n{inputs}\n")
    m = t["mandate"]
    scope = {"fix": "fix: implement, verify and open a PR",
             "triage": "triage: investigate and report findings; no PR unless the fix is trivial and local",
             "review": "review: review the PR's current head and post findings",
             "request": "request: the free-text request in the source trigger"}[t["kind"]]
    worker_rules = (HERE / "prompts" / "worker.md").read_text()
    return f"""{worker_rules}

# Your ticket

- Ticket: {t['id']} ({t['name']}), repository {cfg['repository']}
- Mandate: {scope}; granted by {m['actor']} via {m['label'] or cfg['trigger_prefix']} ({m['strength']}, policy {m['policy']})
- Source thread: #{t['number']} ({'pull request' if t['is_pr'] else 'issue'}) {m['url']}
- Branch: `{t['branch']}`. Check it out from origin if it exists there, otherwise create it from origin/main.
- Ledger: `{sa}` (state is shared; run it from any directory)

Source trigger:
{trigger_card(t['source'])}

Later messages on the thread:
{inputs}
"""


def word_count(text: str) -> int:
    return len(re.sub(r"\]\([^)]*\)", "]", text).split())


def post(cfg: dict, number: int, text: str, review_comment_id: int | None, dry_run: bool) -> str:
    body = f"{cfg['marker']}\n{cfg['banner']}\n\n{text}"
    repo = cfg["repository"]
    if review_comment_id:
        path = f"repos/{repo}/pulls/{number}/comments/{review_comment_id}/replies"
    else:
        path = f"repos/{repo}/issues/{number}/comments"
    if dry_run:
        return f"[dry-run] POST {path}\n{body}"
    return gh_json([path, "-f", f"body={body}", "--jq", "{url: .html_url}"])["url"]


def find_trigger(t: dict, trigger_id: str) -> dict | None:
    for x in [t["source"], *t["history"], *t["inbox"]]:
        if x["id"] == trigger_id:
            return x
    return None


# --------------------------------------------------------------------------- commands


def die(msg: str) -> None:
    print(f"refused: {msg}", file=sys.stderr)
    raise SystemExit(2)


def get_ticket(state: dict, tid: str) -> dict:
    if tid not in state["tickets"]:
        die(f"no ticket {tid}")
    return state["tickets"][tid]


def cmd_poll(a, cfg):
    with store(cfg, write=not a.dry_run) as state:
        triggers, cursor = fetch_triggers(cfg, state["cursor"])
        for trig in triggers:
            d = process(trig, state, cfg)
            if d and a.verbose:
                print(f"{trig['id']} #{trig['number']} {trig['actor']}: {d['action']} {d.get('tickets', '')} - {d['reason']}",
                      file=sys.stderr)
        state["cursor"] = cursor
        check_prs(state, cfg)
        work = work_list(state, cfg)
    print("idle" if not any(work.values()) else json.dumps(work, indent=1))


def cmd_brief(a, cfg):
    with store(cfg) as state:
        t = get_ticket(state, a.ticket)
        if t["status"] != "open":
            die(f"{t['id']} is {t['status']}")
        text = brief(t, cfg)
        t["history"].extend(t["inbox"])
        t["inbox"] = []
        if t["worker_thread"]:
            t["assignment"] = {"state": "running", "started": now_iso()}
    print(text)


def cmd_bind(a, cfg):
    with store(cfg) as state:
        t = get_ticket(state, a.ticket)
        if a.task:
            t["task_id"], t["assignment"] = a.task, {"state": "running", "started": now_iso()}
        if a.thread:
            t["worker_thread"] = a.thread
        if a.watched:
            t["watched"] = True
        if a.cancelled:
            t["needs_cancel"] = False
            if t.get("assignment"):
                t["assignment"]["state"] = "ended"
        if a.failed:
            t["assignment"] = {"state": "ended", "started": (t.get("assignment") or {}).get("started", now_iso())}
            t["reports"].append({"at": now_iso(), "state": "failed", "summary": a.failed, "pr": t.get("pr"),
                                 "question": None})
    print("ok")


def cmd_report(a, cfg):
    with store(cfg) as state:
        t = get_ticket(state, a.ticket)
        if a.pr is not None:
            if a.pr != t.get("pr"):
                t["pr"], t["watched"] = a.pr, False
        if a.state == "ready" and t["kind"] == "fix" and not t.get("pr"):
            die("a fix is not ready without a PR; report blocked with the reason instead")
        rep = {"at": now_iso(), "state": a.state, "summary": a.summary, "pr": t.get("pr"),
               "question": a.question, "question_trigger": a.question_trigger}
        t["reports"].append(rep)
        if a.state in TERMINAL_REPORTS and t.get("assignment"):
            t["assignment"]["state"] = "ended"
        if a.state == "dropped":
            t["status"], t["ended_reason"] = "ended", "dropped: " + a.summary[:200]
            t["relayed"] = len(t["reports"])
    print("ok")


def cmd_handback(a, cfg):
    with store(cfg) as state:
        t = get_ticket(state, a.ticket)
        trig = find_trigger(t, a.trigger)
        if trig is None:
            die(f"{a.trigger} never reached {t['id']}")
        state["candidates"].append({"trigger": trig, "from": t["id"], "reason": a.reason, "at": now_iso()})
    print("ok")


def cmd_accept(a, cfg):
    with store(cfg) as state:
        cand = next((c for c in state["candidates"] if c["trigger"]["id"] == a.trigger), None)
        if cand is None:
            die(f"{a.trigger} is not a handed-back candidate")
        trig = cand["trigger"]
        if trig["actor"] not in cfg["allowed_logins"] or trig["bot"]:
            die(f"{trig['actor']} may not start work; ignore it instead")
        state["candidates"].remove(cand)
        d = apply(trig, {"action": "accept", "kind": a.kind, "reason": f"handed back by {cand['from']}"}, state, cfg)
    print(d["tickets"][0])


def cmd_ignore(a, cfg):
    with store(cfg) as state:
        cand = next((c for c in state["candidates"] if c["trigger"]["id"] == a.trigger), None)
        if cand is None:
            die(f"{a.trigger} is not a handed-back candidate")
        state["candidates"].remove(cand)
        apply(cand["trigger"], {"action": "ignore", "reason": a.reason}, state, cfg)
    print("ok")


def cmd_reply(a, cfg):
    if word_count(a.text) > cfg["reply_word_limit"]:
        die(f"{word_count(a.text)} words; the limit is {cfg['reply_word_limit']}")
    with store(cfg, write=not a.dry_run) as state:
        t = get_ticket(state, a.ticket)
        trig = find_trigger(t, a.trigger) if a.trigger else None
        if a.trigger and trig is None:
            die(f"{a.trigger} never reached {t['id']}")
        last = t["reports"][-1] if t["reports"] else None
        if a.purpose in ("ack", "answer") and trig is None:
            die(f"{a.purpose} needs --trigger: the message it replies to")
        if a.purpose == "ack" and a.trigger in t["acked"]:
            print("already acknowledged")
            return
        if a.purpose == "result" and not (last and last["state"] in PERSON_REPORTS):
            die("result needs a ready, blocked or failed report")
        if a.purpose == "attention":
            if not (last and last.get("question")):
                die("attention needs a report with --question")
            trig = find_trigger(t, last["question_trigger"]) if last.get("question_trigger") else None
        target = trig or t["source"]
        url = post(cfg, target["number"], a.text,
                   target["comment_id"] if target["kind"] == "review_comment" else None, a.dry_run)
        if a.purpose == "ack":
            t["acked"].append(a.trigger)
        if a.purpose in ("result", "attention"):
            t["relayed"] = len(t["reports"])
            if a.purpose == "result" and last["state"] == "ready" and not t.get("pr"):
                t["status"], t["ended_reason"] = "ended", "completed"
    print(url)


def cmd_marker(a, cfg):
    print(f"{cfg['marker']}\n{cfg['banner']}\n")


def cmd_status(a, cfg):
    with store(cfg, write=False) as state:
        tickets = sorted(state["tickets"].values(), key=lambda t: int(t["id"][1:]))
    if a.json:
        print(json.dumps(tickets if a.all else [t for t in tickets if t["status"] == "open"], indent=1))
        return
    rows = []
    for t in tickets:
        if t["status"] != "open" and not a.all:
            continue
        last = t["reports"][-1] if t["reports"] else None
        if t["status"] != "open":
            stage = f"{t['status']} ({t.get('ended_reason')})"
        elif last and last.get("question"):
            stage = "person: answer"
        elif last and last["state"] in PERSON_REPORTS:
            stage = f"person: {'review' if last['state'] == 'ready' else last['state']}"
        elif running(t):
            stage = "working"
        elif t["worker_thread"] is None:
            stage = "queued"
        else:
            stage = "idle"
        pr = f" PR #{t['pr']}" if t.get("pr") else ""
        rows.append(f"{t['id']:>4}  {t['name']:<18} {stage:<20}{pr}  {t['mandate']['url']}")
    print("\n".join(rows) or "no open tickets")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("poll", help="read new GitHub triggers, gate them, print the coordinator's work list")
    s.add_argument("--dry-run", action="store_true", help="do not save state")
    s.add_argument("-v", "--verbose", action="store_true")
    s = sub.add_parser("brief", help="print the worker brief (or new inputs) and mark inputs delivered")
    s.add_argument("ticket")
    s = sub.add_parser("bind", help="record T3 task/thread facts for a ticket")
    s.add_argument("ticket")
    s.add_argument("--task")
    s.add_argument("--thread")
    s.add_argument("--watched", action="store_true")
    s.add_argument("--cancelled", action="store_true")
    s.add_argument("--failed", metavar="REASON", help="the worker died without a report")
    s = sub.add_parser("report", help="worker: record a report")
    s.add_argument("ticket")
    s.add_argument("--state", required=True, choices=["progress", *sorted(TERMINAL_REPORTS)])
    s.add_argument("--summary", required=True)
    s.add_argument("--pr", type=int)
    s.add_argument("--question", help="one concrete question for the ticket owner")
    s.add_argument("--question-trigger", help="trigger id of the message that raised the question")
    s = sub.add_parser("handback", help="worker: return a message that is beyond this ticket")
    s.add_argument("ticket")
    s.add_argument("--trigger", required=True)
    s.add_argument("--reason", required=True)
    s = sub.add_parser("accept", help="coordinator: accept a handed-back candidate as a new ticket")
    s.add_argument("trigger")
    s.add_argument("--kind", default="request", choices=["fix", "triage", "review", "request"])
    s = sub.add_parser("ignore", help="coordinator: ignore a handed-back candidate")
    s.add_argument("trigger")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("reply", help="post a marked comment on the ticket's GitHub thread")
    s.add_argument("ticket")
    s.add_argument("--purpose", required=True, choices=["ack", "result", "attention", "answer"])
    s.add_argument("--text", required=True)
    s.add_argument("--trigger", help="the message this replies to (required for ack and answer)")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("marker", help="print the header every agent-written GitHub text starts with")
    s = sub.add_parser("status", help="tickets, person-waiting first")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    globals()["cmd_" + a.cmd](a, load_config())


if __name__ == "__main__":
    main()
