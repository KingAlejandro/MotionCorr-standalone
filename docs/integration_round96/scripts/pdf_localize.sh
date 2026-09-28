#!/usr/bin/env bash
# Localize WHERE the rendered PDF pages differ: confined to a text band, or in
# the plot area? Uses renders already produced by pdf_audit.sh. Nothing re-run.
set -uo pipefail
R=/home/ubuntu/mc-i96-pdfaudit
cd "$R"
exec > >(tee -a "$R/pdf_localize.log") 2>&1
echo "=== render-difference localization ==="; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
/home/ubuntu/.mc-venv/bin/python3 - <<'PY'
import glob, struct, zlib
import numpy as np

def load_png(p):
    d = open(p,'rb').read(); pos=8; idat=b''; w=h=ct=None
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]; typ = d[pos+4:pos+8]; body = d[pos+8:pos+8+ln]
        if typ==b'IHDR': w,h,_bd,ct = struct.unpack('>IIBB', body[:10])
        elif typ==b'IDAT': idat += body
        elif typ==b'IEND': break
        pos += 12+ln
    raw = zlib.decompress(idat); ch = {0:1,2:3,3:1,4:2,6:4}[ct]; stride = w*ch
    out = np.zeros((h,stride), np.uint8); prev = np.zeros(stride, np.uint8); i=0
    for y in range(h):
        ft = raw[i]; i+=1
        line = np.frombuffer(raw[i:i+stride], np.uint8).copy(); i+=stride
        if ft==1:
            for x in range(ch,stride): line[x]=(int(line[x])+int(line[x-ch]))&0xFF
        elif ft==2: line=(line.astype(int)+prev.astype(int)).astype(np.uint8)
        elif ft==3:
            for x in range(stride):
                a=int(line[x-ch]) if x>=ch else 0
                line[x]=(int(line[x])+((a+int(prev[x]))>>1))&0xFF
        elif ft==4:
            for x in range(stride):
                a=int(line[x-ch]) if x>=ch else 0; b=int(prev[x]); c=int(prev[x-ch]) if x>=ch else 0
                pp=a+b-c; pa,pb,pc=abs(pp-a),abs(pp-b),abs(pp-c)
                pr=a if (pa<=pb and pa<=pc) else (b if pb<=pc else c)
                line[x]=(int(line[x])+pr)&0xFF
        out[y]=line; prev=line
    return out.reshape(h,w,ch)

def save_png(arr, path):
    h,w,ch = arr.shape
    ct = {1:0,3:2,4:6}[ch]
    raw = b''.join(b'\x00'+arr[y].tobytes() for y in range(h))
    def chunk(t,d):
        c = struct.pack('>I',len(d))+t+d
        return c+struct.pack('>I', zlib.crc32(t+d)&0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,ct,0,0,0))
    png += chunk(b'IDAT', zlib.compress(raw,6))+chunk(b'IEND',b'')
    open(path,'wb').write(png)

print(f"{'artifact':14s} {'page':>5s}  {'rows with diff':>28s}  {'cols with diff':>28s}  {'diff px':>8s}  page size")
boxes = {}
for stem in ["all_batches","batch","logfile"]:
    A = sorted(glob.glob(f"png/{stem}.A.*.png")); B = sorted(glob.glob(f"png/{stem}.B.*.png"))
    for idx,(a,b) in enumerate(zip(A,B), 1):
        ia, ib = load_png(a), load_png(b)
        m = (np.abs(ia.astype(np.int16)-ib.astype(np.int16)) > 0).any(axis=2)
        if not m.any(): continue
        rows = np.where(m.any(axis=1))[0]; cols = np.where(m.any(axis=0))[0]
        h,w,_ = ia.shape
        boxes.setdefault(stem, []).append((idx, rows.min(), rows.max(), cols.min(), cols.max(), int(m.sum()), h, w))
        if idx <= 2:
            print(f"{stem:14s} {idx:5d}  rows {rows.min():5d}-{rows.max():5d} ({rows.max()-rows.min()+1:4d} of {h:4d})  "
                  f"cols {cols.min():5d}-{cols.max():5d} ({cols.max()-cols.min()+1:4d} of {w:4d})  {int(m.sum()):8d}  {w}x{h}")
print()
for stem, lst in boxes.items():
    spans = {(r0,r1) for _,r0,r1,_,_,_,_,_ in lst}
    h = lst[0][6]
    allrows = sorted({r for _,r0,r1,_,_,_,_,_ in lst for r in (r0,r1)})
    print(f"{stem}: {len(lst)} differing pages; row-extent across all pages {min(allrows)}-{max(allrows)} of {h} "
          f"({100*(max(allrows)-min(allrows)+1)/h:.1f}% of page height); distinct row spans: {len(spans)}")

# Crop the first differing page of all_batches to its diff bounding box, both arms,
# so the difference can be looked at rather than inferred.
a = sorted(glob.glob("png/all_batches.A.*.png"))[0]; b = sorted(glob.glob("png/all_batches.B.*.png"))[0]
ia, ib = load_png(a), load_png(b)
m = (np.abs(ia.astype(np.int16)-ib.astype(np.int16))>0).any(axis=2)
rows = np.where(m.any(axis=1))[0]; cols = np.where(m.any(axis=0))[0]
r0,r1 = max(0,rows.min()-6), min(ia.shape[0], rows.max()+7)
c0,c1 = max(0,cols.min()-6), min(ia.shape[1], cols.max()+7)
save_png(np.ascontiguousarray(ia[r0:r1, c0:c1]), "crop_main.png")
save_png(np.ascontiguousarray(ib[r0:r1, c0:c1]), "crop_cand.png")
print(f"\ncropped diff region rows {r0}-{r1} cols {c0}-{c1} -> crop_main.png / crop_cand.png")

# And the plot area: everything OUTSIDE the differing rows, compared exactly.
keep = np.ones(ia.shape[0], bool); keep[rows.min():rows.max()+1] = False
outside_equal = np.array_equal(ia[keep], ib[keep])
print(f"page-1 content OUTSIDE the differing row band is byte-identical: {outside_equal} "
      f"({int(keep.sum())} of {ia.shape[0]} rows)")
PY
echo "=== DONE localize ==="
