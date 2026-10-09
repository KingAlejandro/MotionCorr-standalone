"""Derive and render kit results (Markdown, JSON, optional self-contained HTML).

Each report section carries exactly one instrument, named in its first line.
Numbers are never added or subtracted across sections: the unprofiled wall,
the --profile stage times, the Nsight device times and the Nsight Compute
counters each describe a differently perturbed process.
"""
from __future__ import annotations

import html
import importlib.util
import json
import os
import re
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional, Sequence

from . import stats

INSTR_RUN = "mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling"
INSTR_IDENTITY = "lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1"
INSTR_PROFILE = "--profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults"
INSTR_NSYS = "Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated"
INSTR_NCU = "Nsight Compute: replayed kernels, counters only; durations are not timings"

REPO_TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _stage_profile_module():
    spec = importlib.util.spec_from_file_location("stage_profile", os.path.join(REPO_TOOLS, "stage_profile.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------- formatting

def ms(ns) -> str:
    return "%.2f" % (ns / 1e6)


def mib(b) -> str:
    return "-" if b is None else "%.0f" % (b / 1048576.0)


def s3(x) -> str:
    return "-" if x is None else "%.3f" % x


def table(header: Sequence[str], rows: Sequence[Sequence]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def section(title: str, instrument: str, body: str) -> str:
    return "## %s\n\nInstrument: %s.\n\n%s\n" % (title, instrument, body.strip())


# ----------------------------------------------------------------- loading

def load_runs(path: str) -> List[Dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


# ----------------------------------------------------------------- run / compare derivation

def arm_summary(runs: Sequence[Dict]) -> Dict:
    keep = [r for r in runs if r["kind"] == "round" and not r.get("discarded")]
    if not keep:
        return {"n": 0}
    def col(f):
        return [f(r) for r in keep if f(r) is not None]
    wall = col(lambda r: r["wall_s"])
    out = {"n": len(keep), "wall_median_s": stats.median(wall), "wall_iqr_s": stats.iqr(wall),
           "wall_min_s": min(wall), "wall_max_s": max(wall),
           "cpu_median_s": stats.median(col(lambda r: r["cpu_s"])),
           "rss_median_bytes": stats.median(col(lambda r: r["peak_rss_bytes"])),
           "minflt_median": stats.median(col(lambda r: r["minflt"])),
           "majflt_max": max(col(lambda r: r["majflt"])),
           "wall_outlier_rounds": [keep[i]["round"] for i in stats.outliers(wall)]}
    for k in ("peak_process_bytes", "peak_device_delta_bytes"):
        v = col(lambda r: (r.get("vram") or {}).get(k))
        out["vram_" + k] = stats.median(v) if v else None
        out["vram_" + k + "_max"] = max(v) if v else None
    lane = col(lambda r: (r.get("lane") or {}).get("foreign_cores"))
    out["lane_foreign_cores_max"] = max(lane) if lane else None
    load = col(lambda r: r.get("load1_before"))
    out["load1_range"] = [min(load), max(load)] if load else None
    return out


def mark_discards(runs: List[Dict], arms: Sequence[str]) -> List[Dict]:
    """A round is discarded when any of its runs carries a discard flag."""
    bad = defaultdict(list)
    for r in runs:
        if r["kind"] == "round" and r["flags"]["discard"]:
            bad[r["round"]].append("%s: %s" % (r["arm"], "; ".join(r["flags"]["discard"])))
    for r in runs:
        r["discarded"] = r["kind"] == "round" and r["round"] in bad
    return [{"round": k, "reasons": v} for k, v in sorted(bad.items())]


def pairs_for(runs: Sequence[Dict], base: str, arm: str) -> List[Dict]:
    by = defaultdict(dict)
    for r in runs:
        if r["kind"] == "round" and not r.get("discarded"):
            by[r["round"]][r["arm"]] = r
    out = []
    for rnd in sorted(by):
        g = by[rnd]
        if base in g and arm in g:
            order = "AB" if g[base]["position"] < g[arm]["position"] else "BA"
            out.append({"round": rnd, "a": g[base]["wall_s"], "b": g[arm]["wall_s"], "order": order})
    return out


def derive_runs(raw: Dict, floor_s: float = 0.0) -> Dict:
    runs, arms = raw["runs"], raw["arms"]
    discards = mark_discards(runs, arms)
    out = {"arms": arms, "summary": {a: arm_summary([r for r in runs if r["arm"] == a]) for a in arms},
           "discarded_rounds": discards, "comparisons": OrderedDict()}
    for a in arms[1:]:
        out["comparisons"][a] = stats.paired(pairs_for(runs, arms[0], a), floor_s=floor_s)
    return out


def derive_stage_deltas(profiles: Dict[str, str], base: str) -> Optional[Dict]:
    """Per-stage deltas from one --profile pass per arm; steady movies as samples."""
    if not profiles or base not in profiles:
        return None
    sp = _stage_profile_module()
    data = {}
    for arm, path in profiles.items():
        movies, process = sp.load(path)
        steady = movies[1:] if len(movies) > 1 else movies
        per: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        names = []
        for m in steady:
            seen = {st["name"]: st for st in m["stages"]}
            for n in seen:
                if n not in names:
                    names.append(n)
        for m in steady:
            seen = {st["name"]: st for st in m["stages"]}
            for n in names:
                st = seen.get(n, {})
                for k in ("wall_ms", "cpu_ms", "minflt"):
                    per[n][k].append(st.get(k, 0))
        data[arm] = {"stages": per, "order": names, "check": sp.check(movies), "process": process,
                     "movies": len(movies), "movie_wall_ms": [m["wall_ms"] for m in steady]}
    out = {"arms": {}, "base": base}
    for arm in profiles:
        if arm == base:
            continue
        rows = OrderedDict()
        names = data[base]["order"] + [n for n in data[arm]["order"] if n not in data[base]["order"]]
        for n in names:
            row = {}
            for k, min_abs in (("wall_ms", 0.5), ("cpu_ms", 0.5), ("minflt", 50)):
                a = data[base]["stages"].get(n, {}).get(k, [])
                b = data[arm]["stages"].get(n, {}).get(k, [])
                row[k] = stats.per_sample_delta(a, b, min_abs=min_abs)
            rows[n] = row
        out["arms"][arm] = {"stages": rows,
                            "movie_wall": stats.per_sample_delta(data[base]["movie_wall_ms"],
                                                                 data[arm]["movie_wall_ms"], min_abs=0.5)}
    out["checks"] = {a: d["check"] for a, d in data.items()}
    out["processes"] = {a: d["process"] for a, d in data.items()}
    return out


DEVICE_KEYS = (("wall_ns", 0.5e6), ("busy_ns", 0.5e6), ("idle_ns", 0.5e6), ("kernels", 1), ("copy_bytes", 1),
               ("sync_calls", 1), ("sync_blocked_idle_ns", 0.5e6), ("malloc", 1), ("free", 1))


def derive_device_deltas(traces: Dict[str, Dict], base: str) -> Optional[Dict]:
    if not traces or base not in traces:
        return None
    out = {"base": base, "arms": {}}
    for arm, t in traces.items():
        if arm == base:
            continue
        rows = OrderedDict()
        sa, sb = traces[base]["stages"], t["stages"]
        for n in list(sa) + [x for x in sb if x not in sa]:
            ra, rb = sa.get(n), sb.get(n)
            kind = (ra or rb)["kind"]
            row = {"kind": kind}
            for k, min_abs in DEVICE_KEYS:
                if kind in ("stage", "unattributed"):
                    a = ra[k]["per_movie"][1:] if ra and k in ra else []
                    b = rb[k]["per_movie"][1:] if rb and k in rb else []
                    row[k] = stats.per_sample_delta(a, b, min_abs=min_abs)
                else:
                    a = ra[k]["sum"] if ra and k in ra else 0
                    b = rb[k]["sum"] if rb and k in rb else 0
                    row[k] = {"median_a": a, "median_b": b, "delta": b - a, "flag": False, "single": True}
            rows[n] = row
        ma, mb = traces[base].get("memory"), t.get("memory")
        mem = None
        if ma and mb:
            pa = max((d["peak_bytes"] for d in ma["devices"].values()), default=0)
            pb = max((d["peak_bytes"] for d in mb["devices"].values()), default=0)
            mem = {"peak_a": pa, "peak_b": pb, "delta": pb - pa}
        out["arms"][arm] = {"stages": rows, "memory": mem,
                            "totals": {k: (traces[base]["totals"][k], t["totals"][k])
                                       for k in ("busy_ns", "idle_ns", "kernels", "copies", "copy_bytes")}}
    return out


# ----------------------------------------------------------------- rendering

def render_provenance(prov: Dict) -> str:
    lines = ["## Provenance", ""]
    host = prov.get("host", {})
    gpu = prov.get("gpu") or {}
    kit = prov.get("kit", {})
    lines.append("- kit: `%s`%s" % (kit.get("commit"), " (dirty)" if kit.get("dirty") else ""))
    for name, b in prov.get("binaries", {}).items():
        src = b.get("source", {})
        lines.append("- arm `%s`: `%s` sha256 `%s`; source `%s`%s (%s); --profile %s" % (
            name, b["path"], b["sha256"][:16], src.get("commit"), " dirty" if src.get("dirty") else "",
            src.get("origin"), "present" if b.get("has_profile_option") else "absent"))
        if b.get("linked"):
            lines.append("  - linked: " + ", ".join("%s=%s" % kv for kv in sorted(b["linked"].items())))
    lines.append("- host: %s, %s, %s CPUs, lane %s, load1 %s, clocksource %s, THP %s" % (
        host.get("hostname"), host.get("cpu_model"), host.get("cpu_count"),
        _cpus(host.get("lane_cpus")), "%.1f" % host["load1_5_15"][0] if host.get("load1_5_15") else "-",
        host.get("clocksource"), host.get("thp_enabled")))
    if gpu:
        lines.append("- GPU: %s %s (index %s), driver %s, CUDA %s, persistence %s" % (
            gpu.get("name"), gpu.get("uuid"), gpu.get("index"), gpu.get("driver_version"),
            gpu.get("driver_cuda_version"), gpu.get("persistence_mode")))
    if prov.get("locks"):
        lines.append("- locks: " + ", ".join("%s (waited %.0f s)" % (l["path"], l["waited_s"]) for l in prov["locks"]))
    if prov.get("settle"):
        lines.append("- settle: %s" % json.dumps(prov["settle"]))
    if prov.get("input"):
        i = prov["input"]
        lines.append("- input: `%s` in `%s`, %d movies, STAR sha256 `%s`" % (
            i["star"], i["cwd"], len(i["movies"]), i["star_sha256"][:16]))
    if prov.get("payload_args") is not None:
        lines.append("- payload options: `%s`" % " ".join(prov["payload_args"]))
    if prov.get("payload_env"):
        lines.append("- payload env: `%s`" % " ".join("%s=%s" % kv for kv in prov["payload_env"].items()))
    lines.append("- command: `%s`" % " ".join(prov.get("command", [])))
    return "\n".join(lines) + "\n"


def _cpus(c) -> str:
    if not c:
        return "-"
    return "%d-%d" % (c[0], c[-1]) if c == list(range(c[0], c[-1] + 1)) else ",".join(map(str, c))


def render_run_section(d: Dict) -> str:
    rows = []
    for a in d["arms"]:
        s = d["summary"][a]
        if not s.get("n"):
            rows.append([a, 0] + ["-"] * 9)
            continue
        rows.append([a, s["n"], s3(s["wall_median_s"]), s3(s["wall_iqr_s"]),
                     "%s-%s" % (s3(s["wall_min_s"]), s3(s["wall_max_s"])), s3(s["cpu_median_s"]),
                     mib(s["rss_median_bytes"]), "%.0f" % s["minflt_median"], s["majflt_max"],
                     mib(s["vram_peak_process_bytes"]), mib(s["vram_peak_device_delta_bytes"])])
    body = table(["arm", "runs", "wall med s", "wall IQR s", "wall range s", "CPU med s", "peak RSS MiB",
                  "minflt med", "majflt max", "VRAM proc MiB", "VRAM dev delta MiB"], rows)
    body += ("\n\nVRAM columns are sampled peaks and therefore lower bounds. \"proc\" is NVML's per-process "
             "used memory (includes the CUDA context); \"dev delta\" is device used memory minus the idle "
             "baseline taken just before the run.")
    extra = []
    for a in d["arms"]:
        s = d["summary"][a]
        if s.get("n"):
            extra.append("- `%s`: load1 %s, max foreign CPU on lane %s cores, wall outlier rounds %s" % (
                a, "%.1f-%.1f" % tuple(s["load1_range"]) if s.get("load1_range") else "-",
                "%.2f" % s["lane_foreign_cores_max"] if s.get("lane_foreign_cores_max") is not None else "-",
                s["wall_outlier_rounds"] or "none"))
    if extra:
        body += "\n\n" + "\n".join(extra)
    if d["discarded_rounds"]:
        body += "\n\nDiscarded rounds:\n" + "\n".join(
            "- round %d: %s" % (x["round"], " | ".join(x["reasons"])) for x in d["discarded_rounds"])
    for a, c in d["comparisons"].items():
        body += "\n\n" + render_verdict(d["arms"][0], a, c)
    return section("Unprofiled wall and resources", INSTR_RUN, body)


def render_verdict(base: str, arm: str, c: Dict) -> str:
    lines = ["### `%s` vs `%s`: **%s**" % (arm, base, c["verdict"]), ""]
    if c["n_pairs"]:
        ci = c.get("ci")
        lines.append(table(["pairs", "median B-A s", "IQR s", "range s", "CI of median s", "noise s",
                            "sign test", "relative"],
                           [[c["n_pairs"], "%+.3f" % c["median_diff_s"],
                             "%+.3f..%+.3f" % (c["q1_diff_s"], c["q3_diff_s"]),
                             "%+.3f..%+.3f" % (c["min_diff_s"], c["max_diff_s"]),
                             ("%+.3f..%+.3f (%.1f%%)" % (ci["low_s"], ci["high_s"], 100 * ci["confidence"])) if ci else "n/a",
                             "%.3f" % c["noise_s"],
                             "%d+/%d- p=%.3g" % (c["sign_test"]["positive"], c["sign_test"]["negative"],
                                                c["sign_test"]["p_two_sided"]),
                             "%+.2f%%" % (100 * c["relative_median_diff"]) if c.get("relative_median_diff") is not None else "-"]]))
        lines.append("")
        lines.append("Reason: %s. Positive differences mean `%s` is slower." % (c["reason"], arm))
        pos = c.get("positional")
        if pos:
            lines.append("Positional: median B-A when `%s` ran second %+.3f s (n=%d), first %+.3f s (n=%d); "
                         "cost of running second %+.3f s." % (arm, pos["median_diff_ab_s"], pos["n_ab"],
                                                              pos["median_diff_ba_s"], pos["n_ba"],
                                                              pos["second_position_cost_s"]))
        lines.append("Paired differences (s): " + ", ".join("%+.3f" % x for x in c["diffs_s"]))
    else:
        lines.append("Reason: %s." % c["reason"])
    return "\n".join(lines)


def render_identity(ident: Dict) -> str:
    rows = []
    for arm, r in ident.items():
        rows.append([arm, "PASS" if r["identical"] else "FAIL", r["compared"], r["mrc_compared"],
                     len(r["excluded"]), "; ".join(r["problems"]) or "-"])
    body = table(["arm vs base", "result", "files compared", "MRC compared", "excluded", "problems"], rows)
    for arm, r in ident.items():
        for d in r["differences"][:10]:
            body += "\n- `%s` %s: %s" % (arm, d["file"], d["difference"])
        for side, key in (("only in base", "only_a"), ("only in arm", "only_b")):
            if r[key]:
                body += "\n- `%s` %s: %s" % (arm, side, ", ".join(r[key][:10]))
    body += "\n\nExcluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023."
    return section("Product identity", INSTR_IDENTITY, body)


def render_stage_deltas(sd: Dict) -> str:
    body = ("One profiled pass per arm; each steady-state movie (all but the first) is a sample. "
            "Flags mark |delta| > 3 robust standard errors and above 0.5 ms (50 faults). "
            "These are indicative: they localise a change, the verdict above decides it.\n")
    for arm, d in sd["arms"].items():
        mw = d["movie_wall"]
        body += "\n### `%s` vs `%s`\n\nMovie wall (steady, median): %.1f -> %.1f ms (%+.1f)%s\n\n" % (
            arm, sd["base"], mw["median_a"], mw["median_b"], mw["delta"], " **flagged**" if mw["flag"] else "")
        rows = []
        for n, r in d["stages"].items():
            w, c, f = r["wall_ms"], r["cpu_ms"], r["minflt"]
            if w.get("delta") is None:
                continue
            rows.append([("**%s**" % n) if (w["flag"] or c["flag"] or f["flag"]) else n,
                         "%.2f" % w["median_a"], "%.2f" % w["median_b"], "%+.2f%s" % (w["delta"], " *" if w["flag"] else ""),
                         "%+.2f%s" % (c["delta"], " *" if c["flag"] else ""),
                         "%+.0f%s" % (f["delta"], " *" if f["flag"] else "")])
        body += table(["stage", "base wall ms", "arm wall ms", "delta wall ms", "delta CPU ms", "delta minflt"], rows)
    bad = {a: c for a, c in sd["checks"].items() if c}
    if bad:
        body += "\n\nWARNING: non-exhaustive stages: %s" % json.dumps(bad)
    return section("Stage profile deltas", INSTR_PROFILE, body)


def render_device_deltas(dd: Dict) -> str:
    body = ("One traced pass per arm; per-movie values of each stage, steady-state movies as samples. "
            "busy = union of kernel and copy time inside the stage; idle = stage wall - busy.\n")
    for arm, d in dd["arms"].items():
        body += "\n### `%s` vs `%s`\n\n" % (arm, dd["base"])
        rows = []
        for n, r in d["stages"].items():
            def cell(k, scale=1e6, fmt="%+.2f"):
                v = r[k]
                if v.get("delta") is None:
                    return "-"
                return (fmt % (v["delta"] / scale)) + (" *" if v["flag"] else "")
            flagged = any(r[k].get("flag") for k, _ in DEVICE_KEYS)
            rows.append([("**%s**" % n) if flagged else n, cell("wall_ns"), cell("busy_ns"), cell("idle_ns"),
                         cell("kernels", 1, "%+.0f"), cell("sync_calls", 1, "%+.0f"),
                         cell("copy_bytes", 1048576, "%+.1f"), cell("malloc", 1, "%+.0f")])
        body += table(["stage", "wall ms", "busy ms", "idle ms", "kernels", "sync calls", "copy MiB", "mallocs"], rows)
        body += "\n\nOutside-movie rows are single values, not medians, and are never flagged."
        if d["memory"]:
            m = d["memory"]
            body += "\n\nTraced device allocation high-water: %s -> %s MiB (%+.1f MiB)." % (
                mib(m["peak_a"]), mib(m["peak_b"]), m["delta"] / 1048576.0)
    return section("Device deltas", INSTR_NSYS, body)


def render_trace(t: Dict) -> str:
    tot = t["totals"]
    span = t["span_ns"]
    body = ("Traced window %.1f ms, %d movies. Device busy (union of kernels, copies, memsets) %.1f ms "
            "(%.1f%%); idle %.1f ms. Kernels %d (%.1f ms summed), copies %d (%.1f ms, %.1f MiB). "
            "Overlap between kernels and copies %.2f ms. Streams with kernels: %d.\n\n" % (
                span / 1e6, tot["movies"], tot["busy_ns"] / 1e6, 100.0 * tot["busy_ns"] / span if span else 0,
                tot["idle_ns"] / 1e6, tot["kernels"], tot["kernel_sum_ns"] / 1e6, tot["copies"],
                tot["copy_sum_ns"] / 1e6, tot["copy_bytes"] / 1048576.0, tot["overlap_ns"] / 1e6,
                tot["streams_with_kernels"]))
    body += ("Per stage, steady-state median per movie (movies after the first); first movie separately. "
             "Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.\n\n")
    rows = []
    for n, r in t["stages"].items():
        if r["kind"] in ("stage", "unattributed"):
            g = lambda k: r[k]["steady_median"]
            rows.append([n, ms(g("wall_ns")), ms(g("busy_ns")), ms(g("kernel_busy_ns")), ms(g("copy_busy_ns")),
                         "%.0f%%" % (100.0 * g("busy_ns") / g("wall_ns")) if g("wall_ns") else "-",
                         ms(g("idle_ns")), "%.0f" % g("idle_intervals"), "%.0f" % g("kernels"),
                         "%.0f" % g("sync_calls"), ms(g("sync_blocked_idle_ns")),
                         "%.0f/%.0f" % (g("malloc"), g("free")), "%.1f" % (g("copy_bytes") / 1048576.0),
                         "%.0f" % g("pageable_copies"), mib(r.get("mem_peak_bytes")), ms(r["wall_ns"]["first"])])
    body += table(["stage", "wall ms", "busy ms", "kernel ms", "copy ms", "busy %", "idle ms", "idle gaps",
                   "kernels", "sync calls", "sync blocked idle ms", "malloc/free", "copy MiB", "pageable copies",
                   "mem peak MiB", "first movie wall ms"], rows)
    out_rows = [[n, ms(r["wall_ns"]["sum"]), ms(r["busy_ns"]["sum"]), ms(r["idle_ns"]["sum"]),
                 "%d" % r["kernels"]["sum"], "%d/%d" % (r["malloc"]["sum"], r["free"]["sum"])]
                for n, r in t["stages"].items() if r["kind"] in ("outside", "whole")]
    if out_rows:
        body += "\n\nOutside movies (totals):\n\n" + table(["segment", "wall ms", "busy ms", "idle ms", "kernels",
                                                            "malloc/free"], out_rows)
    if t.get("memory"):
        for d, m in t["memory"]["devices"].items():
            body += ("\n\nDevice %s allocation high-water %s MiB at stage `%s` (movie %s); residual at end %s MiB. "
                     "%s." % (d, mib(m["peak_bytes"]), m["peak_segment"], m["peak_movie"], mib(m["residual_bytes"]),
                              t["memory"]["scope"]))
    body += "\n\nTop kernels by device time:\n\n" + table(
        ["kernel", "launches", "total ms", "mean us", "max us", "share"],
        [[k["name"][:60], k["launches"], ms(k["device_ns"]), "%.1f" % (k["mean_ns"] / 1e3), "%.1f" % (k["max_ns"] / 1e3),
          "%.1f%%" % (100 * k["share"])] for k in t["top_kernels"]])
    sync_tot: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0])
    for st in t["syncs_by_stage"].values():
        for k, v in st.items():
            sync_tot[k][0] += v["n"]
            sync_tot[k][1] += v["host_ns"]
            sync_tot[k][2] += v["blocked_idle_ns"]
    if sync_tot:
        body += "\n\nBlocking calls (whole trace; blocked idle = host time in the call while the device was idle):\n\n"
        body += table(["class", "calls", "host ms", "blocked idle ms"],
                      [[k, v[0], ms(v[1]), ms(v[2])] for k, v in sorted(sync_tot.items(), key=lambda kv: -kv[1][1])])
    copy_tot: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0])
    for st in t["copies_by_stage"].values():
        for k, v in st.items():
            copy_tot[k][0] += v["n"]
            copy_tot[k][1] += v["bytes"]
            copy_tot[k][2] += v["device_ns"]
    if copy_tot:
        body += "\n\nCopies by direction and memory kind (whole trace):\n\n"
        body += table(["direction src->dst", "n", "MiB", "device ms", "GB/s"],
                      [[k, v[0], "%.1f" % (v[1] / 1048576.0), ms(v[2]), "%.2f" % (v[1] / v[2]) if v[2] else "-"]
                       for k, v in sorted(copy_tot.items(), key=lambda kv: -kv[1][1])])
        body += "\n\nByte counts are invariant across captures; rates are not (contention, tracing)."
    return section("Device", INSTR_NSYS, body)


def render_kernels(k: Dict) -> str:
    rows = []
    for name, m in k["summary"]["kernels"].items():
        nd = (k.get("nsys") or {}).get(name)
        rows.append([name[:60], m["launches_profiled"], "%.1f" % m.get("sm_pct", float("nan")),
                     "%.1f" % m.get("mem_pct", float("nan")), "%.1f" % m.get("dram_pct", float("nan")),
                     "%.1f" % m.get("achieved_occ_pct", float("nan")), "%.1f" % m.get("theoretical_occ_pct", float("nan")),
                     "%.0f" % m.get("grid", float("nan")), "%.0f" % m.get("block", float("nan")),
                     "%.1f" % m.get("ncu_duration_us", float("nan")),
                     ("%d / %.1f ms / %.1f us" % (nd["launches"], nd["device_ns"] / 1e6, nd["mean_ns"] / 1e3)) if nd else "-"])
    body = table(["kernel", "profiled", "SM %", "MEM %", "DRAM %", "occ %", "theo occ %", "grid", "block",
                  "ncu dur us (ref)", "nsys launches / total / mean"], rows)
    body += ("\n\nPercentages are medians over profiled launches, filtered to unit `%`; metrics reported in other "
             "units under the same name were dropped: %s. Device time comes from the Nsight Systems trace "
             "(last column); ncu serialises and replays kernels, so its duration is a reference only."
             % (json.dumps(k["summary"]["units_rejected"]) or "none"))
    return section("Kernel counters", INSTR_NCU, body)


def render_document(title: str, parts: Sequence[str]) -> str:
    return "# %s\n\n%s" % (title, "\n".join(p for p in parts if p))


# ----------------------------------------------------------------- HTML

def to_html(markdown: str, title: str) -> str:
    """Minimal self-contained HTML for the Markdown this module writes."""
    out, in_table, in_list = [], False, False
    for line in markdown.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join("<th>%s</th>" % _inline(c) for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- ") or line.startswith("  - "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>%s</li>" % _inline(line.lstrip(" -")))
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        m = re.match(r"^(#+) (.*)", line)
        if m:
            n = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (n, _inline(m.group(2)), n))
        elif line.strip():
            out.append("<p>%s</p>" % _inline(line))
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font:14px/1.45 system-ui,sans-serif;max-width:1200px;margin:2em auto;padding:0 1em}"
           "table{border-collapse:collapse;margin:.5em 0}td,th{border:1px solid #bbb;padding:2px 6px;"
           "text-align:right}td:first-child,th:first-child{text-align:left}code{background:#f2f2f2}")
    return ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title><style>%s</style></head>"
            "<body>%s</body></html>\n" % (html.escape(title), css, "\n".join(out)))


def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s
