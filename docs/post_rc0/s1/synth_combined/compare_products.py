#!/usr/bin/env python3
"""Byte-compare two native outputs: MRC header[0:224] + payload and the motion STAR (labels/timestamps excluded)."""
import hashlib, pathlib, sys
def mrc(p):
    b=pathlib.Path(p).read_bytes(); return hashlib.sha256(b[:224]+b[1024:]).hexdigest()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
a,b=map(pathlib.Path,sys.argv[1:3]); ok=True
for name in sys.argv[3:]:
    stem=name  # e.g. movie or fractional
    for ext,fn in (('.mrc',mrc),('.star',sha)):
        pa,pb=a/(stem+ext),b/(stem+ext)
        if not pa.exists() or not pb.exists(): print(stem+ext,'MISSING',pa.exists(),pb.exists()); ok=False; continue
        same=fn(pa)==fn(pb); ok&=same; print(stem+ext,'IDENTICAL' if same else 'DIFFERENT',fn(pa)[:16])
sys.exit(0 if ok else 1)
