import re, glob, gzip, json, math, sys
def gl(path):
    op = gzip.open if path.endswith(".gz") else open
    t = op(path, "rt").read()
    m = re.search(r"data_global_shift\s*\n(.*?)(?=\n# version|\ndata_|\Z)", t, re.S)
    return [list(map(float, l.split()[1:3])) for l in m.group(1).splitlines() if len(l.split()) == 3 and not l.strip().startswith("_")]
def d(a, b): return max(math.hypot(x[0]-y[0], x[1]-y[1]) for x, y in zip(a, b))
out = {}
for spec in sys.argv[1:]:
    name, cpu, cuda = spec.split("=")
    a, b = gl(glob.glob(cpu)[0]), gl(glob.glob(cuda)[0])
    out[name] = round(d(a, b), 4); print(name, out[name])
