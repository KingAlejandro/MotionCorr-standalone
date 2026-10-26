#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Post-run checks for the Stage A/B correctness window. No input is modified.

  stageAB_check.py unittest LOG REQUIRED_OK...   counts, skips, and requires each named test 'ok'
  stageAB_check.py oracle JSON STDOUT            gates G1-G6 and per-path eligible frames
  stageAB_check.py witness SAMPLER OPID UUID     was the oracle PID seen holding a context on the granted GPU only
"""
import json, re, sys


def unittest_log(path, required):
    text = open(path, errors="replace").read()
    res = dict(re.findall(r"^(test_\w+) \(.*?\) \.\.\. (\S+)", text, re.M))
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    skipped = re.findall(r"skipped=(\d+)", text)
    final = "OK" if re.search(r"^OK", text, re.M) else ("FAILED" if "FAILED" in text else "UNKNOWN")
    bad = [t for t in required if res.get(t) != "ok"]
    print(f"ran={ran.group(1) if ran else '?'} final={final} skipped_total={skipped[0] if skipped else 0} "
          f"ok={sum(v == 'ok' for v in res.values())} not_ok={[k for k, v in res.items() if v != 'ok']}")
    print("required_not_ok=" + json.dumps(bad))
    return 0 if final == "OK" and not bad else 1


def oracle(jpath, spath):
    d = json.load(open(jpath))
    rows = d["rows"]
    ok = True
    for p in ("cpu_global", "cpu_local", "cuda_single_global", "cuda_single_local", "cuda_batched_local"):
        r = [x for x in rows if x["path"] == p]
        e = sum(x["eligible"] for x in r)
        z = sum(x["zeroed"] for x in r)
        print(f"{p}: rows={len(r)} eligible_frames={e} zeroed_frames={z}")
        ok &= len(r) > 0 and e > 0
    print("gates=" + json.dumps(d["gates"]) + f" failures={d['failures']}")
    passed = "ORACLE PASSED" in open(spath, errors="replace").read()
    print("ORACLE_PASSED_LINE=" + str(passed))
    print("ALL_PATHS_STRICTLY_POSITIVE" if ok else "PATH_NOT_REACHED")
    gates_ok = d["failures"] == 0 and all(v["fail"] == 0 and v["inconclusive"] == 0 and v["pass"] > 0 for v in d["gates"].values())
    print("GATES_ALL_PASS_NONEMPTY=" + str(gates_ok))
    return 0 if ok and passed and gates_ok else 1


def witness(sampler, opid, uuid):
    seen_on, lines, other_compute = {}, 0, set()
    for line in open(sampler, errors="replace"):
        parts = line.rstrip("\n").split("|")
        if len(parts) < 3:
            continue
        lines += 1
        for app in filter(None, parts[2].split(";")):
            f = [x.strip() for x in app.split(",")]
            if len(f) < 3:
                continue
            if f[0] == str(opid):
                seen_on.setdefault(f[1], 0)
                seen_on[f[1]] += 1
            else:
                other_compute.add((f[0], f[1]))
    print(f"samples={lines} oracle_pid={opid} seen_on={seen_on} other_compute_apps_seen={sorted(other_compute)}")
    verdict = "WITNESSED" if seen_on.get(uuid, 0) > 0 and set(seen_on) == {uuid} else "INCONCLUSIVE"
    print(verdict)
    return 0 if verdict == "WITNESSED" else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "unittest":
        sys.exit(unittest_log(sys.argv[2], sys.argv[3:]))
    if mode == "oracle":
        sys.exit(oracle(sys.argv[2], sys.argv[3]))
    if mode == "witness":
        sys.exit(witness(sys.argv[2], sys.argv[3], sys.argv[4]))
    sys.exit(2)
