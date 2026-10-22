#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Archive only this task's receipts, metadata and tiny-case products."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

root=Path(sys.argv[1]).resolve()
assert (root/'validation.exit').read_text().strip()=='0'
out=root/'evidence'
out.mkdir(exist_ok=False)
for name in ['logs','validation','build-attempt1-logs','cases-cpu','cases-cuda']:
    shutil.copytree(root/name,out/name)
for p in root.iterdir():
    if p.is_file() and (p.suffix in ['.py','.pid','.exit','.done','.json','.log']):
        shutil.copyfile(p,out/p.name)
shutil.copyfile(root/'v2fixtures/MANIFEST.json',out/'fixture-MANIFEST.json')
for kind in ['cpu','cuda']:
    b=root/('build-'+kind)
    d=out/('metadata-'+kind);d.mkdir()
    for name in ['CMakeCache.txt','compile_commands.json','CTestTestfile.cmake']:
        shutil.copyfile(b/name,d/name)
    for name in ['motioncorr_core','motioncorr','cuda_hermitian_inverse','cuda_hermitian_ccf',
                 'cuda_peak_fit','cuda_realspace_border_branch','peak_fit_arithmetic',
                 'hermitian_projection_oracle','realspace_border_validation']:
        flags=b/'CMakeFiles'/(name+'.dir')/'flags.make'
        if flags.is_file():
            shutil.copyfile(flags,d/(name+'-flags.make'))
files=sorted(p for p in out.rglob('*') if p.is_file())
index={str(p.relative_to(out)):dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size)
       for p in files}
archive=root/'native-receipts.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for p in files:
        tar.add(p,arcname=str(p.relative_to(out)))
(root/'native-index.json').write_text(json.dumps(dict(
    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=index),indent=2)+'\n')
print(len(files),'receipt files',archive.stat().st_size,'archive bytes')
