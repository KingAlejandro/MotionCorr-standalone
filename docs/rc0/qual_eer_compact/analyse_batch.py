import hashlib, json, pathlib, re, sys
ROOT = pathlib.Path("/mnt/clathrin/alex-motioncorr-rc0/W-EER-Q")
def sha(p):
    # MRC payload only (after the 1024-byte header and nsymbt extended header): the header carries a run timestamp
    import struct
    h = hashlib.sha256()
    with open(p, "rb") as f:
        hd = f.read(1024); nsym = struct.unpack("<i", hd[92:96])[0]
        f.seek(1024 + nsym)
        for b in iter(lambda: f.read(1 << 24), b""): h.update(b)
    return h.hexdigest()[:16]
out = {}
for case in sys.argv[1:]:
    rr = json.load(open(ROOT / "results" / case / "result.json"))
    out[case] = {}
    for arm in ("auto", "float"):
        d = ROOT / "runs" / case / f"out-{arm}"
        prods = {}
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".mrc", ".star"):
                prods[str(p.relative_to(d))] = sha(p) if p.suffix == ".mrc" else ("star:%d B" % p.stat().st_size)
        err = (ROOT / "results" / case / f"{arm}.stderr").read_text(errors="replace")
        warns = sorted(set(re.findall(r"WARNING: [^\n]*", err)))
        errs = re.findall(r"ERROR: \n?([^\n]+)", err)
        errs = [e for e in errs if e.strip()]
        sizes = {}
        for lg in sorted(d.rglob("movie*.log")):
            m = re.search(r"Movie size: X = (\d+) Y = (\d+) N = (\d+)", lg.read_text(errors="replace"))
            sizes[lg.name] = m.groups() if m else None
        joint = (d / "corrected_micrographs.star").exists()
        out[case][arm] = dict(rc=rr["arms"][arm]["rc"], witness=rr["arms"][arm]["witness"], products=prods, joint_star=joint, warnings=warns[:4], n_warn_lines=len(re.findall(r"WARNING: [^\n]*", err)), errors=sorted(set(errs))[:4], sizes=sizes)
    a, f = out[case]["auto"]["products"], out[case]["float"]["products"]
    out[case]["auto_eq_float_products"] = a == f
json.dump(out, open(ROOT / "results" / "batch_analysis.json", "w"), indent=1)
for c, v in out.items():
    print("==", c, "auto==float products:", v["auto_eq_float_products"])
    for arm in ("auto", "float"):
        x = v[arm]; print(" ", arm, "rc", x["rc"], "joint", x["joint_star"], "nwarn", x["n_warn_lines"], x["warnings"][:1], "ERR", [e[:140] for e in x["errors"]]); print("    ", x["products"]); print("    ", x["sizes"])
