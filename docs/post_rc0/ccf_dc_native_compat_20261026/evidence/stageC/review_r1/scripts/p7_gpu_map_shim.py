"""P7: the CUDA pid->UUID sampler (gpu_map + summarize) against a fake nvidia-smi on PATH; not exercised by any author test."""
import json, os, stat, sys, tempfile
from pathlib import Path
W = Path(sys.argv[1]); sys.path.insert(0, str(W / "tools"))
import ccf_dc_stagec_driver as drv
G2 = "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598"
res = {}
with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
    shim = Path(t) / "nvidia-smi"
    def make(body):
        shim.write_text("#!/bin/sh\n" + body); shim.chmod(0o755)
    os.environ["PATH"] = f"{t}:{os.environ['PATH']}"
    make(f'printf "4242, {G2}\\n3983855, {G2}\\n4243, GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d\\n"\n')
    res["map_tree_4242_4243"] = drv.gpu_map({4242, 4243})
    res["map_foreign_not_in_tree"] = drv.gpu_map({1})
    make("exit 9\n")
    try:
        drv.gpu_map({4242}); res["rc9"] = "no error (BAD)"
    except OSError as e:
        res["rc9"] = f"OSError: {e}"
    rec = dict(pid=4242, ppid=1, name="mc", state="R", threads=9, tasks=9, cpus_allowed="80-87", utime=1, stime=1, via="children")
    s_ok = [dict(t=0, pids=[rec], errors=[], gpu={"4242": [G2]})]
    s_none = [dict(t=0, pids=[rec], errors=[], gpu={})]
    s_err = [dict(t=0, pids=[rec], errors=[], gpu_error="OSError('nvidia-smi rc 9')")]
    for k, s in (("summ_mapped", s_ok), ("summ_unmapped", s_none), ("summ_error", s_err)):
        out = drv.summarize(s, True, True, False, False, "procsamples.jsonl")
        res[k] = {x: out.get(x) for x in ("status", "gpu_status", "gpu_uuids_seen_by_pid", "read_errors")}
print(json.dumps(res, indent=1))
