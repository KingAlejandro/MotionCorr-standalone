#!/usr/bin/env python3
"""CLI smoke test for the nsys analysis scripts.

Checks the scripts actually run, rather than trusting the JSON and SVGs that were
generated once by hand and committed. Covers the three defect classes that shipped
in the first version of this directory:

  1. a script that dies at its first executable statement (missing `import sys`);
  2. a script that writes into a directory it never creates;
  3. an instrumentation patcher whose literal source anchors have gone stale, and
     whose `assert`-based refusal disappears under `python -O`.

Needs no capture, no GPU and no network. Run from the repository root:

    python3 tools/nsys_analysis/selftest.py

Not registered with CTest: this directory is a documentation/tooling lane that
touches no build files. Whoever next edits CMakeLists.txt should register it.
"""
import ast, json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PY = sys.executable
fails = []

def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -- " + detail) if detail and not cond else ""))
    if not cond: fails.append(name)

def run(args, **kw):
    return subprocess.run([PY] + args, capture_output=True, text=True, **kw)

print("1. every script parses and has no name used before import")
for f in sorted(HERE.glob("*.py")):
    src = f.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        check(f.name + " parses", False, str(e)); continue
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import): imported |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom): imported |= {(a.asname or a.name) for a in n.names}
    bound = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    bound |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    bound |= {a.arg for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda)) for a in n.args.args}
    STD = {"sys","os","json","csv","re","math","sqlite3","collections","statistics",
           "pathlib","zlib","html","subprocess","shutil","time","hashlib","argparse","ast","tempfile"}
    used = {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    missing = sorted((used & STD) - imported - bound)
    check(f.name + " imports what it uses", not missing, "missing: " + ",".join(missing))

print("2. arms24_json.py reaches input handling and creates its output directory")
with tempfile.TemporaryDirectory() as td:
    r = run([str(HERE / "arms24_json.py"), td + "/"])
    check("gets past argv without NameError", "NameError" not in r.stderr, r.stderr.strip()[:120])
    check("fails on the missing capture, not on itself",
          "sqlite3" in r.stderr or "unable to open database" in r.stderr or r.returncode == 0,
          r.stderr.strip()[:120])

print("3. patch_nvtx.py: patches known sources, refuses unknown ones, survives -O")
samples = {}
for tag, rev in (("historical", "1d7e13f"), ("current", "HEAD")):
    g = subprocess.run(["git", "-C", str(ROOT), "show", rev + ":src/motioncorr_runner.cpp"],
                       capture_output=True, text=True)
    if g.returncode == 0 and g.stdout: samples[tag] = g.stdout
if not samples:
    check("a motioncorr_runner.cpp revision is reachable", False, "no git revision available")
for tag, src in samples.items():
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "motioncorr_runner.cpp"; f.write_text(src)
        r = run([str(HERE / "patch_nvtx.py"), str(f)])
        check(tag + " source patches", r.returncode == 0 and "patched:" in r.stdout, r.stderr.strip()[:140])
        out = f.read_text()
        check(tag + " push/pop balanced",
              out.count("RCTIC(") == out.count("RCTOC("),
              "%d push vs %d pop" % (out.count("RCTIC("), out.count("RCTOC(")))
        r2 = run([str(HERE / "patch_nvtx.py"), str(f)])
        check(tag + " refuses to double-patch", r2.returncode != 0, "re-patched an already patched tree")
with tempfile.TemporaryDirectory() as td:
    f = pathlib.Path(td) / "bogus.cpp"; f.write_text("int main(){return 0;}\n")
    before = f.read_text()
    r = run([str(HERE / "patch_nvtx.py"), str(f)])
    check("refuses an unsupported source", r.returncode != 0, "accepted an unsupported source")
    check("leaves an unsupported source untouched", f.read_text() == before)
    rO = run(["-O", str(HERE / "patch_nvtx.py"), str(f)])
    check("refusal survives python -O", rO.returncode != 0,
          "under -O it exited 0; the gate was compiled out")

print("4. mkarms24.py emits two charts and keeps the time domains apart")
data = ROOT / "docs/profiling_20261001/data24/arms24.json"
if not data.exists():
    check("committed arms24.json present", False, str(data))
else:
    with tempfile.TemporaryDirectory() as td:
        pre = os.path.join(td, "sub", "arms24")      # a directory it must create
        r = run([str(HERE / "mkarms24.py"), pre, str(data)])
        check("runs", r.returncode == 0, r.stderr.strip()[:140])
        wall, dev = pathlib.Path(pre + "_wall.svg"), pathlib.Path(pre + "_device.svg")
        check("writes arms24_wall.svg", wall.exists())
        check("writes arms24_device.svg", dev.exists())
        if wall.exists():
            w = wall.read_text()
            check("wall chart carries no device series", "kernel" not in w and "memcpy" not in w)
            check("wall chart says it is unprofiled", "unprofiled" in w)
        if dev.exists():
            dv = dev.read_text()
            check("device chart does not reinstate the old idle label",
                  "GPU idle (host-only work)" not in dv and ">GPU idle<" not in dv)
            check("device chart never calls the remainder idle",
                  "idle" not in dv.lower().replace("upper bound on idle", "")
                                         .replace("establishing real idle", ""))
            check("device chart marks the untraced arm unknown", "not traced" in dv)
            check("device chart bounds busy rather than asserting it", "&lt;=" in dv or "<=" in dv)
        arms = json.loads(data.read_text())["arms"]
        mixed = [a for a in arms if "span" in a and abs(a["span"] - a["wall"]) > 0.5]
        check("profiled span and unprofiled wall genuinely differ (so keeping them apart matters)",
              bool(mixed),
              "no arm differs; the separation would be untestable here")

print()
if fails:
    print("FAILED %d check(s): %s" % (len(fails), "; ".join(fails)))
    sys.exit(1)
print("all nsys_analysis CLI checks passed")
