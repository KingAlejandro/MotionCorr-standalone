#!/usr/bin/env python3
"""Keep the first N movie rows of a RELION movies STAR, preserving every other block.

Used to run a short job on the same dataset without editing the canonical input.
Usage: subset_star.py <src.star> <dst.star> <n>
"""
import sys
from pathlib import Path


def main():
    src, dst, n_keep = sys.argv[1], sys.argv[2], int(sys.argv[3])
    lines = Path(src).read_text().splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "data_movies")
    except StopIteration:
        raise SystemExit(f"{src}: no data_movies block")
    kept, seen = [], 0
    for line in lines[start:]:
        token = line.strip().split()[0].lower() if line.strip() else ""
        if token.endswith((".tif", ".tiff", ".mrc", ".mrcs", ".eer")):
            seen += 1
            if seen > n_keep:
                continue
        kept.append(line)
    if seen == 0:
        raise SystemExit(f"{src}: no movie rows found")
    Path(dst).write_text("\n".join(lines[:start] + kept) + "\n")
    print(f"{dst}: kept {min(seen, n_keep)} of {seen} movie rows")


if __name__ == "__main__":
    main()
