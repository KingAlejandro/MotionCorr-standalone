"""Tests for the superagent gate and ledger. Run: python3 -m unittest agents/superagent/test_sa.py"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sa  # noqa: E402

CFG = {
    "repository": "o/r", "allowed_logins": ["alex"], "trigger_prefix": "/agent",
    "labels": {"agent:fix": "fix", "agent:triage": "triage", "agent:review": "review"},
    "marker": "<!-- motioncorr-superagent -->", "banner": "_bot_", "reply_word_limit": 100,
    "max_running": 1, "stale_assignment_hours": 6, "branch_prefix": "agent/", "state_dir": "",
}
_n = iter(range(1, 10_000))


def comment(actor="alex", body="hi", number=7, bot=False, kind="comment"):
    i = next(_n)
    return {"id": f"ic:{i}", "kind": kind, "number": number, "is_pr": False, "actor": actor, "bot": bot,
            "body": body, "label": None, "url": f"https://x/{number}#{i}", "created_at": "2026-11-05T00:00:00Z",
            "comment_id": i}


def label(name="agent:fix", actor="alex", number=7, removed=False):
    t = comment(actor=actor, number=number, body="")
    t.update(kind="unlabeled" if removed else "labeled", label=name, id=f"ev:{next(_n)}")
    return t


class Gate(unittest.TestCase):
    def setUp(self):
        self.state = sa.empty_state()

    def run_(self, trig, cfg=CFG):
        return sa.process(trig, self.state, cfg)

    def ticket(self, tid="T1"):
        return self.state["tickets"][tid]

    def test_own_marked_message_is_dropped(self):
        d = self.run_(comment(body=CFG["marker"] + "\n/agent do it"))
        self.assertEqual(d["action"], "drop")
        self.assertEqual(self.state["tickets"], {})

    def test_request_needs_allowed_sender_and_prefix(self):
        self.assertEqual(self.run_(comment(actor="mallory", body="/agent fix it"))["action"], "ignore")
        self.assertEqual(self.run_(comment(body="please fix it"))["action"], "ignore")
        self.assertEqual(self.run_(comment(body="/agentfoo"))["action"], "ignore")
        self.assertEqual(self.run_(comment(actor="x[bot]", bot=True, body="/agent fix"))["action"], "ignore")
        self.assertEqual(self.state["tickets"], {})
        d = self.run_(comment(body="/agent fix the STAR writer"))
        self.assertEqual(d["action"], "accept")
        self.assertEqual(self.ticket()["kind"], "request")
        self.assertEqual(self.ticket()["mandate"]["actor"], "alex")

    def test_label_accepts_dedupes_and_unlabel_stops(self):
        self.assertEqual(self.run_(label(actor="mallory"))["action"], "ignore")
        self.assertEqual(self.run_(label("bug"))["action"], "ignore")
        self.assertEqual(self.run_(label())["action"], "accept")
        self.assertEqual(self.ticket()["branch"], "agent/fix-7")
        self.assertEqual(self.run_(label())["action"], "ignore")  # duplicate
        self.assertEqual(self.run_(label("agent:triage"))["action"], "accept")  # other kind is separate work
        self.assertEqual(self.run_(label(removed=True))["action"], "stop")
        self.assertEqual(self.ticket("T1")["status"], "stopped")
        self.assertEqual(self.ticket("T2")["status"], "open")

    def test_follow_ups_reach_open_ticket_from_anyone(self):
        self.run_(label())
        self.assertEqual(self.run_(comment(actor="colleague", body="also check X"))["action"], "deliver")
        self.assertEqual(self.run_(comment(actor="ci[bot]", bot=True, body="red"))["action"], "deliver")
        self.assertEqual(len(self.ticket()["inbox"]), 2)
        # an unlisted person's /agent is still not a request
        self.assertEqual(self.run_(comment(actor="colleague", body="/agent do Y"))["action"], "ignore")

    def test_ended_ticket_resumes_on_person_not_bot_and_revalidates(self):
        self.run_(label())
        self.ticket()["status"] = "ended"
        self.assertEqual(self.run_(comment(actor="ci[bot]", bot=True))["action"], "ignore")
        self.assertEqual(self.ticket()["status"], "ended")
        self.assertEqual(self.run_(comment(actor="colleague", body="this regressed"))["action"], "resume")
        self.assertEqual(self.ticket()["status"], "open")
        self.ticket()["status"] = "ended"
        narrowed = dict(CFG, allowed_logins=["someone-else"])
        self.assertEqual(self.run_(comment(actor="colleague"), narrowed)["action"], "ignore")
        self.assertEqual(self.ticket()["status"], "ended")

    def test_stop_withdraws_live_and_ended_and_blocks_delivery(self):
        self.run_(label())
        self.run_(label("agent:triage"))
        self.ticket("T2")["status"] = "ended"
        self.ticket("T1")["assignment"] = {"state": "running", "started": sa.now_iso()}
        self.assertEqual(self.run_(comment(actor="mallory", body="/agent stop"))["action"], "ignore")
        d = self.run_(comment(body="/agent stop"))
        self.assertEqual(sorted(d["tickets"]), ["T1", "T2"])
        self.assertTrue(self.ticket("T1")["needs_cancel"])
        self.assertEqual(self.run_(comment(actor="colleague", body="hello?"))["action"], "ignore")

    def test_watched_pr_comments_are_left_to_t3(self):
        self.run_(label())
        self.ticket().update(pr=9, watched=True)
        self.assertEqual(self.run_(comment(number=9, kind="review_comment"))["action"], "drop")
        self.assertEqual(self.run_(comment(number=7))["action"], "deliver")  # the issue thread is not watched

    def test_trigger_is_processed_once(self):
        t = label()
        self.assertIsNotNone(self.run_(t))
        self.assertIsNone(self.run_(t))
        self.assertEqual(len(self.state["tickets"]), 1)

    def test_work_list_respects_slots_but_not_for_deliveries(self):
        self.run_(label(number=1))
        self.run_(label(number=2))
        w = sa.work_list(self.state, CFG)
        self.assertEqual([x["ticket"] for x in w["dispatch"]], ["T1"])  # max_running = 1
        self.ticket("T1").update(worker_thread="th1", assignment={"state": "running", "started": sa.now_iso()})
        self.run_(comment(number=1, body="more"))
        w = sa.work_list(self.state, CFG)
        self.assertEqual(w["dispatch"], [])
        self.assertEqual([x["ticket"] for x in w["deliver"]], ["T1"])


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "config.json"
        self.cfg_path.write_text(sa.json.dumps(dict(CFG, state_dir=self.tmp.name)))
        os.environ["SUPERAGENT_CONFIG"] = str(self.cfg_path)
        os.environ.pop("SUPERAGENT_STATE_DIR", None)
        cfg = sa.load_config()
        with sa.store(cfg) as state:
            sa.process(label(), state, cfg)
            state["candidates"].append({"trigger": comment(actor="colleague", body="/agent x"), "from": "T1",
                                        "reason": "r", "at": sa.now_iso()})

    def tearDown(self):
        os.environ.pop("SUPERAGENT_CONFIG", None)
        self.tmp.cleanup()

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                sa.main(list(argv))
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue() + err.getvalue()

    def test_fix_is_not_ready_without_pr(self):
        code, msg = self.cli("report", "T1", "--state", "ready", "--summary", "done")
        self.assertEqual(code, 2, msg)
        self.assertEqual(self.cli("report", "T1", "--state", "ready", "--summary", "done", "--pr", "5")[0], 0)

    def test_reply_limits_and_purposes(self):
        code, msg = self.cli("reply", "T1", "--purpose", "attention", "--text", "q?", "--dry-run")
        self.assertEqual(code, 2, msg)
        code, msg = self.cli("reply", "T1", "--purpose", "result", "--text", " ".join(["w"] * 101), "--dry-run")
        self.assertEqual(code, 2, msg)
        code, msg = self.cli("reply", "T1", "--purpose", "ack", "--text", "On it.", "--dry-run")
        self.assertEqual(code, 2, msg)  # ack needs the message it replies to
        self.cli("report", "T1", "--state", "blocked", "--summary", "s", "--question", "Which gate?")
        code, msg = self.cli("reply", "T1", "--purpose", "attention", "--text", "Which gate?", "--dry-run")
        self.assertEqual(code, 0, msg)
        self.assertIn(CFG["marker"], msg)
        self.assertIn("issues/7/comments", msg)

    def test_handed_back_unlisted_message_cannot_be_accepted(self):
        cfg = sa.load_config()
        with sa.store(cfg, write=False) as state:
            tid = state["candidates"][0]["trigger"]["id"]
        code, msg = self.cli("accept", tid)
        self.assertEqual(code, 2, msg)
        self.assertEqual(self.cli("ignore", tid, "--reason", "not a request")[0], 0)


if __name__ == "__main__":
    unittest.main()
