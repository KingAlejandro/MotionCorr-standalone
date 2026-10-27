import sys, tarfile, os, hashlib, json
tgz, dest = sys.argv[1], sys.argv[2]
dest = os.path.realpath(dest)
assert os.listdir(dest) == [], "dest not empty"
rej = []; ok = []
with tarfile.open(tgz, "r:gz") as t:
    mem = t.getmembers()
    for m in mem:
        n = m.name
        if n.startswith("/") or ".." in n.split("/") or not (m.isfile() or m.isdir()):
            rej.append((n, m.type.decode() if isinstance(m.type, bytes) else str(m.type))); continue
        tgt = os.path.realpath(os.path.join(dest, n))
        if not tgt.startswith(dest + os.sep) and tgt != dest:
            rej.append((n, "escape")); continue
        ok.append(m)
    if rej:
        print(json.dumps({"rejected": rej})); sys.exit(2)
    for m in ok:
        t.extract(m, dest, filter="data") if hasattr(tarfile, "data_filter") else t.extract(m, dest)
print(json.dumps({"members": len(mem), "files": sum(m.isfile() for m in ok), "rejected": 0}))
