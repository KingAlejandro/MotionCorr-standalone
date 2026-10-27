"""Render RESULT_TABLES.md from the sealed stage-1 and the stage-2 JSON only (no new computation)."""
import json
from pathlib import Path
W = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1')
s1 = json.loads((W / 'out/stage1_fit.json').read_text()); s2 = json.loads((W / 'out/stage2_result.json').read_text())
LIM = ('rms', 'p95', 'max'); f = lambda a: ' / '.join('%.4f' % a[k] for k in LIM)
L = ['# B2 cross-feed offline screen: result tables (generated from out/stage1_fit.json and out/stage2_result.json)\n',
     f"**Status: {s2['status']}** (never an acceptance). Primary criterion met: {s2['primary']['all_six_identifiable_pass_both_fields']}; five original passes retained: {s2['primary']['five_original_passes_retained']}. Control reproduced: {s2['control_ok']}.\n",
     '## Stage 1 checks (sealed before truth)\n', '| check | pass |', '|---|---|'] + [f'| {k} | {v} |' for k, v in s1['checks'].items()]
L += ['\n## Rank / conditioning per local observation set (arms: legacy "native", B1, B2, C)\n', '| set | patches | arm | rank / columns | raw min sv | raw max sv | raw cond | scaled cond | spatial rank | distinct times |', '|---|---|---|---|---|---|---|---|---|---|']
for k, v in s1['native'].items():
    if v['status'] != 'LOCAL': continue
    for arm, c in v['conditioning'].items():
        L.append(f"| {k} | {v['n_patches']} | {arm} | {c['fit_rank']} / {c['fit_n_cols']} | {c['raw_min']:.4g} | {c['raw_max']:.4g} | {c['raw_cond']:.4g} | {c['scaled_cond']:.4g} | {c['spatial_rank']} | {c['distinct_times_per_patch']} |")
L += ['\n## Replay, equivalence, h(0) (fixed ceiling 0.01313142874082845 px; equivalence bound 1e-9 px)\n', '| set | legacy replay vs native runtime (field max px) | legacy coeff max abs diff | B1 vs B2 / C vs B2 (px) | h(0) exactly 0 (B1,B2,C) |', '|---|---|---|---|---|']
for k, v in s1['native'].items():
    if v['status'] != 'LOCAL': continue
    L.append(f"| {k} | {v['legacy_replay_field_max_px']:.3e} | {v['legacy_replay_coeff_max_abs']:.3e} | {v['equivalence_B1_vs_B2_max_px']:.2e} / {v['equivalence_C_vs_B2_max_px']:.2e} | {v['h0_B1_exactly_zero']}, {v['h0_B2_exactly_zero']}, {v['h0_C_exactly_zero']} |")
L += ['\n## Old-harm control: B2 on the old-weight observations vs retained native UP_B2\n', '| case | B2 projection vs native UP_B2 field (px) | offline B2 old weight R-rt (A) | retained native UP_B2 (A) | retained UP_only (A) | abs diff to UP_B2 (A) |', '|---|---|---|---|---|---|']
for c, v in s2['control'].items():
    L.append(f"| {c} | {s1['controls'][c]['B2_projection_of_UP_only_obs_vs_native_UP_B2_field_max_px']:.3e} | {f(v['offline_B2_old_weight_R_rt'])} ({v['gate_offline']}) | {f(v['retained_native_UP_B2'])} ({v['gate_retained_UP_B2']}) | {f(v['retained_native_UP_only'])} | {max(v['abs_diff_A'].values()):.2e} |")
L += ['\n## Full score table (A; RMS / p95 / max; limits .20 / .40 / .80)\n', 'Native columns are actual measured fields; offline columns are counterfactual. R-rt = runtime G + full-precision refit coefficients; R-hyb = STAR read-back G + the same coefficients (hybrid, not a serialised refit).\n',
      '| case | field | native OFF | native ON | legacy OFF (offline) | legacy ON (offline) | B2 OFF | B2 + full-width |', '|---|---|---|---|---|---|---|---|']
for c in ('noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated'):
    for g, nat in (('rt', 'runtime'), ('hyb', 'STAR')):
        row = [f"{f(s2['native'][c + '/' + a][nat])} {s2['native'][c + '/' + a][nat + '_gate']}" for a in ('OFF', 'ON')]
        for a, fit in (('OFF', 'legacy'), ('ON', 'legacy'), ('OFF', 'B2'), ('ON', 'B2')):
            e = s2['offline'][f'{c}/{a}/{fit}/R_{g}']; row.append(f"{f(e['angstrom'])} {e['gate']}")
        L.append(f"| {c}{' (UNIDENTIFIABLE)' if c in ('flat', 'repeated') else ''} | R-{g} | " + ' | '.join(row) + ' |')
L += ['\n## Directional diagnostic (noisy B2 + full-width vs the measured native legacy full-width field)\n']
for k, v in s2['directional_noisy'].items():
    L.append(f"- {k}: " + ', '.join(f"{m} {d['native_legacy_fullwidth']:.4f} -> {d['B2_fullwidth']:.4f} ({'improves' if d['improves'] else 'TIE' if d['tie'] else 'REGRESSES'})" for m, d in v.items()))
L += ['\nStill FAIL against the unchanged limits (noisy B2 + full-width): ' + f"R-rt {f(s2['offline']['noisy/ON/B2/R_rt']['angstrom'])}; R-hyb {f(s2['offline']['noisy/ON/B2/R_hyb']['angstrom'])}.\n",
      f"## Every metric increase of B2 + full-width (all cases, both fields, vs native ON and vs native OFF; PASS->PASS included): {len(s2['increases_B2_fullwidth'])}\n"]
for i in s2['increases_B2_fullwidth']:
    L.append(f"- {i['case']} {i['field']} {i['metric']} vs {i['versus']}: {i['native']:.4f} -> {i['B2_fullwidth']:.4f} A ({i['gate_transition']})")
ms = [k for k, v in s2['offline'].items() if v['margin_sensitive_metrics'] and '/ON/B2/' in k]
L += [f"\nMargin-sensitive (within 0.01313142874082845 x .885 = {s2['environment']['margin_A']:.5f} A of a limit) B2 + full-width comparisons: {ms or 'none'}.", '']
(W / 'RESULT_TABLES.md').write_text('\n'.join(L))
