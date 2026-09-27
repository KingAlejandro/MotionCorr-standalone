#!/usr/bin/env python3
"""Require native resident global, local and dose-weighted stages for all movies."""
import json
import sys
from pathlib import Path

def witness(root):
    logs = sorted((Path(root) / 'Movies').glob('*.log'))
    rows=[]
    for log in logs:
        text=log.read_text(errors='replace')
        checks={
            'resident_fft': 'Computing full-frame Fourier transforms (CUDA in-VRAM)' in text,
            'global_completed': '[CUDA Global Alignment] completed' in text,
            'resident_reconstruction': 'Reconstructing globally aligned frames (CUDA in-VRAM)' in text,
            'local_completed': text.count('[CUDA Patch Alignment] completed') == 25,
            'resident_dose_dispatch': 'Dose weighting and summing frames (CUDA in-VRAM)' in text,
            'resident_dose_profile': '[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]' in text,
            'no_fallback_warning': 'falling back' not in text.lower() and 'fallback' not in text.lower(),
        }
        rows.append({'movie':log.stem,'checks':checks,'pass':all(checks.values())})
    return {'rows':rows,'movies':len(rows),'pass':len(rows)==24 and all(r['pass'] for r in rows)}
if __name__=='__main__':
    r=witness(sys.argv[1]); print(json.dumps(r,indent=2)); sys.exit(0 if r['pass'] else 1)
