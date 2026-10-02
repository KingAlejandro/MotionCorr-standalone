#!/usr/bin/env python3
import collections, sys
path = sys.argv[1]
leaf = collections.Counter(); incl = collections.Counter(); tot = 0
for ln in open(path):
    st, n = ln.rsplit(" ", 1); n = int(n); tot += n
    fr = st.split(";")
    leaf[fr[-1]] += n
    for f in set(fr): incl[f] += n
print("total samples: %d" % tot)
print()
print("%-56s%9s%8s" % ("LEAF (self time)", "samples", "%"))
for k, v in leaf.most_common(25):
    print("  %-54s%7d%8.1f" % (k[:54], v, 100.0*v/tot))
print()
print("%-56s%9s%8s" % ("INCLUSIVE (on stack)", "samples", "%"))
skip = ("motioncorr", "_start", "__libc_start_main", "main")
for k, v in incl.most_common(40):
    if k in skip: continue
    print("  %-54s%7d%8.1f" % (k[:54], v, 100.0*v/tot))
