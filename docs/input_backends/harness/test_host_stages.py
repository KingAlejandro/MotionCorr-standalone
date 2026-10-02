#!/usr/bin/env python3
"""Powered CLI controls for the historical host-stage parser; no hardware."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def fixture(route="compact"):
    lines = []
    for rep in (1, 2, 3):
        for arm in ("base", "cand"):
            lines.append(f"STAGEHDR rep={rep} arm={arm} variant=u8_lzw_rps1 rc=0 routes=[ 6 {route} ]")
            stages = (("read movie", rep * .1), ("apply gain and initial sum", rep * .2)) if route != "nvcomp" else (("device ingest (nvCOMP)", rep * .3),)
            for name, value in stages:
                lines.append(f"STAGE rep={rep} arm={arm} variant=u8_lzw_rps1 {name} : {value:.3f} sec")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--predecessor", type=Path)
    a = ap.parse_args()
    parser = Path(__file__).with_name("host_stages.py")
    results = []
    with tempfile.TemporaryDirectory(prefix="host-stages-controls-") as temp:
        temp = Path(temp)
        def run(name, text, extra=(), old=False):
            log = temp / (name + ".log")
            log.write_text(text)
            cmd = [sys.executable, str(a.predecessor if old else parser), str(log)]
            if not old: cmd += ["--variants", "u8_lzw_rps1", *extra]
            return subprocess.run(cmd, text=True, capture_output=True)
        healthy = fixture()
        r = run("healthy", healthy)
        if r.returncode: raise RuntimeError(r.stderr)
        data = json.loads(r.stdout)["u8_lzw_rps1"]
        for arm in ("base", "cand"):
            if (data[arm]["reps"] != 3 or data[arm]["read movie"] != .2
                    or data[arm]["apply gain and initial sum"] != .4
                    or data[arm]["device ingest (nvCOMP)"] is not None
                    or not data[arm]["unavailable"]):
                raise RuntimeError("positive median/unavailable oracle")
        results.append("healthy medians and explicit unavailable: PASS")
        negatives = {
            "failed-rc": healthy.replace("rc=0", "rc=1", 1),
            "missing-header": "\n".join(healthy.splitlines()[1:]),
            "missing-required-stage": healthy.replace("STAGE rep=1 arm=base variant=u8_lzw_rps1 read movie : 0.100 sec\n", ""),
            "duplicate-stage": healthy + "STAGE rep=3 arm=cand variant=u8_lzw_rps1 read movie : 0.300 sec\n",
            "duplicate-header": healthy + "STAGEHDR rep=3 arm=cand variant=u8_lzw_rps1 rc=0 routes=[ 6 compact ]\n",
            "missing-repetition": "\n".join(x for x in healthy.splitlines() if "rep=3" not in x),
            "missing-arm": "\n".join(x for x in healthy.splitlines() if "arm=cand" not in x),
            "mixed-route": healthy.replace("6 compact", "3 compact 3 float", 1),
            "changed-route": healthy.replace("6 compact", "6 float", 1),
            "unknown-variant": healthy.replace("u8_lzw_rps1", "unlisted"),
            "negative-time": healthy.replace("0.100 sec", "-0.100 sec", 1),
            "nonfinite-time": healthy.replace("0.100 sec", "1e999 sec", 1),
            "incomplete-optional": healthy + "STAGE rep=3 arm=cand variant=u8_lzw_rps1 device ingest (nvCOMP) : 0.001 sec\n",
        }
        for name, text in negatives.items():
            r = run(name, text)
            if r.returncode == 0 or r.stdout or not r.stderr.startswith("host_stages:"):
                raise RuntimeError(name + ": rejection failed or unrelated error")
            results.append(name + ": PASS (named rejection)")
        gpu = fixture("nvcomp")
        missing_tag = "\n".join(x for x in gpu.splitlines() if not (x.startswith("STAGE ") and "arm=base" in x))
        # Legacy source still emitted another timer; only the documented absent
        # device-ingest tag is allowed, not an entirely missing timing report.
        for rep in (1, 2, 3):
            missing_tag += f"\nSTAGE rep={rep} arm=base variant=u8_lzw_rps1 apply gain and initial sum : 0.000 sec"
        r = run("legacy-not-opted-in", missing_tag)
        if r.returncode == 0: raise RuntimeError("legacy absence silently accepted")
        r = run("legacy-explicit", missing_tag, ["--legacy-base-untagged-ingest"])
        if r.returncode or json.loads(r.stdout)["u8_lzw_rps1"]["base"]["device ingest (nvCOMP)"] is not None:
            raise RuntimeError("explicit legacy tag unavailable control")
        results.append("legacy absence rejected unless explicit, then null: PASS")
        if a.predecessor:
            for name in ("failed-rc", "missing-required-stage", "duplicate-stage", "missing-repetition", "missing-arm"):
                old = run("old-" + name, negatives[name], old=True)
                if old.returncode != 0 or not old.stdout.strip():
                    raise RuntimeError("predecessor did not accept powered invalid case: " + name)
                results.append("predecessor accepts " + name + ": DISCRIMINATING")
    # The corrected renderer reads the retained payload without replacing its
    # original chart or promoting these historical measurements to PR137.
    with tempfile.TemporaryDirectory(prefix="host-stage-chart-controls-") as temp:
        temp = Path(temp)
        here = Path(__file__).resolve().parent
        retained = json.loads((here.parent / "data/host_stages.json").read_text())
        data = temp / "data"; data.mkdir()
        out = temp / "out"; out.mkdir()
        def chart(payload):
            (data / "host_stages.json").write_text(json.dumps(payload))
            return subprocess.run([sys.executable, str(here / "build_host_chart.py"),
                                   str(data), str(out)], text=True, capture_output=True)
        if chart(retained).returncode:
            raise RuntimeError("retained chart positive failed")
        svg = (out / "host-stages-scoped.svg").read_text()
        if ("historical stacked #138" not in svg or "UNRECORDED" not in svg
                or "not current #137 acceptance" not in svg or ">unavailable<" not in svg):
            raise RuntimeError("chart attribution/unavailable oracle")
        results.append("retained chart scoped attribution/unavailable: PASS")
        partial = dict(retained); partial.pop(next(iter(partial)))
        if chart(partial).returncode == 0:
            raise RuntimeError("partial chart inventory accepted")
        bad_reps = json.loads(json.dumps(retained))
        bad_reps["u8_lzw_rps1"]["cand"]["reps"] = 2
        if chart(bad_reps).returncode == 0:
            raise RuntimeError("chart rep-count claim not enforced")
        results.append("partial chart inventory and wrong repetition count rejected: PASS")
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
