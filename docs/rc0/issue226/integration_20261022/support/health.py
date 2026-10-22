"""Fail-closed GPU3 resource guard. New scratch only; no foreign PID signalling."""
import itertools, json, os, signal, subprocess, time, xml.etree.ElementTree as ET
from pathlib import Path
W = Path('/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z')
UUID = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
OWNED = {}
SAMPLES=itertools.count()

def identity(pid):
    p = Path('/proc') / str(pid)
    stat = (p/'stat').read_text().split(') ', 1)[1].split()
    return {'starttime': stat[19], 'cmdline': (p/'cmdline').read_bytes().hex(),
            'pgid': os.getpgid(pid)}

def remember(p):
    OWNED[p.pid] = identity(p.pid)
    with (W/'logs/owned-processes.jsonl').open('a') as f:
        f.write(json.dumps({'pid': p.pid, **OWNED[p.pid]})+'\n')

def stop_owned(p, sig=signal.SIGTERM):
    if p.poll() is not None:
        p.wait(); return
    saved = OWNED[p.pid]
    current = identity(p.pid)
    if saved != current or current['pgid'] != p.pid:
        raise RuntimeError(f'own process identity changed: {p.pid}')
    os.killpg(p.pid, sig)
    try: p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if identity(p.pid) != saved: raise RuntimeError('PID changed before escalation')
        os.killpg(p.pid, signal.SIGKILL); p.wait(timeout=10)
    with (W/'logs/owned-processes.jsonl').open('a') as f:
        f.write(json.dumps({'reaped_pid':p.pid, 'exit':p.returncode})+'\n')

def snapshot(label, idle=False):
    r = subprocess.run(['nvidia-smi','-i',UUID,'-q','-x'],capture_output=True,text=True,check=True)
    g=ET.fromstring(r.stdout).find('gpu')
    sample_index=next(SAMPLES)
    (W/'logs'/f'health-{os.getpid()}-{sample_index:04d}.xml').write_text(r.stdout)
    def text(p):
        e=g.find(p)
        if e is None or e.text is None: raise RuntimeError('missing GPU health field '+p)
        return e.text.strip()
    rec={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()), 'label':label,
         'uuid':text('uuid'), 'name':text('product_name'),
         'recovery_action':text('gpu_recovery_action'),
         'memory_used':text('fb_memory_usage/used'), 'util':text('utilization/gpu_util'),
         'volatile_ecc':{e.tag:e.text.strip() for e in g.findall('ecc_errors/volatile/*') if 'correctable' in e.tag},
         'aggregate_ecc':{e.tag:e.text.strip() for e in g.findall('ecc_errors/aggregate/*') if 'correctable' in e.tag},
         'remapped':{e.tag:e.text.strip() for e in g.findall('remapped_rows/*') if len(e)==0},
         'retired_pending':text('retired_pages/pending_blacklist'),
         'apps':[int(e.text) for e in g.findall('processes/process_info/pid')]}
    with (W/'logs/health.jsonl').open('a') as f: f.write(json.dumps(rec)+'\n')
    if label.endswith('pre') or label.endswith('post'):
        (W/'logs'/f'{label}.xml').write_text(r.stdout)
    if rec['uuid']!=UUID or rec['name']!='NVIDIA A100 80GB PCIe':
        raise RuntimeError('GPU identity mismatch')
    if rec['recovery_action']!='None': raise RuntimeError('GPU recovery action required')
    # Inspect every numeric ECC/retired-page leaf, not just summary counters.
    for section in ('ecc_errors','retired_pages'):
        node=g.find(section)
        if node is None: raise RuntimeError('missing health section '+section)
        for leaf in node.iter():
            value=(leaf.text or '').strip()
            if len(leaf)==0 and value.isdigit() and int(value):
                raise RuntimeError('nonzero hardware health count '+leaf.tag+'='+value)
    retired=g.findtext('retired_pages/pending_retirement')
    if retired not in ('No','N/A'): raise RuntimeError('retired page retirement pending')
    health={k:ET.tostring(g.find(k),encoding='unicode') for k in
            ('ecc_errors','retired_pages','remapped_rows')}
    baseline=W/'logs/health-baseline.json'
    if baseline.exists():
        if health!=json.loads(baseline.read_text()): raise RuntimeError('GPU health changed')
    else: baseline.write_text(json.dumps(health,indent=2)+'\n')
    if not rec['volatile_ecc'] or not rec['aggregate_ecc']: raise RuntimeError('missing ECC counts')
    if any(int(v) for values in (rec['volatile_ecc'],rec['aggregate_ecc']) for v in values.values()):
        raise RuntimeError('GPU ECC error')
    rows=rec['remapped']
    if rows.get('remapped_row_unc')!='0' or rows.get('remapped_row_corr')!='0' or rows.get('remapped_row_pending')!='No' or rows.get('remapped_row_failure')!='No':
        raise RuntimeError('GPU row remap error/pending or unrecognized fields: '+str(rows))
    if rec['retired_pending'] not in ('No','N/A'): raise RuntimeError('retired page pending')
    for pid in rec['apps']:
        try: pgid=os.getpgid(pid)
        except ProcessLookupError: continue
        if not any(pgid == own for own in OWNED): raise RuntimeError(f'foreign GPU process {pid}')
    if idle and (rec['apps'] or int(rec['memory_used'].split()[0])>8 or rec['util']!='0 %'):
        raise RuntimeError('GPU not idle: '+str(rec))
    return rec

def settle(label):
    # Predefined post-utilization settling only: at most 20 one-second samples.
    # Every sample independently checks identity/ECC/row-remap/errors and foreign apps.
    for i in range(20):
        rec=snapshot(label+f'-sample-{i}')
        if rec['apps'] or int(rec['memory_used'].split()[0])>8:
            raise RuntimeError('post-health has apps or abnormal memory; no settling waiver')
        if not rec['apps'] and int(rec['memory_used'].split()[0])<=8 and rec['util']=='0 %':
            return snapshot(label+'-post',idle=True)
        time.sleep(1)
    raise RuntimeError('GPU did not release/settle within 20 samples')
