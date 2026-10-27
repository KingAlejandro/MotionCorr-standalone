"""Reviewer probes on the dry-run harness (fake producers, fake pins, no MotionCorr). Each probe stops the campaign after
a few jobs through the injected guard. argv[1] = worktree."""
import fcntl, json, os, sys, tempfile
from pathlib import Path
W = Path(sys.argv[1]); sys.path.insert(0, str(W / "tools"))
import test_ccf_dc_stagec_driver as T
drv = T.drv
out = {}

def lock_free(path):
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN); return True
    except OSError:
        return False
    finally:
        os.close(fd)

# P1: are the three leases still held while the reports and the manifest are written (amendment 1 section 2)?
with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
    w = T.World(t)
    seen = {}
    def guard(label, need_gpu):
        return (0, "ok\n") if len(seen.setdefault("n", [None])) < 2 and not seen["n"].append(1) else (1, "stop\n")
    d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=guard)
    orig = d.write_manifest
    def spy():
        seen["free_during_manifest"] = {n: lock_free(p) for n, p in w.pins["locks"].items()}
        return orig()
    d.write_manifest = spy
    res = d.execute()
    out["P1"] = dict(status=res["status"], reason=res["reason"], leases_free_while_manifest_written=seen["free_during_manifest"])

# P2a control: input changed alone -> must stop. P2b: input and the fixture MANIFEST.json changed together after verify().
for tag, both in (("P2a_input_only", False), ("P2b_input_and_manifest", True)):
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
        w = T.World(t)
        n = []
        def guard(label, need_gpu, w=w, n=n, both=both):
            n.append(label)
            if len(n) == 1:                      # after verify(), before the first job (affine CUDA exp none)
                star = w.kfx / "affine.star"; star.write_bytes(b"TAMPERED")
                if both:
                    m = json.loads((w.kfx / "MANIFEST.json").read_text())
                    m["cases"]["affine"]["files"]["affine.star"] = T.sha(star)
                    (w.kfx / "MANIFEST.json").write_text(json.dumps(m))
                return 0, "ok\n"
            return (0, "ok\n") if len(n) == 2 else (1, "probe stop\n")
        d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=guard)
        res = d.execute()
        staged = sorted((d.outdir / "runs").glob("*affine*/cwd/affine.star"))
        out[tag] = dict(status=res["status"], reason=res["reason"], jobs_executed=res["jobs_executed"],
                        staged_inputs=[p.read_bytes().decode(errors="replace") for p in staged])

# P3: the guard script is pinned and hashed once in verify(); change it between jobs (real guard path, no hook).
with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
    w = T.World(t)
    g = Path(t) / "guard.sh"; g.write_text("#!/bin/bash\necho pinned-guard-ok; exit 0\n")
    pins = dict(w.pins, guard=dict(path=str(g), sha256=T.sha(g)))
    calls = []
    def spawner(*a, **k):
        calls.append(1)
        r = drv.default_spawner(*a, **k)
        if len(calls) == 1:
            g.write_text("#!/bin/bash\necho UNPINNED-GUARD-RAN; exit 7\n")
        return r
    d = drv.Driver(w.write_pins(pins=pins), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), spawner=spawner)
    res = d.execute()
    out["P3"] = dict(status=res["status"], reason=res["reason"],
                     guard_logs={p.name: p.read_text().strip() for p in sorted((d.outdir / "guards").iterdir())})

# P5: is the release (run_id, authorized_by, release sha256) recorded anywhere the driver writes?
src = (W / "tools/ccf_dc_stagec_driver.py").read_text()
out["P5_release_refs_in_driver"] = [l.strip() for l in src.splitlines() if "release" in l and ("write" in l or "self.release" in l)]
print(json.dumps(out, indent=1))
