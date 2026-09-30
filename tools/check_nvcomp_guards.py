#!/usr/bin/env python3
"""A CudaMovieSession member defined under _NVCOMP_ENABLED must be declared there too.

This class of defect has now appeared twice on this branch and is invisible to
every test in the suite, because the suite never links the configuration it
breaks:

  gatherFrameSamples   defined inside the guard, declared outside. A CUDA build
                       without USE_NVCOMP had a call with no symbol. It linked
                       anyway because nothing assigns nvcomp_ingested in that
                       configuration, so the call was provably dead and GCC
                       dropped it before the linker looked. Adding unrelated
                       code near the call site stopped that reasoning firing.

  endIngestScratch     the same thing one level up: moving gatherFrameSamples
                       out of the guard gave it an unguarded caller, and CI run
                       317 failed with "undefined reference to
                       CudaMovieSession::endIngestScratch()".

Building the configuration does catch it -- eventually, and only when the
optimiser happens not to hide it. This checks the actual property instead: the
declaration and the definition of every member agree about the guard. It needs
no compiler, no CUDA and no nvCOMP, so it runs everywhere the rest of the
device-free suite does.

Definition guarded + declaration unguarded is the failure. The reverse is
harmless (an unused declaration), and is reported as a warning only.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

GUARD = "#if defined(_NVCOMP_ENABLED)"
DECL = re.compile(r"^\s+(?:bool|void|int|size_t|float\s*\*?)\s+(\w+)\s*\(")
DEFN = re.compile(r"^(?:bool|void|int|size_t|float\s*\*?)\s+CudaMovieSession::(\w+)\s*\(")


def guarded_lines(lines: list[str]) -> set[int]:
    """Indices sitting inside an _NVCOMP_ENABLED conditional, nesting-aware."""
    inside: set[int] = set()
    stack: list[bool] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#if"):
            stack.append(s == GUARD)
        elif s.startswith("#endif"):
            if stack:
                stack.pop()
        if any(stack):
            inside.add(i)
    return inside


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    hdr = root / "src/acc/cuda/cuda_movie_session.h"
    src = root / "src/acc/cuda/cuda_movie_session.cu"
    if not hdr.is_file() or not src.is_file():
        print(f"FAIL: cannot find {hdr} / {src}")
        return 1

    h, c = hdr.read_text().splitlines(), src.read_text().splitlines()
    hg, cg = guarded_lines(h), guarded_lines(c)

    decls = {m.group(1): (i in hg) for i, l in enumerate(h) if (m := DECL.match(l))}
    defs = {m.group(1): (i in cg) for i, l in enumerate(c) if (m := DEFN.match(l))}

    errors, warnings = [], []
    for name, def_guarded in sorted(defs.items()):
        if name not in decls:
            continue
        if def_guarded and not decls[name]:
            errors.append(
                f"{name}: defined inside {GUARD} but declared outside it. A CUDA "
                f"build without USE_NVCOMP will fail to link any call that the "
                f"optimiser does not remove.")
        elif decls[name] and not def_guarded:
            warnings.append(f"{name}: declared inside the guard, defined outside it.")

    for w in warnings:
        print(f"WARNING: {w}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print(f"nvcomp guards: {len(defs)} CudaMovieSession members, "
          f"declaration and definition agree on all of them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
