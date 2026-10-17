"""Post-hoc look at run order in a warmab.json (not the pre-set test, which is the
plain sign test over 12 pairs printed by warmab.py).
Prints base - cand per rep split by the candidate's position, and the mean of each
consecutive rep pair (rep 2k and 2k+1 run the arms in opposite orders, so the
position cost cancels within the pair).  usage: position.py <warmab.json>"""
import json, statistics as st, sys
from math import comb
d = json.load(open(sys.argv[1]))
recs = d["records"]
def sign_p(x):
    n = len(x); w = sum(v > 0 for v in x); k = min(w, n - w)
    return w, n, min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
for ng in sorted({r["ngpu"] for r in recs}):
    diff, pos = {}, {}
    for rep in sorted({r["rep"] for r in recs}):
        b = next(r for r in recs if r["rep"] == rep and r["ngpu"] == ng and r["arm"] == "base")
        c = next(r for r in recs if r["rep"] == rep and r["ngpu"] == ng and r["arm"] == "cand")
        diff[rep] = b["dataset_wall_s"] - c["dataset_wall_s"]; pos[rep] = c["order"]
    print(f"{ng}x8-24 (base - cand, s; positive = cand faster)")
    for p in (0, 1):
        v = [diff[k] for k in diff if pos[k] == p]
        print(f"  cand ran {'first ' if p == 0 else 'second'}: median {st.median(v):+.3f}  [{', '.join('%+.3f' % x for x in v)}]")
    reps = sorted(diff)
    pairs = [(diff[reps[i]] + diff[reps[i + 1]]) / 2 for i in range(0, len(reps) - 1, 2)]
    w, n, p = sign_p(pairs)
    print(f"  order-balanced rep pairs: median {st.median(pairs):+.3f}  cand faster {w}/{n}  sign p={p:.3f}  [{', '.join('%+.3f' % x for x in pairs)}]")
