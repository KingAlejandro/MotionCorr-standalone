#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hash-index all fresh arrays/products remotely; package compact receipts only."""
import datetime,hashlib,json,pathlib,sys,tarfile
r=pathlib.Path(sys.argv[1]);index={}
for p in sorted(r.rglob('*')):
    if p.is_file() and p.relative_to(r).parts[0] not in ['build-cpu','build-cuda','src'] and p.suffix not in ['.gz'] and p.name not in ['file-index.json','receipt-index.json']:
        data=p.read_bytes();index[str(p.relative_to(r))]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
(r/'file-index.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=index),indent=2)+'\n')
names=[]
for p in sorted(r.rglob('*')):
    if not p.is_file():continue
    name=str(p.relative_to(r));parts=p.relative_to(r).parts
    if (len(parts)==1 and (p.suffix=='.py' or p.name.startswith('direct-witness'))) or name in ['fixture-spectral-identities.json','verification.json','witnesses.json','trajectories.json','analysis-first-reconciliation.json','analysis-verification.json','analysis-verification.exit','analysis-verification.pid','analysis-verification.log','analysis-final-receipt.json','analysis-final.exit','analysis-final.pid','analysis-final.log','file-index.json','neutrality.json','controls.json','binaries.json','campaign.json','build.pid','build.exit','build-driver.log','build-reconciliation.json','run.pid','run.exit','run-driver.log','analysis.pid','analysis.exit','analysis.log','analysis-summary.json','source-binding.json','overlay-binding.json','DESIGN.md','fixture-MANIFEST.json']:
        names.append(name)
    elif parts[0] in ['run-logs','build-logs'] and p.name!='compile_commands.json':names.append(name)
    elif parts[0]=='runs' and (p.suffix in ['.json','.txt','.log','.star'] or p.name.endswith('.json')):names.append(name)
    elif parts[0] in ['build-cpu','build-cuda'] and (p.name=='CMakeCache.txt' or p.name=='flags.make' or p.name=='link.txt'):names.append(name)
with tarfile.open(r/'receipts.tar.gz','w:gz') as t:
    for name in names:t.add(r/name,arcname=name)
meta=dict(archive='receipts.tar.gz',archive_sha256=hashlib.sha256((r/'receipts.tar.gz').read_bytes()).hexdigest(),files={name:dict(bytes=(r/name).stat().st_size,sha256=hashlib.sha256((r/name).read_bytes()).hexdigest()) for name in names},raw_arrays_products='remain in '+str(r),array_product_index_sha256=hashlib.sha256((r/'file-index.json').read_bytes()).hexdigest())
(r/'receipt-index.json').write_text(json.dumps(meta,indent=2)+'\n');print(len(names),'receipts',meta['archive_sha256'])
