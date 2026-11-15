#!/usr/bin/env python3
"""Summarize retained standalone characterization; no acceptance thresholds."""
import csv, json
from pathlib import Path
root = Path(__file__).resolve().parent
lines = (root/'injection.csv').read_text().splitlines()
rows = list(csv.DictReader(lines[1:]))
assert len(rows) == 112, len(rows)
result = {}
for row in rows:
    key = f"{row['nx']}x{row['ny']}"
    entry = result.setdefault(key, {})
    entry.setdefault(row['plan'], {})[row['injection']] = {
        key: float(value) for key, value in row.items()
        if key not in ('nx','ny','plan','injection')
    }
(root/'injection-summary.json').write_text(json.dumps(result, indent=2)+'\n')
text = ['| Width × height | Nyquist: constant | DC: alternating | Both: constant, alternating | Four corners: active coefficient | Maximum fitted residual RMS |',
        '|---|---:|---:|---|---|---:|']
for size, plans in result.items():
    p = plans['many']
    both = p['both']
    corners = [p[name]['const_coefficient' if name.startswith('nyquist') else 'alternating_coefficient'] for name in ('nyquist_corner','dc_corner','nyquist_ycorner','dc_ycorner')]
    text.append(f"| {size.replace('x',' × ')} | {p['nyquist']['const_coefficient']:.9g} | {p['dc']['alternating_coefficient']:.9g} | {both['const_coefficient']:.9g}, {both['alternating_coefficient']:.9g} | {', '.join(f'{c:.9g}' for c in corners)} | {max(r['residual_rms'] for r in p.values()):.3g} |")
(root/'injection-table.md').write_text('\n'.join(text)+'\n')
print('\n'.join(text))
