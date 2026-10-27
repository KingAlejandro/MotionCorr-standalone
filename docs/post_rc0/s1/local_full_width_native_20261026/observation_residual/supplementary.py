"""POST-FREEZE arithmetic on observation_residual.json (not a frozen quantity, no gate): concentration shares, eta/H ratios, and which patches/frames increase ON versus OFF."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
D = json.loads((Path(sys.argv[1]) / 'observation_residual.json').read_text())
out = ['# Supplementary arithmetic (computed after the freeze from the frozen outputs; descriptive, no gate)\n']
out.append('| case/arm | patch with largest eta RMS (g1-4) | its share of sum of eta^2 (g1-4) | eta RMS / H RMS per frame g1..g4 |')
out.append('|---|---|---|---|')
for k, e in D['cases'].items():
    tot = sum(r['norm'] ** 2 for r in e['rank_eta_g1_4']); top = e['rank_patch_eta_rms'][0]['patch']
    sh = sum(r['norm'] ** 2 for r in e['rank_eta_g1_4'] if r['patch'] == top) / tot
    ratio = ' / '.join('%.3f' % (e['eta_block']['per_frame'][str(g)]['rms'] / e['H_block']['per_frame'][str(g)]['rms']) for g in range(1, 5))
    out.append(f'| {k} | ({top[0]},{top[1]}) | {sh:.3f} | {ratio} |')
out.append('\nPatches whose g=1..4 RMS is larger with full-width ON than with OFF (frames with larger RMS ON: none in every listed quantity unless shown):\n')
for c, ch in D['arm_changes'].items():
    for q in ('eta', 'e_tr', 'fit:native_runtime_coeff', 'fit:legacy_coeff', 'fit:B2_coeff'):
        up = [(tuple(o['patch']), round(o['rms_OFF_g1_4'], 4), round(o['rms_ON_g1_4'], 4)) for o in ch[q]['per_patch'] if o['rms_ON_g1_4'] > o['rms_OFF_g1_4']]
        fr = [g for g in range(1, 5) if ch[q]['per_frame'][str(g)]['rms_ON'] > ch[q]['per_frame'][str(g)]['rms_OFF']]
        out.append(f'- {c} {q}: patches (patch, OFF, ON) {up or "none"}; frames {fr or "none"}')
(Path(sys.argv[1]) / 'SUPPLEMENTARY.md').write_text('\n'.join(out) + '\n'); print('\n'.join(out))
