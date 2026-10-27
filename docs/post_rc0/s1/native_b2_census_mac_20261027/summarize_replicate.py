#!/usr/bin/env python3
"""Report the frozen five-arm Mac replicate; never alter or rerun producers."""
import csv
import hashlib
import json
from pathlib import Path
import sys
from scipy.stats import binomtest

LABEL = 'Mac replicate census, not hash-identical to the frozen census'
ARMS = ['OFF', 'B2', 'UP', 'UPFW', 'FW']
PAIRS = [('B2', 'OFF'), ('FW', 'OFF'), ('UPFW', 'UP'), ('UP', 'OFF')]
FIELDS = ['runtime', 'STAR']


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def exact_p(wins, losses):
    return float(binomtest(wins, wins + losses, .5).pvalue) if wins + losses else 1.0


def summarize(rows):
    result = dict(n=len(rows), pass_counts={}, comparisons={})
    for field in FIELDS:
        result['pass_counts'][field] = {arm: sum(r['arms'][arm][field + '_gate'] == 'PASS'
                                               for r in rows) for arm in ARMS}
    for candidate, baseline in PAIRS:
        key = candidate + '_vs_' + baseline
        result['comparisons'][key] = {}
        for field in FIELDS:
            wins = sum(r['arms'][candidate][field]['rms'] < r['arms'][baseline][field]['rms'] for r in rows)
            losses = sum(r['arms'][candidate][field]['rms'] > r['arms'][baseline][field]['rms'] for r in rows)
            rescues = [r['movie'] for r in rows if r['arms'][candidate][field + '_gate'] == 'PASS'
                       and r['arms'][baseline][field + '_gate'] == 'FAIL']
            regressions = [r['movie'] for r in rows if r['arms'][candidate][field + '_gate'] == 'FAIL'
                           and r['arms'][baseline][field + '_gate'] == 'PASS']
            result['comparisons'][key][field] = dict(
                lower_RMS=wins, higher_RMS=losses, ties=len(rows) - wins - losses,
                two_sided_exact_RMS_sign_p=exact_p(wins, losses),
                rescues=rescues, pass_to_fail=regressions,
                discordant_pass_sign_p=exact_p(len(rescues), len(regressions)))
    return result


def table(headers, rows):
    return '| ' + ' | '.join(headers) + ' |\n|' + '|'.join('---' for _ in headers) + '|\n' + ''.join(
        '| ' + ' | '.join(str(v) for v in row) + ' |\n' for row in rows)


def main():
    work = Path(sys.argv[1]).resolve()
    census = json.loads((work / 'census.json').read_text())
    rows = census['movies']
    assert census['completed'] == len(rows) == 100
    assert len({r['movie'] for r in rows}) == 100
    assert (work / 'COMPLETE.json').exists() and not (work / 'STOP.json').exists()
    for row in rows:
        assert set(row['arms']) == set(ARMS)
        for arm in ARMS:
            assert row['arms'][arm]['native_exit'] == row['arms'][arm]['score_exit'] == 0
    out = work / 'report'
    out.mkdir(exist_ok=False)
    refs = json.loads((work / 'frozen_reference.json').read_text())['movies']
    groups = dict(all_100=rows, in_model_80=[r for r in rows if r['in_model']],
                  remaining_20=[r for r in rows if not r['in_model']],
                  outmodel_10=[r for r in rows if r['condition'] == 'outmodel'],
                  pedestal32_no_local_10=[r for r in rows if r['condition'] == 'pedestal32'])
    for key in ['all_100', 'in_model_80', 'remaining_20']:
        for flag in [False, True]:
            groups[key + ('_P6_flagged' if flag else '_P6_unflagged')] = [
                r for r in groups[key] if r['P6']['flagged'] == flag]
    summaries = {key: summarize(value) for key, value in groups.items()}
    p5 = {}
    for field in FIELDS:
        flips = []
        for r in rows:
            old, new = refs[r['movie']][field + '_gate'], r['arms']['OFF'][field + '_gate']
            if old != new:
                flips.append(dict(movie=r['movie'], frozen_OFF=old, Mac_OFF=new,
                                  in_model=r['in_model'], P6_flagged=r['P6']['flagged'],
                                  frozen_metrics=refs[r['movie']][field], Mac_metrics=r['arms']['OFF'][field]))
        p5[field] = dict(agree=100 - len(flips), denominator=100, flips=flips,
                         threshold='No acceptance threshold; descriptive agreement count',
                         by_group={key: dict(agree=sum(refs[r['movie']][field + '_gate'] == r['arms']['OFF'][field + '_gate'] for r in group), n=len(group)) for key, group in groups.items()})
    flagged = [r['movie'] for r in rows if r['P6']['flagged']]
    p6 = dict(flagged_count=len(flagged), flagged_movies=flagged,
              total_different=[r['movie'] for r in rows if r['P6']['total_difference'] != 0],
              squared_difference_exceeds_1000=[r['movie'] for r in rows if abs(r['P6']['squared_sum_difference']) > 1000],
              maximum_abs_total_difference=max(abs(r['P6']['total_difference']) for r in rows),
              maximum_abs_squared_sum_difference=max(abs(r['P6']['squared_sum_difference']) for r in rows))
    regressions = []
    for candidate, baseline in PAIRS:
        for r in rows:
            for field in FIELDS:
                for metric in ['rms', 'p95', 'max']:
                    a, b = r['arms'][baseline][field][metric], r['arms'][candidate][field][metric]
                    if b > a:
                        regressions.append(dict(movie=r['movie'], pair=candidate + '_vs_' + baseline,
                            field=field, metric=metric, baseline=a, candidate=b, delta=b-a,
                            P6_flagged=r['P6']['flagged']))
    write(out / 'metric_regressions.json', regressions)
    with (out / 'metric_regressions.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['movie', 'pair', 'field', 'metric', 'baseline', 'candidate', 'delta', 'P6_flagged'])
        writer.writeheader()
        writer.writerows(regressions)
    with (out / 'P6_moments.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['movie', 'condition', 'in_model', 'P6_flagged', 'Mac_total', 'frozen_total', 'delta_total', 'Mac_squared_sum', 'frozen_squared_sum', 'delta_squared_sum', 'Mac_Poisson_total', 'frozen_Poisson_total', 'Mac_Poisson_squared_sum', 'frozen_Poisson_squared_sum'])
        for r in rows:
            p = r['P6']
            writer.writerow([r['movie'], r['condition'], r['in_model'], p['flagged'], p['Mac']['total'], p['frozen']['total'], p['total_difference'], p['Mac']['squared_sum'], p['frozen']['squared_sum'], p['squared_sum_difference'], p['Mac']['underlying_Poisson_total'], p['frozen']['underlying_Poisson_total'], p['Mac']['underlying_Poisson_squared_sum'], p['frozen']['underlying_Poisson_squared_sum']])
    time_rows = []
    with (out / 'per_movie.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        columns = ['movie', 'condition', 'in_model', 'P6_flagged', 'movie_sha256']
        columns += [arm + '_' + key for arm in ARMS for key in ['runtime_gate', 'STAR_gate', 'runtime_rms_A', 'runtime_p95_A', 'runtime_max_A', 'STAR_rms_A', 'STAR_p95_A', 'STAR_max_A', 'wall_seconds']]
        writer.writerow(columns)
        for r in rows:
            values = [r['movie'], r['condition'], r['in_model'], r['P6']['flagged'], r['movie_sha256']]
            for arm in ARMS:
                a = r['arms'][arm]
                values += [a['runtime_gate'], a['STAR_gate'], *[a['runtime'][m] for m in ['rms', 'p95', 'max']], *[a['STAR'][m] for m in ['rms', 'p95', 'max']], a['seconds']]
            writer.writerow(values)
            time_rows.append([r['movie'], 'yes' if r['P6']['flagged'] else 'no', *[f"{r['arms'][a]['seconds']:.6f}" for a in ARMS]])
    (out / 'timings.md').write_text('# ' + LABEL + '\n\nWhole-job wall seconds, one run per arm, fixed order OFF, B2, UP, UPFW, FW. First movie additionally ran the second-binary identity arm after OFF. Descriptive only; no speedup claim. Timings include `/usr/bin/time -l`, process startup and publication/exit; exclude generation and scoring.\n\n' + table(['Movie', 'P6 flagged', *ARMS], time_rows))
    timing = {}
    for arm in ARMS:
        times = sorted(r['arms'][arm]['seconds'] for r in rows)
        timing[arm] = dict(n=len(times), mean_seconds=sum(times)/len(times),
                          median_seconds=(times[49]+times[50])/2,
                          min_seconds=times[0], max_seconds=times[-1])
    im = summaries['in_model_80']
    verdicts = dict(P1='UNTESTABLE on replicate inputs',
        P2={f: im['pass_counts'][f]['B2'] > im['pass_counts'][f]['OFF'] for f in FIELDS},
        P3='REPORTED: every pass-to-fail and every metric regression is listed',
        P4='REPORTED: descriptive timings only', P5=p5,
        P6=dict(status='REPORTED separately, without changing the frozen rule', **p6),
        Q1={f: im['comparisons']['FW_vs_OFF'][f] for f in FIELDS},
        Q2={f: im['pass_counts'][f]['FW'] >= im['pass_counts'][f]['OFF'] for f in FIELDS},
        Q3='REPORTED: all OFF-pass/FW-fail and UP-pass/UPFW-fail listed',
        Q4={f: dict(comparison=im['comparisons']['UPFW_vs_UP'][f],
                    pass_count_at_least_UP=im['pass_counts'][f]['UPFW'] >= im['pass_counts'][f]['UP']) for f in FIELDS})
    result = dict(label=LABEL, native_producers=501, main_arm_producers=500, all_native_and_score_exits=0,
                  groups=summaries, predictions=verdicts, timing=timing,
                  conditions={c: summarize([r for r in rows if r['condition'] == c]) for c in sorted({r['condition'] for r in rows})},
                  sampling_failures=[dict(movie=r['movie'], arm=a, sampling=r['arms'][a]['sampling']) for r in rows for a in ARMS if r['arms'][a]['sampling'] != 'VALID'],
                  pair_global_differences=[dict(movie=r['movie'], pairs=r['pair_globals_identical']) for r in rows if not all(r['pair_globals_identical'].values())],
                  regression_metric_rows=len(regressions))
    write(out / 'summary.json', result)
    write(out / 'P5_agreement.json', p5)
    write(out / 'P6_flagged.json', [r for r in rows if r['P6']['flagged']])
    for pair in [c + '_vs_' + b for c, b in PAIRS]:
        reg_rows = []
        for r in rows:
            values = []
            for field in FIELDS:
                a = [x for x in regressions if x['pair'] == pair and x['movie'] == r['movie'] and x['field'] == field]
                values.append('; '.join(f"{x['metric']}: {x['baseline']:.12g} → {x['candidate']:.12g}" for x in a) or 'none')
            if any(v != 'none' for v in values):
                reg_rows.append([r['movie'], r['P6']['flagged'], *values])
        (out / (pair + '_regressions.md')).write_text('# ' + LABEL + '\n\nEvery strict RMS/p95/max increase, Å; no regression tolerance applied.\n\n' + table(['Movie', 'P6 flagged', 'Runtime increases', 'Actual STAR increases'], reg_rows))
    score_rows = []
    for c, group in result['conditions'].items():
        score_rows.append([c, *[str(group['pass_counts']['runtime'][a]) + '/' + str(group['pass_counts']['STAR'][a]) for a in ARMS]])
    (out / 'conditions.md').write_text('# ' + LABEL + '\n\nPasses of 10; runtime/actual STAR.\n\n' + table(['Condition', *ARMS], score_rows))
    print(json.dumps(dict(groups={k: v['pass_counts'] for k, v in summaries.items()}, P6=p6,
                          P5={f: p5[f]['agree'] for f in FIELDS}, timing=timing), indent=2))


if __name__ == '__main__':
    main()
