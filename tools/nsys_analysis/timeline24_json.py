#!/usr/bin/env python3
"""Extract the 24-movie picture: GPU activity raster, per-movie walls, and
stage totals aggregated over all movies."""
import sqlite3, sys, json, collections
c = sqlite3.connect(sys.argv[1])
def one(q, *a):
    r = c.execute(q, a).fetchone(); return r[0] if r and r[0] is not None else 0
R = collections.defaultdict(list)
for nm, a, b in c.execute("""select coalesce(e.text,s.value),e.start,e.end from NVTX_EVENTS e
    left join StringIds s on s.id=e.textId where e.end is not null"""):
    R[nm].append((a, b))
def u(iv):
    iv = sorted(iv); m = []
    for a, b in iv:
        if m and a <= m[-1][1]: m[-1][1] = max(m[-1][1], b)
        else: m.append([a, b])
    return [tuple(x) for x in m]
MV = "MOVIE (executeOwnMotionCorrection)"
movies = sorted(R[MV])
lo = one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME") or movies[0][0]
hi = one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME") or movies[-1][1]
lo = min(lo, movies[0][0]); hi = max(hi, movies[-1][1])
ker = u([(r[0], r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")])
mem = u([(r[0], r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")])
def clip(iv, a, b): return sum(min(y, b)-max(x, a) for x, y in iv if x < b and y > a)

stages = []
for nm, v in R.items():
    if nm == MV: continue
    w = u(v); wall = sum(b-a for a, b in w)
    if wall < 2e6: continue                      # drop sub-2 ms markers
    stages.append(dict(name=nm, n=len(v), wall=wall,
                       kern=sum(clip(ker, a, b) for a, b in w),
                       mcpy=sum(clip(mem, a, b) for a, b in w)))
stages.sort(key=lambda s: -s["wall"])

per_movie = []
for a, b in movies:
    per_movie.append(dict(start=a-lo, end=b-lo, wall=b-a,
                          kern=clip(ker, a, b), mcpy=clip(mem, a, b)))
mw = sum(b-a for a, b in movies)
json.dump(dict(span=hi-lo, nmovies=len(movies),
               movie_total=mw, pre=movies[0][0]-lo, post=hi-movies[-1][1],
               kernel=[[a-lo, b-lo] for a, b in ker],
               memcpy=[[a-lo, b-lo] for a, b in mem],
               tot_kern=sum(b-a for a, b in ker), tot_mcpy=sum(b-a for a, b in mem),
               stages=stages, per_movie=per_movie),
          open(sys.argv[2], "w"))
print("span %.1f s, %d movies, movie_total %.1f s, pre %.1f s, post %.1f s"
      % ((hi-lo)/1e9, len(movies), mw/1e9, (movies[0][0]-lo)/1e9, (hi-movies[-1][1])/1e9))
print("GPU busy: kernels %.1f ms + transfers %.1f ms"
      % (sum(b-a for a, b in ker)/1e6, sum(b-a for a, b in mem)/1e6))
