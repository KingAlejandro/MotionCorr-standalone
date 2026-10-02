#!/usr/bin/env python3
"""Validate campaign-8 TIMING stage records before producing medians.

Host elapsed stage timers are not CPU utilization or pure GPU duration. This
historical campaign included the separate PR138 nvCOMP-widening experiment;
it is not current PR137 native acceptance or current-source performance.
Missing optional timers are explicit null/unavailable, never invented zero.
The legacy baseline's absent nvCOMP tag requires an explicit command-line flag.
No source/binary pin can be recovered from the stage lines alone.
"""
import argparse
import json
import math
import re
import statistics

WANT = ("read movie", "device ingest (nvCOMP)", "apply gain and initial sum")
VARIANTS = ("u16_deflate_rps1", "u16_deflate_rps8", "u16_lzw_rps1",
            "u8_deflate_rps1", "u8_deflate_rps1_48f", "u8_lzw_rps1", "u8_lzw_rps1_48f")
HDR = re.compile(r"^STAGEHDR rep=(\d+) arm=(base|cand) variant=(\S+) rc=(\d+) "
                 r"routes=\[\s*(\d+)\s+(nvcomp|compact|float)\s*\]\s*$")
LINE = re.compile(r"^STAGE rep=(\d+) arm=(base|cand) variant=(\S+) "
                  r"(.+?)\s*:\s*([-+\d.eE]+) sec\s*$")


def summarize(text, variants, expected_reps, legacy_base_untagged=False):
    if expected_reps <= 0 or not variants or len(set(variants)) != len(variants):
        raise ValueError("positive repetitions and unique declared variants required")
    runs = {}
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("STAGEHDR"):
            m = HDR.fullmatch(line)
            if not m:
                raise ValueError(f"line {number}: malformed/mixed route header")
            rep, arm, var, rc, movies, route = m.groups()
            key = (var, arm, int(rep))
            if var not in variants or not 1 <= int(rep) <= expected_reps:
                raise ValueError(f"line {number}: undeclared variant/repetition")
            if int(rc) != 0 or int(movies) <= 0:
                raise ValueError(f"line {number}: unsuccessful/empty run")
            if key in runs:
                raise ValueError(f"line {number}: duplicate run header")
            runs[key] = {"route": route, "movies": int(movies), "stages": {}}
        elif line.startswith("STAGE"):
            m = LINE.fullmatch(line)
            if not m:
                raise ValueError(f"line {number}: malformed stage")
            rep, arm, var, stage, value = m.groups()
            key = (var, arm, int(rep))
            if key not in runs:
                raise ValueError(f"line {number}: stage without successful run header")
            if stage not in WANT:
                continue  # other application timers are outside this breakdown
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"line {number}: invalid elapsed time")
            if stage in runs[key]["stages"]:
                raise ValueError(f"line {number}: duplicate stage")
            runs[key]["stages"][stage] = value
    required_keys = {(v, a, r) for v in variants for a in ("base", "cand")
                     for r in range(1, expected_reps + 1)}
    if set(runs) != required_keys:
        raise ValueError("incomplete declared run/arm/repetition inventory")
    out = {}
    for var in variants:
        out[var] = {}
        for arm in ("base", "cand"):
            records = [runs[(var, arm, rep)] for rep in range(1, expected_reps + 1)]
            route = records[0]["route"]
            if any(r["route"] != route or r["movies"] != records[0]["movies"] for r in records):
                raise ValueError(f"{var}/{arm}: route/movie inventory changed between repetitions")
            required = set(WANT[::2]) if route != "nvcomp" else {WANT[1]}
            legacy = legacy_base_untagged and arm == "base" and route == "nvcomp"
            if legacy:
                required.remove(WANT[1])
            for r in records:
                if not required <= r["stages"].keys() or not r["stages"]:
                    raise ValueError(f"{var}/{arm}: missing required stage")
            rec = {"route": route, "reps": expected_reps, "movies": records[0]["movies"]}
            unavailable = {}
            for stage in WANT:
                present = [stage in r["stages"] for r in records]
                if any(present) and not all(present):
                    raise ValueError(f"{var}/{arm}: incomplete optional stage {stage}")
                rec[stage] = round(statistics.median(r["stages"][stage] for r in records), 3) if all(present) else None
                if not all(present):
                    unavailable[stage] = "explicit legacy baseline tag absent" if legacy and stage == WANT[1] else "timer absent; duration not established"
            rec["unavailable"] = unavailable
            out[var][arm] = rec
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--expected-reps", type=int, default=3)
    ap.add_argument("--legacy-base-untagged-ingest", action="store_true")
    a = ap.parse_args()
    try:
        with open(a.log, encoding="utf-8", errors="strict") as f:
            result = summarize(f.read(), a.variants.split(","), a.expected_reps,
                               a.legacy_base_untagged_ingest)
    except (OSError, ValueError) as e:
        ap.exit(1, f"host_stages: {e}\n")
    print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
