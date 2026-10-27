import sys, json, hashlib, os
pins = json.load(open(sys.argv[1]))["fixtures"]
want = {}
for tier, v in pins.items():
    for name, h in v["file_hashes"].items():
        want.setdefault(h, []).append(f"{tier}/{name}")
found = {}
for root in sys.argv[2:]:
    for dp, dn, fn in os.walk(root):
        if "/.git" in dp or "/build/" in dp and "replay" not in dp: continue
        for f in fn:
            if not f.endswith((".npy", ".star", ".mrcs", ".json")): continue
            p = os.path.join(dp, f)
            try:
                if os.path.getsize(p) > 200_000_000: continue
                h = hashlib.sha256(open(p, "rb").read()).hexdigest()
            except OSError: continue
            if h in want:
                for k in want[h]: found.setdefault(k, p)
allk = sorted(k for ks in want.values() for k in ks)
print(json.dumps({"pinned": len(allk), "found": len(found), "missing": [k for k in allk if k not in found], "found_paths": found}, indent=1))
