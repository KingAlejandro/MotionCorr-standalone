#!/usr/bin/env python3
"""Folded stacks from an nsys CPU-sampling export, with unresolved frames
collapsed to their module so the graph stays readable."""
import sqlite3, sys, collections, re
db, out = sys.argv[1], sys.argv[2]
only_main = (len(sys.argv) > 3 and sys.argv[3] == "main")
c = sqlite3.connect(db)
S = {r[0]: r[1] for r in c.execute("select id,value from StringIds")}
names = {r[0]: S.get(r[1], "?") for r in c.execute("select globalTid,nameId from ThreadNames")}
HEX = re.compile(r"^0x[0-9a-f]+$")

def label(sym, mod):
    nm = S.get(sym)
    md = (S.get(mod) or "[unknown]").split("/")[-1]
    if nm and not HEX.match(nm):
        return nm.split("(")[0][:70]          # drop C++ parameter lists
    if md.startswith("[") :
        return md
    return "[%s]" % md

ev = dict(c.execute("select id, globalTid from COMPOSITE_EVENTS"))
frames = collections.defaultdict(list)
for cid, sym, mod, depth in c.execute(
        "select id, symbol, module, stackDepth from SAMPLING_CALLCHAINS"):
    frames[cid].append((depth, label(sym, mod)))

counts = collections.Counter(); dropped = 0
for cid, tid in ev.items():
    f = frames.get(cid)
    if not f: dropped += 1; continue
    proc = names.get(tid, "?")
    if only_main and proc != "motioncorr": continue
    f.sort(key=lambda x: -x[0])
    stack = [proc] + [n for _, n in f]
    dedup = [stack[0]]
    for x in stack[1:]:
        if x != dedup[-1]: dedup.append(x)
    counts[";".join(dedup)] += 1

with open(out, "w") as fh:
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        fh.write("%s %d\n" % (k, v))
print("%s: %d samples, %d unique stacks, %d without callchain"
      % (out, sum(counts.values()), len(counts), dropped))
