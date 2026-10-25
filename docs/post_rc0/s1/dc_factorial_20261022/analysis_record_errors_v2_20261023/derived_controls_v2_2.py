#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual CLI derived-arithmetic controls. Usage: derived_controls_v2_2.py NEW_ATTEMPT.

Immutable R2 inputs read in place. Restore mutants must lose reports and be
rejected; they do not establish any false numeric motion PASS.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, obj):
    p.write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    target = HERE / 'summarize_v2_2.py'
    pins = json.loads((HERE / 'HARNESS_BINDINGS_v2_2.json').read_text())['original_harness_sha256']
    assert sha(HERE / 'range_controls_v2_1.py') == pins['range_controls_v2_1.py']
    strict_json = load_module('old_strict_parser', HERE / 'range_controls_v2_1.py').strict_json
    generator_pin = json.loads((HERE / 'HARNESS_BINDINGS_v2_1.json').read_text())['original_harness_sha256']['run_controls.py']
    assert sha(HERE / 'run_controls.py') == generator_pin
    gen = load_module('old_fixture_generator', HERE / 'run_controls.py')
    receipt = dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE,text=True).strip(),
                   target_sha256=sha(target), python=sys.executable, python_sha256=sha(Path(sys.executable).resolve()),
                   numeric_threads=1, checks=[], commands=[])
    save(out / 'START.json', {k:v for k,v in receipt.items() if k not in ('checks','commands')})

    def check(name, actual, expected):
        receipt['checks'].append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))

    def run(name, ev, expected_error=True, script=target, mutant=False):
        folder = out / name
        folder.mkdir(exist_ok=False)
        inputs = {p.name:sha(p) for p in sorted((ev/'B').glob('*.json'))}
        argv = [sys.executable,'-B',str(script),str(ev),str(folder/'out')]
        child = subprocess.run(argv,env=ENV,capture_output=True,text=True,timeout=30)
        (folder/'stdout.log').write_text(child.stdout); (folder/'stderr.log').write_text(child.stderr)
        summary, coverage = folder/'out/tierB-v2.json', folder/'out/coverage.md'
        command = dict(name=name,argv=argv,exit=child.returncode,script_sha256=sha(script),inputs=inputs,
                       summary_exists=summary.exists(),coverage_exists=coverage.exists())
        receipt['commands'].append(command)
        check(name+'/immutable-inputs',{p.name:sha(p) for p in sorted((ev/'B').glob('*.json'))},inputs)
        if mutant:
            check(name+'/report-loss',[child.returncode,summary.exists(),coverage.exists()],[1,False,False])
            check(name+'/strict-serialization-mechanism','ValueError: Out of range float' in child.stderr,True)
            command['contract_verdict']='REJECT' if child.returncode!=2 or not summary.exists() or not coverage.exists() else 'ACCEPT'
            check(name+'/mutant-rejected',command['contract_verdict'],'REJECT')
            return None
        check(name+'/exit-and-files',[child.returncode,summary.exists(),coverage.exists()],[2 if expected_error else 0,True,True])
        if not summary.exists():return None
        try:
            result = strict_json(summary)
        except (ValueError,UnicodeError) as exc:
            check(name+'/strict-json',str(exc),'valid strict JSON'); return None
        check(name+'/strict-json',True,True)
        check(name+'/record-inputs-not-relabelled',[(a['status'],a['state'],a['reasons']) for a in result['record_audit']],
              [('EVALUATED','EVALUATED',[])]*20)
        check(name+'/global-input-errors',result['global_error_count'],0)
        for arm in ['none','global']:
            r = next(x for x in result['rows'] if (x['condition'],x['backend'],x['arm'])==('pedestal32','cpu',arm))
            check(name+'/'+arm+'/input-coverage',r['coverage'],dict(expected=10,present=10,evaluated=10,missing=0,unrun=0,error=0))
            check(name+'/'+arm+'/input-counts',[r['n'],r['n_records'],r['error_ids']],[10,10,[]])
        q = next(x for x in result['pairs'] if (x['condition'],x['backend'],x['arm'],x['metric'])==('pedestal32','cpu','global','rms'))
        check(name+'/matched-inputs',[q['pairs'],q['coverage'],q['error_ids']],
              [10,dict(expected=10,matched=10,error=0,missing=0,unrun=0),[]])
        check(name+'/finite-delta-accounting',q['finite_delta_count']+q['unrepresentable_delta_count'],10)
        check(name+'/WLT-accounting',q['wins']+q['losses']+q['ties'],q['finite_delta_count'])
        check(name+'/derived-events-count',len(result['derived_errors']),result['derived_error_count'])
        check(name+'/no-missing-events',all(e['id']==i and e['operation'] in ('cell_median','paired_subtraction','paired_median')
              and bool(e['input_ids']) and bool(e['reason']) for i,e in enumerate(result['derived_errors'])),True)
        check(name+'/no-fabricated-missing-cells',next(r for r in result['rows'] if (r['condition'],r['backend'],r['arm'])==('dose4','cpu','none'))['state'],'UNRUN')
        for a in result['record_audit']:
            check(name+'/audit-hash/'+a['filename_id'],a['sha256'],inputs[Path(a['path']).name])
        if expected_error:
            check(name+'/error-state',[result['state'],q['category']],['EVALUATION_ERROR']*2)
            check(name+'/suppressed-inference',[q['sign_p'],q['failure_mcnemar_p']],[None,None])
            check(name+'/coverage-explains-derived','derived arithmetic errors:' in coverage.read_text() and 'Affected comparisons retain matched INPUT counts' in coverage.read_text(),True)
        else:
            check(name+'/no-derived-errors',result['derived_errors'],[])
            check(name+'/complete-cell',next(r for r in result['rows'] if (r['condition'],r['backend'],r['arm'])==('pedestal32','cpu','global'))['state'],'COMPLETE')
        command['contract_verdict']='ACCEPT' if all(c['passed'] for c in receipt['checks'] if c['name'].startswith(name+'/')) else 'REJECT'
        return result

    retained=HERE/'review-r2-retained'
    cases={}
    for case in strict_json(retained/'BOUNDARY_PROBES.json'):
        ev=retained/'boundary-01'/case['name']/'eval'; cases[case['name']]=ev
        check(case['name']+'/R2-hash-bindings',{p.name:sha(p) for p in sorted((ev/'B').glob('*.json'))},case['inputs'])
        result=run(case['name'],ev)
        if result is None:continue
        q=next(x for x in result['pairs'] if (x['condition'],x['backend'],x['arm'],x['metric'])==('pedestal32','cpu','global','rms'))
        row=next(x for x in result['rows'] if (x['condition'],x['backend'],x['arm'])==('pedestal32','cpu','global'))
        check(case['name']+'/no-selected-cohort-median',q['median_delta'],None)
        if case['name']=='finite-large-median':
            check(case['name']+'/precise-operations',[(e['operation'],e['metric']) for e in result['derived_errors']], [('cell_median','rms'),('paired_median','rms')])
            check(case['name']+'/null-cell-median',[row['median_rms_px'],row['state'],row['derived_error_count']],[None,'EVALUATION_ERROR',1])
            check(case['name']+'/finite-deltas',[q['finite_delta_count'],q['unrepresentable_delta_count']],[10,0])
            check(case['name']+'/cell-blocks-all-own-inference',all(x['category']=='EVALUATION_ERROR' and x['sign_p'] is None and x['failure_mcnemar_p'] is None for x in result['pairs'] if (x['condition'],x['backend'],x['arm'])==('pedestal32','cpu','global')),True)
        else:
            check(case['name']+'/precise-operations',[(e['operation'],e['metric'],e.get('seed')) for e in result['derived_errors']],[('paired_subtraction','rms',0)])
            check(case['name']+'/cell-remains-complete',[row['state'],row['derived_error_count']],['COMPLETE',0])
            check(case['name']+'/finite-deltas',[q['finite_delta_count'],q['unrepresentable_delta_count']],[9,1])
            reg=next(r for r in result['regressions'] if r['metric']=='rms' and r['seed']==0)
            check(case['name']+'/regression-not-lost-or-invented',[reg['none'],reg['arm_value'],reg['delta'],reg['derived_error_id']],[-1e308,1e308,None,0])
            good=next(x for x in result['pairs'] if (x['condition'],x['backend'],x['arm'],x['metric'])==('pedestal32','cpu','global','max'))
            check(case['name']+'/unaffected-comparison',[good['category'],good['sign_p']],['improves',.001953125])

    def fixture(name,change):
        ev=out/'fixtures'/name/'B';ev.mkdir(parents=True,exist_ok=False)
        data=[gen.record(s,a) for s in range(10) for a in ['none','global']]
        change(data)
        for m in data:save(ev/(m['id']+'.json'),m)
        return ev.parent
    def large_pairs(data):
        for m in data:m['truth']['field']['px']['rms']= -5e307 if m['arm']=='none' else 5e307
    pair_ev=fixture('isolated-paired-median',large_pairs)
    result=run('isolated-paired-median',pair_ev)
    if result:
        check('isolated-paired-median/only-pair-operation',[(e['operation'],e['metric']) for e in result['derived_errors']],[('paired_median','rms')])
        check('isolated-paired-median/rows-complete',all(r['state']=='COMPLETE' and r['derived_error_count']==0 for r in result['rows'] if r['condition']=='pedestal32' and r['backend']=='cpu' and r['arm'] in ['none','global']),True)
    def near_boundary(data):
        for m in data:m['truth']['field']['px']['rms']= -1e307 if m['arm']=='none' else 1e307
    result=run('representable-near-boundary',fixture('representable-near-boundary',near_boundary),expected_error=False)
    if result:
        q=next(x for x in result['pairs'] if (x['condition'],x['backend'],x['arm'],x['metric'])==('pedestal32','cpu','global','rms'))
        check('representable-near-boundary/no-clamp',[q['median_delta'],q['category'],q['sign_p']],[2e307,'harms',.001953125])
    def all_medians(data):
        for m in data:
            if m['arm']!='global':continue
            t=m['truth'];t['field']['px'].update(rms=1e308,p95=1e308);t['field']['angstrom']['rms']=1e308
            t['global_trajectory']['px']['rms']=1e308;t['local_component']['px']['rms']=1e308
            m['image']['interior']['transfer_inband']=1e308;m['image']['interior']['bands'][-1]['transfer']=1e308
    result=run('all-cell-median-sites',fixture('all-cell-median-sites',all_medians))
    if result:
        row=next(r for r in result['rows'] if (r['condition'],r['backend'],r['arm'])==('pedestal32','cpu','global'))
        fields=['median_rms_px','median_p95_px','median_rms_A','median_global_rms_px','median_local_rms_px','median_transfer','median_transfer_top']
        check('all-cell-median-sites/seven-sites',[row[k] for k in fields],[None]*7)
        check('all-cell-median-sites/event-count',row['derived_error_count'],7)
    def integer_difference(data):
        for m in data:
            if m['group']=='pedestal32-s00':m['truth']['field']['px']['rms']= -(10**308) if m['arm']=='none' else 10**308
    run('finite-integer-difference',fixture('finite-integer-difference',integer_difference))

    # Separate restorations isolate the four audited derived-value sites.
    source=target.read_text();mutants=out/'mutants';mutants.mkdir(exist_ok=False)
    row_anchor="""med = lambda k: summary_median([x[k] for x in done], derived_errors,
                    dict(operation='cell_median', condition=c, backend=backend, arm=arm,
                         metric=k, input_ids=[x['id'] for x in done]))"""
    delta_anchor="""d = paired_difference(a[metric], b[metric], derived_errors,
                            dict(operation='paired_subtraction', condition=c, backend=backend,
                                 arm=arm, metric=metric, seed=a['seed'], input_ids=[a['id'], b['id']]))"""
    reg_anchor='none=a[metric], arm_value=b[metric], delta=None,'
    median_anchor="""md = (summary_median(deltas, derived_errors,
                        dict(operation='paired_median', condition=c, backend=backend, arm=arm,
                             metric=metric, input_ids=matched_ids)) if all(d is not None for d in deltas) else None)"""
    mutations=[('restore-cell-median',row_anchor,'med = lambda k: st.median([x[k] for x in done]) if done else None',cases['finite-large-median']),
               ('restore-paired-subtraction',delta_anchor,'d = b[metric] - a[metric]',cases['finite-large-difference']),
               ('restore-regression-emission',reg_anchor,'none=a[metric], arm_value=b[metric], delta=b[metric] - a[metric],',cases['finite-large-difference']),
               ('restore-paired-median',median_anchor,'md = st.median(deltas) if deltas and all(d is not None for d in deltas) else None',pair_ev)]
    for name,anchor,replacement,ev in mutations:
        assert source.count(anchor)==1,name
        script=mutants/(name+'.py');script.write_text(source.replace(anchor,replacement))
        run(name,ev,script=script,mutant=True)
    receipt['result']='PASS' if all(c['passed'] for c in receipt['checks']) else 'FAIL'
    save(out/'DERIVED_CONTROLS.json',receipt)
    print(json.dumps(dict(result=receipt['result'],checks=len(receipt['checks']),failures=[c for c in receipt['checks'] if not c['passed']])))
    return 0 if receipt['result']=='PASS' else 1


if __name__=='__main__':
    sys.exit(main())
