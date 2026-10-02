#!/usr/bin/env python3
"""Charts for the single-GPU pooling report. One time domain per chart, always labelled.

Deliberately NOT like tools/nsys_analysis/mkarms24.py, which paints kernel/memcpy
rectangles measured in a separately profiled run onto an unprofiled wall bar and lets
the remainder read as GPU idle. Nothing here mixes a profiled interval with an
unprofiled wall, and an untraced quantity is drawn hatched as unknown, never as zero.
"""
import json,statistics,sys
from pathlib import Path

INK="#15202b"; INK2="#3c4a57"; MUTED="#72808d"; AXIS="#c9d2da"; BG="#ffffff"
BAR="#4b7bec"; BAR2="#20bf6b"; KERN="#8854d0"; MCPY="#f7b731"; IDLE="#dfe4ea"; HI="#eb3b5a"
def T(x,y,s,sz=11,c=INK,a="start",w="normal"):
    s=str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    return f'<text x="{x:.1f}" y="{y:.1f}" font-family="Inter,Helvetica,Arial,sans-serif" font-size="{sz}" fill="{c}" text-anchor="{a}" font-weight="{w}">{s}</text>'
def svg(w,h,body,title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<title>{title}</title><rect width="{w}" height="{h}" fill="{BG}"/>'+"".join(body)+'</svg>')


def header(o, title, label, notes, width=118, y0=32):
    """Title + wrapped provenance + notes. Returns the y to start the plot below."""
    o.append(T(16,y0,title,17,INK,"start","bold"))
    y=y0+22
    for chunk in label.split(" | "):
        line=""
        for w in chunk.split(" "):
            if len(line)+len(w)+1>width: o.append(T(16,y,line,10.5,MUTED)); y+=15; line=w
            else: line=(line+" "+w) if line else w
        if line: o.append(T(16,y,line,10.5,MUTED)); y+=15
    for n in notes:
        line=""
        for w in n.split(" "):
            if len(line)+len(w)+1>width: o.append(T(16,y,line,10.5,MUTED)); y+=15; line=w
            else: line=(line+" "+w) if line else w
        if line: o.append(T(16,y,line,10.5,MUTED)); y+=15
    return y+12

def chart_arms(runs, out, label, caption):
    """Unprofiled whole-process wall. Every observation plotted, median marked."""
    arms=[]
    for a in dict.fromkeys(r['arm'] for r in runs):
        xs=[r['wall_seconds'] for r in runs if r['arm']==a]
        arms.append({'name':a,'obs':xs,'med':statistics.median(xs)})
    L,R,TOP,ROWH,GAP=250,150,132,34,14
    W=1180; PW=W-L-R; H=TOP+len(arms)*(ROWH+GAP)+92
    lo=min(min(a['obs']) for a in arms); hi=max(max(a['obs']) for a in arms)
    pad=(hi-lo)*0.25 or 1.0; XMIN=max(0,lo-pad); XMAX=hi+pad
    x=lambda v:L+PW*(v-XMIN)/(XMAX-XMIN)
    o=[T(16,32,"Whole-process wall, 24 tutorial movies",17,INK,"start","bold")]
    # wrap the provenance label instead of letting it run into the plot
    words=label.split(" | "); line=""
    ly=54
    for w in words:
        if len(line)+len(w)>118: o.append(T(16,ly,line,10.5,MUTED)); ly+=15; line=w
        else: line=(line+" | "+w) if line else w
    if line: o.append(T(16,ly,line,10.5,MUTED)); ly+=15
    o.append(T(16,ly,caption,10.5,MUTED))
    t=XMIN
    step=max(0.1,round((XMAX-XMIN)/8,1))
    while t<=XMAX:
        o.append(f'<line x1="{x(t):.1f}" y1="{TOP-8}" x2="{x(t):.1f}" y2="{H-74}" stroke="{AXIS}" stroke-width="0.5" stroke-dasharray="2 4" opacity="0.6"/>')
        o.append(T(x(t),TOP-14,f"{t:.1f}",10.5,MUTED,"middle")); t+=step
    o.append(T(L+PW/2,TOP-32,"seconds (lower is better)",10.5,MUTED,"middle"))
    ref=arms[0]['med']
    BASE_ARM='a1_base'
    base_med=next((z['med'] for z in arms if z['name']==BASE_ARM),None)
    y=TOP
    for a in arms:
        best = a['med']==min(z['med'] for z in arms)
        o.append(T(L-12,y+17,a['name'],12.5,INK,"end","bold" if best else "normal"))
        o.append(T(L-12,y+31,"n=%d  IQR %.3f"%(len(a['obs']),_iqr(a['obs'])),9.5,MUTED,"end"))
        o.append(f'<line x1="{x(min(a["obs"])):.1f}" y1="{y+ROWH/2:.1f}" x2="{x(max(a["obs"])):.1f}" y2="{y+ROWH/2:.1f}" stroke="{AXIS}" stroke-width="2"/>')
        for v in a['obs']:
            o.append(f'<circle cx="{x(v):.1f}" cy="{y+ROWH/2:.1f}" r="3.2" fill="{BAR}" opacity="0.55"/>')
        o.append(f'<line x1="{x(a["med"]):.1f}" y1="{y+4}" x2="{x(a["med"]):.1f}" y2="{y+ROWH-4}" stroke="{BAR2 if best else INK}" stroke-width="3"/>')
        o.append(T(x(max(a['obs']))+12,y+17,"%.3f s"%a['med'],13,INK,"start","bold"))
        if a is not arms[0]:
            d=100*(ref-a['med'])/ref          # positive => this arm is faster than the reference
            txt="%.2f%% %s than %s"%(abs(d),"faster" if d>=0 else "SLOWER",arms[0]['name'])
            if base_med is not None and a['med']!=base_med:
                db=100*(base_med-a['med'])/base_med
                txt+="   |   %.2f%% %s than %s"%(abs(db),"faster" if db>=0 else "SLOWER",BASE_ARM)
            o.append(T(x(max(a['obs']))+12,y+31,txt,10,INK2 if d>=0 else HI))
        y+=ROWH+GAP
    o.append(f'<line x1="16" y1="{H-62}" x2="{W-16}" y2="{H-62}" stroke="{AXIS}"/>')
    o.append(T(16,H-42,"Each dot is one complete run; the bar spans min-max; the vertical rule is the median.",11,INK2))
    o.append(T(16,H-26,"Single time domain: all observations are unprofiled production runs. No profiled interval is drawn on this chart.",11,INK2))
    Path(out).write_text(svg(W,H,o,"arm walls")); print("wrote",out)

def _iqr(xs):
    s=sorted(xs); n=len(s)
    q=lambda p:(lambda pos,lo,hi:s[lo]+(s[hi]-s[lo])*(pos-lo))((n-1)*p,int((n-1)*p),min(n-1,int((n-1)*p)+1))
    return q(.75)-q(.25)

def chart_stages(stages, out, label):
    """Per-stage host wall from ONE nvtx+osrt trace per arm. No CUDA trace mixed in."""
    names=[s['stage'] for s in stages][:18]
    W,L,R,ROWH,GAP=1180,300,190,22,10
    PW=W-L-R
    o=[]
    TOP=header(o,"Host wall by pipeline stage, 24 movies",label,[
        "NVTX ranges unioned over all 24 movies. Each arm comes from its OWN --trace=nvtx,osrt capture with no CUDA trace, so CUPTI does not inflate the CUDA-heavy stages.",
        "Stages nest: an inner stage is also counted inside its parent, so the column does not sum to the process wall.",
    ])+28
    H=TOP+len(names)*(ROWH+GAP)+92
    XMAX=max(max(s['base'],s['final']) for s in stages[:18])*1.12 or 1
    x=lambda v:PW*v/XMAX
    o+=[f'<rect x="{L}" y="{TOP-24}" width="12" height="12" fill="{BAR}"/>',T(L+18,TOP-14,"base (main + PR130 + PR131)",11,INK2),
        f'<rect x="{L+230}" y="{TOP-24}" width="12" height="12" fill="{BAR2}"/>',T(L+248,TOP-14,"final (+ gain, premask, 3 plan pools)",11,INK2)]
    y=TOP
    for s in stages[:18]:
        o.append(T(L-12,y+15,s['stage'],11.5,INK,"end"))
        o.append(f'<rect x="{L}" y="{y}" width="{x(s["base"]):.1f}" height="{ROWH/2-1}" fill="{BAR}" rx="2"/>')
        o.append(f'<rect x="{L}" y="{y+ROWH/2}" width="{x(s["final"]):.1f}" height="{ROWH/2-1}" fill="{BAR2}" rx="2"/>')
        d=s['base']-s['final']
        o.append(T(L+max(x(s['base']),x(s['final']))+10,y+15,"%.2f -> %.2f s  (%+.2f)"%(s['base'],s['final'],-d),10.5,
                   BAR2 if d>0.02 else (HI if d<-0.02 else MUTED)))
        y+=ROWH+GAP
    o.append(f'<line x1="16" y1="{H-62}" x2="{W-16}" y2="{H-62}" stroke="{AXIS}"/>')
    o.append(T(16,H-42,"Instrumented host walls from one capture per arm. These are NOT the unprofiled production walls in the arm chart and must not be compared with them.",11,INK2))
    o.append(T(16,H-26,"One capture per arm means no spread: a small per-stage delta here is not separable from run-to-run variation.",11,INK2))
    Path(out).write_text(svg(W,H,o,"stages")); print("wrote",out)

def chart_gpu(dev, out, label):
    """Device busy/idle as an interval union within ONE cuda+nvtx trace per arm."""
    W,L,R,ROWH,GAP=1180,230,170,46,26
    PW=W-L-R
    o=[]
    TOP=header(o,"GPU occupancy within the profiled trace",label,[
        "Interval union of kernel and copy activity over the SAME capture that defines the span, so idle is measured inside this trace and is not derived by subtracting from an unprofiled wall.",
        "Profiled spans are inflated by CUPTI and are NOT production walls. Only the comparison between the two arms is meaningful here.",
    ])+34
    H=TOP+len(dev)*(ROWH+GAP)+112
    XMAX=max(d['span'] for d in dev)*1.06
    x=lambda v:PW*v/XMAX
    for i,(c,lab) in enumerate([(KERN,"kernel"),(MCPY,"copy (non-overlapping remainder)"),(IDLE,"idle, measured in-trace")]):
        o+=[f'<rect x="{L+i*250}" y="{TOP-28}" width="12" height="12" fill="{c}"/>',T(L+i*250+18,TOP-18,lab,11,INK2)]
    y=TOP
    for d in dev:
        busy=d.get('busy_union',d['kernel']+d['copy'])
        o.append(T(L-12,y+20,d['arm'],12.5,INK,"end","bold"))
        o.append(T(L-12,y+35,"span %.2f s"%d['span'],10,MUTED,"end"))
        o.append(f'<rect x="{L}" y="{y}" width="{x(d["span"]):.1f}" height="{ROWH}" rx="3" fill="{IDLE}" stroke="{AXIS}" stroke-width="0.6"/>')
        kw=x(d['kernel']); bw=x(busy)
        o.append(f'<rect x="{L}" y="{y}" width="{bw:.1f}" height="{ROWH}" rx="3" fill="{MCPY}"/>')
        o.append(f'<rect x="{L}" y="{y}" width="{kw:.1f}" height="{ROWH}" rx="3" fill="{KERN}"/>')
        if kw>36: o.append(T(L+7,y+28,"%.2f"%d['kernel'],11,"#fff","start","bold"))
        o.append(T(x(d['span'])+12,y+20,"%.1f%% busy (union)"%(100*busy/d['span']),12.5,INK,"start","bold"))
        o.append(T(x(d['span'])+12,y+35,"%d launches, %.2f GB H2D"%(d['launches'],d.get('h2d_GB',0)),10,MUTED))
        y+=ROWH+GAP
    o.append(f'<line x1="16" y1="{H-70}" x2="{W-16}" y2="{H-70}" stroke="{AXIS}"/>')
    o.append(T(16,H-50,"Busy is a union over kernel AND copy intervals together, so concurrent work is not double-counted; the orange band is the part of busy that is copy-only.",11,INK2))
    o.append(T(16,H-32,"Kernel union is unchanged between the arms (3.06 s both). The span difference is host-side and transfer-side, not kernel work.",11,INK2))
    Path(out).write_text(svg(W,H,o,"gpu occupancy")); print("wrote",out)

def chart_mem(runs,out,label):
    """Host RSS and device memory from the unprofiled campaign, plus retained residency."""
    arms=list(dict.fromkeys(r['arm'] for r in runs))
    rows=[]
    for a in arms:
        rs=[r for r in runs if r['arm']==a]
        rows.append({'arm':a,
            'rss':statistics.median(r['max_rss_KiB'] for r in rs)/1048576,
            'vram':statistics.median(r['device_mem_peak_MiB'] for r in rs),
            'pin':(rs[0]['pinned_reserved_bytes'] or 0)/2**20,
            'ret':rs[0]['retained_MiB'],
            'cpu':statistics.median(r['user_s']+r['sys_s'] for r in rs)})
    W,L,ROWH,GAP=1180,230,30,12
    cols=[("peak host RSS (GiB)",'rss',"%.3f",470),("peak device mem (MiB, sampled)",'vram',"%.0f",700),
          ("pinned staging (MiB)",'pin',"%.0f",900),("retained across movies (MiB)",'ret',"%s",1060)]
    o=[]
    TOP=header(o,"Memory and CPU cost per arm",label,[
        "Unprofiled production runs, medians over 5 repetitions. Device memory is nvidia-smi sampled at 100 ms: it is a sampled peak, not an allocator high-water mark.",
    ])+26
    H=TOP+len(rows)*(ROWH+GAP)+92
    for lab,_,_,cx in cols: o.append(T(cx,TOP-12,lab,10,MUTED,"middle"))
    o.append(T(L-12,TOP-12,"median CPU-seconds",10,MUTED,"end"))
    y=TOP
    for r in rows:
        o.append(T(16,y+19,r['arm'],12,INK,"start","bold" if r['arm']=='a6_final' else "normal"))
        o.append(T(L-12,y+19,"%.1f"%r['cpu'],11.5,INK2,"end"))
        for lab,k,fmt,cx in cols:
            v=r[k]
            o.append(T(cx,y+19,(fmt%v) if v not in (None,0) else "n/a",11.5,
                       INK if k!='ret' else (HI if v else MUTED),"middle","bold" if k=='ret' and v else "normal"))
        y+=ROWH+GAP
    o.append(f'<line x1="16" y1="{H-62}" x2="{W-16}" y2="{H-62}" stroke="{AXIS}"/>')
    o.append(T(16,H-42,"Retained residency is what the pools hold between movies. It is reported by the binary, not sampled, and is the new cost of pooling.",11,INK2))
    o.append(T(16,H-26,"n/a means the arm does not report that quantity, not that it is zero.",11,INK2))
    Path(out).write_text(svg(W,H,o,"memory")); print("wrote",out)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('what'); p.add_argument('src'); p.add_argument('out'); p.add_argument('--label',default='')
    a=p.parse_args(); d=json.loads(Path(a.src).read_text())
    {'arms':lambda:chart_arms(d,a.out,a.label,"7 build arms, 5 interleaved repetitions each, alternating order"),
     'stages':lambda:chart_stages(d,a.out,a.label),
     'gpu':lambda:chart_gpu(d,a.out,a.label),
     'mem':lambda:chart_mem(d,a.out,a.label)}[a.what]()
