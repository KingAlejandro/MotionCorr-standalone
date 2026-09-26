#!/usr/bin/env python3
"""Insert FFTW_LOCK_STATS probes around every
#pragma omp critical(FourierTransformer_fftw_plan) block."""
import re, sys

PRAGMA = "#pragma omp critical(FourierTransformer_fftw_plan)"

def patch(path, is_create):
    src = open(path).read()
    if "FLS_WAIT_BEGIN" in src:
        print(f"{path}: already patched"); return 0
    out, pos, n = [], 0, 0
    while True:
        i = src.find(PRAGMA, pos)
        if i < 0:
            out.append(src[pos:]); break
        # start of the pragma's line (preserve indentation)
        ls = src.rfind("\n", 0, i) + 1
        indent = src[ls:i]
        # find the opening brace after the pragma line
        ob = src.index("{", i)
        # find its matching close brace
        depth, j = 0, ob
        while True:
            if src[j] == "{": depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        body = src[ob+1:j]
        out.append(src[pos:ls])
        out.append(f"{indent}FLS_WAIT_BEGIN();\n")
        out.append(src[ls:ob+1])
        out.append(f"\n{indent}\tFLS_ENTER();")
        out.append(body.rstrip())
        out.append(f"\n{indent}\tFLS_EXIT({1 if is_create else 0});\n{indent}}}")
        pos = j + 1
        n += 1
    open(path, "w").write("".join(out))
    print(f"{path}: patched {n} site(s)")
    return n

def add_include(path, header):
    src = open(path).read()
    if header in src: return
    # insert after the first #include line
    m = re.search(r'^#include[^\n]*\n', src, re.M)
    src = src[:m.end()] + f'#include "{header}"\n' + src[m.end():]
    open(path, "w").write(src)
    print(f"{path}: added include")

root = sys.argv[1]
add_include(f"{root}/src/jaz/single_particle/new_ft.cpp", "src/jaz/single_particle/fftw_lock_stats.h")
add_include(f"{root}/src/jaz/single_particle/new_ft.h",   "src/jaz/single_particle/fftw_lock_stats.h")
c = patch(f"{root}/src/jaz/single_particle/new_ft.cpp", True)
d = patch(f"{root}/src/jaz/single_particle/new_ft.h",  False)
assert c == 4 and d == 2, f"expected 4 create + 2 destroy sites, got {c} + {d}"
print("OK")
