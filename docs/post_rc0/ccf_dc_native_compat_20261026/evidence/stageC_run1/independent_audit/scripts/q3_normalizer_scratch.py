"""Q3 scratch only: does a versioned v2 log normaliser that ignores ONLY the two CUDA timing values
repair the zero-cuda B3 STOP, while every other line and every semantic mutant stays strict?
v1 is extracted verbatim (ast) from the sealed tools/ccf_dc_native_rows.py; nothing in the repo is changed."""
import ast, json, re, sys, os
SRC, RUNS, OUT = sys.argv[1:4]
tree = ast.parse(open(SRC).read())
keep = [n for n in tree.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("CLOCK_LINE", "LOG_WALL_LINE") for t in n.targets))
        or (isinstance(n, ast.FunctionDef) and n.name == "normalise_console")]
assert len(keep) == 3, [ast.dump(k)[:60] for k in keep]
ns = {"re": re}
exec(compile(ast.Module(body=keep, type_ignores=[]), SRC, "exec"), ns)
v1 = ns["normalise_console"]

# v2: v1 plus two fully anchored line patterns; exact label, exact spacing, fixed-point value, " ms" suffix.
GPU_ALIGN = re.compile(r"(?m)^   Total GPU alignment time:     [0-9]+\.[0-9]{2} ms$")
UNW_RECON = re.compile(r"(?m)^  Total Unweighted Reconstruction Time: [0-9]+\.[0-9]{2} ms$")
def v2_log(text, outdir):
    t = v1(text, outdir)
    t = GPU_ALIGN.sub("   Total GPU alignment time:     T ms", t)
    return UNW_RECON.sub("  Total Unweighted Reconstruction Time: T ms", t)

HOST = "/home/alex/mc-dcnative-stagec-20261027-r1/runs/runs"
J = {k: next(d for d in os.listdir(RUNS) if d.startswith(k)) for k in ("J007", "J008", "J009")}
logs = {k: open(os.path.join(RUNS, d, "out", "zero.log")).read() for k, d in J.items()}
od = {k: f"{HOST}/{d}/out" for k, d in J.items()}
res = {"v1_source_sha256": __import__("hashlib").sha256(open(SRC, "rb").read()).hexdigest(), "pairs": {}, "controls": {}}

def eq(norm, a, b, ta=None, tb=None):
    return norm(logs[a] if ta is None else ta, od[a]) == norm(logs[b] if tb is None else tb, od[b])

for a, b in (("J007", "J008"), ("J008", "J009"), ("J007", "J009")):
    da = [l for l in zip(v1(logs[a], od[a]).splitlines(), v1(logs[b], od[b]).splitlines()) if l[0] != l[1]]
    res["pairs"][f"{a}_vs_{b}"] = dict(v1_equal=eq(v1, a, b), v2_equal=eq(v2_log, a, b), v1_residual_lines=da)
# v2 changes only the two labelled lines relative to v1 (no other line touched)
for k in logs:
    l1, l2 = v1(logs[k], od[k]).splitlines(), v2_log(logs[k], od[k]).splitlines()
    res.setdefault("v2_touches_only", {})[k] = dict(same_line_count=len(l1) == len(l2),
        changed=[x for x, y in zip(l1, l2) if x != y])
# scratch CPU-shaped log (the CUDA log with the CUDA profile blocks removed): v2 == v1 exactly
cpu_like = "\n".join(l for l in logs["J008"].splitlines() if "CUDA" not in l and "VRAM" not in l and "Total" not in l and "Per-kernel" not in l and "Device:" not in l) + "\n"
res["cpu_shaped_v1_equals_v2"] = v1(cpu_like, od["J008"]) == v2_log(cpu_like, od["J008"])

base = logs["J008"]
def mut(old, new, count=1):
    assert old in base, old
    return base.replace(old, new, count)
gpu_line = next(l for l in base.splitlines() if "Total GPU alignment time" in l)
unw_line = next(l for l in base.splitlines() if "Total Unweighted Reconstruction Time" in l)
M = {
 # must stay EQUAL under v2 (timing-only changes)
 "timing_only_gpu_value": (mut(gpu_line, "   Total GPU alignment time:     987.65 ms"), True),
 "timing_only_unw_value": (mut(unw_line, "  Total Unweighted Reconstruction Time: 12.00 ms"), True),
 "timing_only_both_and_wall": (mut(gpu_line, "   Total GPU alignment time:     0.01 ms").replace(unw_line, "  Total Unweighted Reconstruction Time: 3.14 ms").replace("Full movie wall time: 0.176 s", "Full movie wall time: 9.999 s"), True),
 # must FAIL under v2 (semantic or structural changes)
 "rmsd_value": (mut("RMSD = 0 px", "RMSD = 0.01 px"), False),
 "converged_flag": (mut("converged=yes", "converged=no"), False),
 "peak_vram_numeric": (mut("Peak VRAM: 0.05 MiB", "Peak VRAM: 0.06 MiB"), False),
 "buffer_vram_numeric": (mut("Buffer VRAM:                  0.78 MiB", "Buffer VRAM:                  0.79 MiB"), False),
 "local_skip_text": (mut("Local alignment is skipped.", "Local alignment is done."), False),
 "frames_used": (mut("Frames to be used: 1 2 3 4 5", "Frames to be used: 1 2 3 4"), False),
 "gpu_label_changed": (mut(gpu_line, "   Total GPU alignment tim3:     1.19 ms"), False),
 "gpu_prefix_spacing": (mut(gpu_line, "  Total GPU alignment time:     1.19 ms"), False),
 "gpu_unit_changed": (mut(gpu_line, "   Total GPU alignment time:     1.19 s"), False),
 "gpu_value_nonnumeric": (mut(gpu_line, "   Total GPU alignment time:     nan ms"), False),
 "gpu_value_three_decimals": (mut(gpu_line, "   Total GPU alignment time:     1.190 ms"), False),
 "gpu_trailing_text": (mut(gpu_line, gpu_line + " (retry)"), False),
 "gpu_line_deleted": (mut(gpu_line + "\n", ""), False),
 "gpu_line_duplicated": (mut(gpu_line + "\n", gpu_line + "\n" + gpu_line + "\n"), False),
 "gpu_line_moved": (mut(gpu_line + "\n", "").replace(" [CUDA Global Alignment] completed", gpu_line + "\n [CUDA Global Alignment] completed"), None),
 "unw_label_changed": (mut(unw_line, "  Total Weighted Reconstruction Time: 0.25 ms"), False),
 "unw_line_deleted": (mut(unw_line + "\n", ""), False),
 "timing_plus_semantic": (mut(gpu_line, "   Total GPU alignment time:     5.00 ms").replace("converged=yes", "converged=no"), False),
 "dw_timing_line_inserted": (mut(unw_line, unw_line + "\n  Total DW Reconstruction Time: 0.10 ms"), False),
 "device_id": (mut("Device: 0,", "Device: 1,"), False),
}
for name, (text, expect) in M.items():
    got = eq(v2_log, "J007", "J008", tb=text) if False else (v2_log(base, od["J008"]) == v2_log(text, od["J008"]))
    got_v1 = v1(base, od["J008"]) == v1(text, od["J008"])
    res["controls"][name] = dict(v2_equal=got, v1_equal=got_v1, expected_v2_equal=expect,
                                 ok=(got == expect) if expect is not None else None)
bad = [k for k, v in res["controls"].items() if v["ok"] is False]
res["control_failures"] = bad
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps({"pairs": {k: (v["v1_equal"], v["v2_equal"]) for k, v in res["pairs"].items()},
                  "cpu_shaped_v1_equals_v2": res["cpu_shaped_v1_equals_v2"], "control_failures": bad,
                  "moved": res["controls"]["gpu_line_moved"]}, indent=0))

# console part of the producer claim, under the frozen v1 exactly as identity_report applies it
con = {}
for a, b in (("J007", "J008"), ("J008", "J009")):
    rd = lambda k, f: open(os.path.join(RUNS, J[k], f)).read()
    con[f"{a}_vs_{b}"] = dict(
        stdout=v1(rd(a, "stdout.txt"), od[a]) == v1(rd(b, "stdout.txt"), od[b]),
        stderr=sorted(v1(rd(a, "stderr.txt"), od[a]).splitlines()) == sorted(v1(rd(b, "stderr.txt"), od[b]).splitlines()))
res["console_v1"] = con
json.dump(res, open(OUT, "w"), indent=1)
print("console_v1", con)
