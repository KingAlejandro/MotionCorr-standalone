import json,re,sys,xml.etree.ElementTree as ET,collections,hashlib
d=sys.argv[1]
exp=json.load(open(d+'/expected_collection.json'))
out={}
for cfg in ('cpu','cuda','nvcomp'):
    x=ET.parse(f'{d}/ctest-{cfg}.junit.xml').getroot()
    ts=x if x.tag=='testsuite' else x.find('testsuite')
    attrs=dict(ts.attrib)
    cases=ts.findall('testcase')
    names=[c.get('name') for c in cases]
    dup=[n for n,c in collections.Counter(names).items() if c>1]
    st={}
    for c in cases:
        s=c.get('status')
        kids=[k.tag for k in c]
        st[c.get('name')]=(s,kids,float(c.get('time') or 0))
    bad={n:v for n,v in st.items() if v[0]!='run' or any(k in ('failure','error','skipped') for k in v[1])}
    log=open(f'{d}/ctest-{cfg}.log').read()
    listing=re.findall(r'^\s+Test\s+#\d+:\s+(\S+)\s*$',log,re.M)
    e=exp['cfg'][cfg]
    eset=set(e['expected'] if isinstance(e,dict) and 'expected' in e else e) if not isinstance(e,dict) or 'expected' in e else None
    out[cfg]=dict(attrs=attrs,n=len(names),dup=dup,bad=bad,listing=len(listing),listing_eq_junit=set(listing)==set(names),
       expected_keys=list(e.keys()) if isinstance(e,dict) else type(e).__name__,
       expected_eq_junit=(eset==set(names)) if eset is not None else None,
       zero_time=[n for n,v in st.items() if v[2]==0.0])
    # passed-lines in log
    passed=re.findall(r'Test\s+#\d+:\s+(\S+)\s+\.+\s+(\S+)',log)
    out[cfg]['log_status']=dict(collections.Counter(s for _,s in passed))
    out[cfg]['log_names_eq']=set(n for n,_ in passed)==set(names)
    out[cfg]['names']=sorted(names)
json.dump(out,open(sys.argv[2],'w'),indent=1)
for c,v in out.items():
    print(c,{k:v[k] for k in v if k!='names'})
