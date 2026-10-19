#!/usr/bin/env python3
"""SUPPLEMENTARY (not a QF item): #204 case m0_swapped_nx128_inherited on F's binaries.
Arms: CUDA+nvCOMP --ingest float/auto/compact and the CPU build, each on the big-endian input and on the
same pixels written little-endian. Checks: rc 0, routes, products-only identity (lib.identity) across the
CUDA routes, and big-endian == little-endian on each arm (the swap decodes to the same pixels).
Every run goes through tools/qf_lane_exec.sh (lane lock, bench probe, UUID pin, CPU mask)."""
import json
import os
import sys
from pathlib import Path

W = Path(os.environ["QF_W"])
sys.path.insert(0, str(W / "tools" / "harness_mrc"))
import synth_mrc_matrix as h  # noqa: E402

lane = W / "tools" / "qf_lane_exec.sh"
work = W / "supp-m0-nx128"
case = [c for c in h.cases() if c["name"] == "m0_swapped_nx128_inherited"][0]
res = {"case": case, "arms": {}, "compare": {}}
arms = {}
for endian in ("big", "little"):
    c = dict(case, big=(endian == "big"))
    writer, _ = h.make_writer(c)
    for ingest in ("float", "auto", "compact", "cpu"):
        cpu = ingest == "cpu"
        os.environ["MC_BIN"] = str(W / ("build-cpu" if cpu else "build-nvcomp") / "motioncorr")
        os.environ["QF_LANE_CPU_ONLY"] = "1" if cpu else "0"
        a = h.run_motioncorr(lane, work, f"{endian}-{ingest}", "movie.mrcs", writer,
                             None if cpu else ingest, 0, cpu, expected_frames=c["nz"])
        arms[(endian, ingest)] = a
        res["arms"][f"{endian}-{ingest}"] = h.brief(a)
for e in ("big", "little"):
    for r in ("auto", "compact"):
        res["compare"][f"{e}: float vs {r}"] = h.compare(arms[(e, "float")], arms[(e, r)])
for r in ("float", "auto", "compact", "cpu"):
    res["compare"][f"{r}: big vs little"] = h.compare(arms[("big", r)], arms[("little", r)])
ok = all(a["rc"] == 0 and a["mrc_products"] and a["completion_star"] for a in arms.values())
ok = ok and all(v["identical"] for v in res["compare"].values())
ok = ok and arms[("big", "float")]["witness"] == ["float"] and arms[("big", "compact")]["witness"] == ["compact"]
res["all_hold"] = ok
(W / "supp-m0-nx128.json").write_text(json.dumps(res, indent=1))
for k, v in res["compare"].items():
    print(k, v["identical"], "mrc_compared=", v["mrc_compared"], v["problems"][:2])
print({k: (v["rc"], v["witness"]) for k, v in res["arms"].items()})
print("ALL_HOLD" if ok else "NOT_ALL_HOLD")
