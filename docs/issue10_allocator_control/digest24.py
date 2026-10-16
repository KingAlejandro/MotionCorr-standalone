#!/usr/bin/env python3
"""Print a manifest of product digests for one MotionCorr output tree.

MRCs: SHA-256 of data after the 1024-byte header and extended header.
STARs: SHA-256 of the file, with the output-dir prefix removed.
"""
import hashlib, os, struct, sys
root = sys.argv[1].rstrip('/')
rows = []
for dirpath, _, files in os.walk(root):
    for f in sorted(files):
        p = os.path.join(dirpath, f)
        rel = os.path.relpath(p, root)
        if f.endswith('.mrc'):
            with open(p, 'rb') as fh:
                hdr = fh.read(1024)
                nsymbt = struct.unpack('<i', hdr[92:96])[0]
                fh.seek(1024 + nsymbt)
                rows.append((rel, 'mrc', hashlib.sha256(fh.read()).hexdigest()))
        elif f.endswith('.star'):
            data = open(p, 'rb').read().replace(root.encode() + b'/', b'')
            rows.append((rel, 'star', hashlib.sha256(data).hexdigest()))
for r in sorted(rows):
    print(*r)
