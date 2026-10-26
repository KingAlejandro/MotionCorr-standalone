#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the byte-exact Part-2 supplemental input export (stdlib only)."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[4]
files={}
for rel in ['native-receipts.tar.gz','native-index.json']:
    source='docs/post_rc0/parallel_20261022/numerics/'+rel
    b=subprocess.check_output(['git','show','805d9de2:'+source],cwd=REPO)
    p=ROOT/'input-cache/extra'/rel
    p.parent.mkdir(exist_ok=True)
    if p.exists(): assert p.read_bytes()==b
    else: p.write_bytes(b)
    files[rel]=dict(sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),origin='805d9de2:'+source)
assert files['native-receipts.tar.gz']['sha256']=='def6ab01874e4ff5a118feb3e307f80e6bdcee5973358cd3b0484526b3ec2435'
b=(json.dumps(files,indent=1)+'\n').encode()
assert hashlib.sha256(b).hexdigest()=='6ec3b6127be33176c915949b62dcd7fa3308eb7c640a1319c2ae70da03313c67'
p=ROOT/'EXTRA-INPUTS.json'
if p.exists(): assert p.read_bytes()==b
else: p.write_bytes(b)
