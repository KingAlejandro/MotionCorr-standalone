#!/usr/bin/env python3
"""Per-arm device-memory timelines and GPU execution profiles.

One capture per arm, nsys --trace=cuda --cuda-memory-usage=true. Every series on a
chart comes from that arm's own capture; nothing is combined across runs. Profiled
spans are inflated by CUPTI and by the memory-usage instrumentation itself, so the
time axis is NOT a production wall -- it is there to show structure, not duration.
"""
import json,sys
from pathlib import Path
INK="#15202b"; INK2="#3c4a57"; MUTED="#72808d"; AXIS="#c9d2da"; BG="#fff"
LINE="#4b7bec"; FLOOR="#eb3b5a"; PEAK="#8854d0"; BUSY="#20bf6b"; IDLE="#eef1f4"
def T(x,y,s,sz=11,c=INK,a="start",w="normal"):
    s=str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    return f'<text x="{x:.1f}" y="{y:.1f}" font-family="Inter,Helvetica,Arial,sans-serif" font-size="{sz}" fill="{c}" text-anchor="{a}" font-weight="{w}">{s}</text>'
def svg(w,h,b,t): return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><title>{t}</title><rect width="{w}" height="{h}" fill="{BG}"/>'+"".join(b)+'</svg>'
def hdr(o,title,label,notes,y0=32,width=120):
    o.append(T(16,y0,title,17,INK,"start","bold")); y=y0+22
    for chunk in list(label.split(" | "))+notes:
        line=""
        for wd in chunk.split(" "):
            if len(line)+len(wd)+1>width: o.append(T(16,y,line,10.5,MUTED)); y+=15; line=wd
            else: line=(line+" "+wd) if line else wd
        if line: o.append(T(16,y,line,10.5,MUTED)); y+=15
    return y+10

MIB=2**20
def vram(arms,out,label):
    W,L,R,RH,GAP=1180,210,260,70,20
    PW=W-L-R
    o=[]; TOP=hdr(o,"Device memory over time, per arm",label,[
        "Running total of CUDA allocations minus deallocations inside each arm's own capture.",
        "The red rule is the steady-state FLOOR: what the process still holds between movies. The purple tick is the peak.",
        "Each arm has its own time axis normalised to its own span, so the shapes are comparable but the widths are not durations."])+16
    H=TOP+len(arms)*(RH+GAP)+92
    ymax=max(a['vram']['peak_bytes'] for a in arms)*1.08
    y=TOP
    for a in arms:
        v=a['vram']; pts=v['points']; span=a['span_s'] or 1
        o.append(T(L-12,y+20,a['arm'],12.5,INK,"end","bold" if a['arm']=='a6_final' else "normal"))
        o.append(T(L-12,y+35,"%d allocs / %d frees"%(v['alloc_events'],v['free_events']),9.5,MUTED,"end"))
        o.append(f'<rect x="{L}" y="{y}" width="{PW}" height="{RH}" fill="{IDLE}"/>')
        step=max(1,len(pts)//1400)
        d=[]
        for i in range(0,len(pts),step):
            t,b=pts[i]
            d.append(f'{L+PW*min(1.0,t/span):.1f},{y+RH-RH*min(1.0,b/ymax):.1f}')
        if d: o.append(f'<polyline points="{" ".join(d)}" fill="none" stroke="{LINE}" stroke-width="1.1" opacity="0.95"/>')
        fl=v['retained_floor_bytes'] or 0
        fy=y+RH-RH*min(1.0,fl/ymax)
        o.append(f'<line x1="{L}" y1="{fy:.1f}" x2="{L+PW}" y2="{fy:.1f}" stroke="{FLOOR}" stroke-width="1.6" stroke-dasharray="5 3"/>')
        py=y+RH-RH*min(1.0,v['peak_bytes']/ymax)
        o.append(f'<line x1="{L+PW*min(1.0,v["peak_t_s"]/span):.1f}" y1="{py:.1f}" x2="{L+PW*min(1.0,v["peak_t_s"]/span):.1f}" y2="{y+RH}" stroke="{PEAK}" stroke-width="1.4" opacity="0.8"/>')
        o.append(T(L+PW+12,y+20,"peak %.0f MiB"%(v['peak_bytes']/MIB),11.5,PEAK,"start","bold"))
        o.append(T(L+PW+12,y+36,"floor %.1f MiB"%(fl/MIB),11.5,FLOOR,"start","bold"))
        o.append(T(L+PW+12,y+52,"span %.2f s (profiled)"%span,9.5,MUTED))
        y+=RH+GAP
    o.append(f'<line x1="16" y1="{H-70}" x2="{W-16}" y2="{H-70}" stroke="{AXIS}"/>')
    o.append(T(16,H-50,"Pooling barely moves the PEAK -- those buffers were already live during a movie. It raises the FLOOR, because they are no longer released between movies.",11,INK2))
    o.append(T(16,H-32,"Floor is the minimum of the running total over the middle 25-85% of the span, so warm-up and teardown cannot flatter it.",11,INK2))
    Path(out).write_text(svg(W,H,o,"vram per arm")); print("wrote",out)

def gpuprof(arms,out,label,big=False):
    nb=len(arms[0]['gpu']['occupancy_bins'])
    W,L,R,RH,GAP=(1180,210,150,(96 if big else 44),(26 if big else 14))
    PW=W-L-R
    o=[]; TOP=hdr(o,"GPU execution profile" + (" - final arm" if big else ", per arm"),label,[
        f"Fraction of each time bin in which the device was executing a kernel or a copy, from that arm's own capture. {nb} bins across the span.",
        "Tall bars are device work; the gaps are the device waiting on the host. This is structure, not duration: the span is CUPTI-inflated."])+14
    H=TOP+len(arms)*(RH+GAP)+92
    y=TOP
    for a in arms:
        occ=a['gpu']['occupancy_bins']; n=len(occ); bw=PW/n
        nm=a['arm'].replace('_hires','')
        o.append(T(L-12,y+(RH/2+4),nm,12.5,INK,"end","bold" if nm=='a6_final' else "normal"))
        o.append(f'<rect x="{L}" y="{y}" width="{PW}" height="{RH}" fill="{IDLE}"/>')
        for i,v in enumerate(occ):
            if v<=0: continue
            o.append(f'<rect x="{L+i*bw:.2f}" y="{y+RH-RH*v:.2f}" width="{bw+0.35:.2f}" height="{RH*v:.2f}" fill="{BUSY}"/>')
        mean=sum(occ)/len(occ)
        o.append(T(L+PW+12,y+(RH/2),"%.1f%% busy"%(100*mean),11.5,INK,"start","bold"))
        o.append(T(L+PW+12,y+(RH/2)+15,"%d kernels"%a['gpu']['kernels'],9.5,MUTED))
        y+=RH+GAP
    o.append(f'<line x1="16" y1="{H-70}" x2="{W-16}" y2="{H-70}" stroke="{AXIS}"/>')
    o.append(T(16,H-50,("The 24 per-movie groups are visible as repeating dense clusters; the device is idle between and within them." if big
                        else "The device is idle in most of every bin: the host, not the GPU, sets the pace. This bin width is too coarse to resolve the 24 per-movie groups - see the single-arm chart for those."),11,INK2))
    o.append(T(16,H-32,"None of these changes alters kernel work (kernel union is 3.058 s base vs 3.061 s final). They remove host time and PCIe traffic, which is why the pattern compresses horizontally without getting denser.",11,INK2))
    Path(out).write_text(svg(W,H,o,"gpu profile")); print("wrote",out)

if __name__=="__main__":
    what,outp,label=sys.argv[1],sys.argv[2],sys.argv[3]
    names=sys.argv[4:]
    arms=[json.loads(Path(f"/home/alex/mc-release-20261002/report/data/vram-{n}.json").read_text()) for n in names]
    (vram if what=="vram" else (lambda a,o,l: gpuprof(a,o,l,big=(len(a)==1))))(arms,outp,label)
