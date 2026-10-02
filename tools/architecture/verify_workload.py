#!/usr/bin/env python3
"""Audit retained matrix associations and native execution, without recomputing."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compare_motioncorr import parse_star_file

root=Path(sys.argv[1]).resolve()
cases=json.loads((root/'cases.json').read_text())
results=json.loads((root/'results.json').read_text())
gpu=json.loads((root/'provenance.json').read_text())['gpu']
if len(cases)!=49 or {(r['profile'],r['arm']) for r in results}!={
        ('mixed','float'),('mixed','auto'),('mixed','reverse'),
        ('gain_defect','float'),('gain_defect','auto')} or len(results)!=5:
    raise ValueError('incomplete fixed experiment matrix')
checked=0
for result in results:
    out=root/(result['profile']+'-'+result['arm'])
    selected=cases if result['profile']=='mixed' else [c for c in cases if c['nx']==256]
    aggregate=parse_star_file(out/'corrected_micrographs.star')
    table=aggregate['micrographs']
    if len(table['rows'])!=len(selected): raise ValueError('aggregate count differs')
    rows=[dict(zip(table['labels'],r)) for r in table['rows']]
    mapping={r['_rlnMicrographMetadata']:r for r in rows}
    if len(mapping)!=len(selected): raise ValueError('duplicate aggregate association')
    optics=aggregate['optics']
    groups={int(r[optics['labels'].index('_rlnOpticsGroup')]):dict(zip(optics['labels'],r))
            for r in optics['rows']}
    for c in selected:
        stem=str(Path(c['path']).with_suffix('')).replace('.','_')
        meta=out/(stem+'.star')
        fields=parse_star_file(meta)['general']['fields']
        expected={'_rlnImageSizeX':c['nx'],'_rlnImageSizeY':c['ny'],'_rlnImageSizeZ':c['frames'],
                  '_rlnMicrographOriginalPixelSize':1 if c['optics']==1 else 1.5,
                  '_rlnVoltage':300 if c['optics']==1 else 200}
        if fields['_rlnMicrographMovieName']!=c['path'] or any(float(fields[k])!=v for k,v in expected.items()):
            raise ValueError('per-movie association or physical metadata differs')
        row=mapping[str(meta)]
        if int(row['_rlnOpticsGroup'])!=c['optics']: raise ValueError('wrong aggregate optics group')
        for label,suffix in [('_rlnMicrographName','.mrc'),('_rlnMicrographNameNoDW','_noDW.mrc')]:
            if row[label]!=str(out/(stem+suffix)): raise ValueError('wrong aggregate image association')
        group=groups[c['optics']]
        if float(group['_rlnMicrographPixelSize'])!=expected['_rlnMicrographOriginalPixelSize'] or float(group['_rlnVoltage'])!=expected['_rlnVoltage']:
            raise ValueError('wrong aggregate physical metadata')
        log=(out/(stem+'.log')).read_text()
        if gpu and ('Fourier transforms (CUDA in-VRAM)' not in log or
                    re.search(r'failed|falling back|CUDA Error',log,re.I)):
            raise ValueError('missing resident CUDA execution or failure present')
        checked+=1
print(json.dumps(dict(verdict='PASS',movie_associations=checked,
                     native_resident_movies=checked if gpu else 0,profiles=len(results)),indent=2))
