"""Where the slow rounds of the 2026-10-14 fixed-cost series spent their time.

For every profiled run in profiles.tgz (extracted into <dir>): process run wall, the
first movie's `ingest setup` (where the staging pool is pinned), and the mid-run
excess = sum over movies 2.. of (movie wall - that run's steady median), with the
slowest movies. usage: slow_rounds.py <dir with r*_n*_*/profile.jsonl>"""
import glob, json, os, statistics as st, sys
ING = "session and device ingest/device ingest/ingest setup"
D = sys.argv[1]
by_arm = {}
for d in sorted(glob.glob(os.path.join(D, "r*_n*_*"))):
    L = [json.loads(l) for l in open(os.path.join(d, "profile.jsonl"))]
    mv = [x for x in L if x["type"] == "movie"]; pr = [x for x in L if x["type"] == "process"][0]
    walls = [m["wall_ms"] for m in mv]; med = st.median(walls[1:])
    ing = next(s["wall_ms"] for s in mv[0]["sub"] if s["name"] == ING)
    excess = sum(w - med for w in walls[1:])
    slow = [(i, round(w)) for i, w in enumerate(walls) if i > 0 and w > med + 150]
    tag = os.path.basename(d); n, arm = tag.split("_")[1], tag.split("_")[2]
    by_arm.setdefault((n, arm), []).append((excess, ing))
    print(f"{tag:14s} run={pr['run_wall_ms']:7.0f} first_ingest_setup={ing:6.1f} steady={med:4.0f} "
          f"mid_run_excess={excess:6.0f} movies>steady+150ms={slow[:8]}{' ...' if len(slow) > 8 else ''}")
print("\nper arm: runs with mid-run excess > 1 s, and the largest first-movie ingest setup")
for (n, arm), v in sorted(by_arm.items()):
    print(f"  {n} {arm:5s} {sum(e > 1000 for e, _ in v)}/{len(v)} runs; excess ms {sorted(round(e) for e, _ in v)}; "
          f"max ingest setup {max(i for _, i in v):.1f} ms")
