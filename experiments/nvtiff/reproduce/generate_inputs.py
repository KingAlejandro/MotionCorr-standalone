#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Known controlled pixels only; no tutorial/untrusted compressed bytes."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import tifffile,imagecodecs

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pixels(frames,bits):
    f,y,x=np.indices((frames,512,1024),dtype=np.uint32)
    return ((f*1031+y*79+x*31+(x*y)%997)%(1<<bits)).astype('uint%d'%bits)
def main():
    root=Path(sys.argv[1]);root.mkdir(exist_ok=False)
    rows=[]
    specs=[('u8-strip-p1',8,24,1,False,'<'),('u8-strip-p2',8,48,2,False,'<'),
      ('u16-strip-p1',16,24,1,False,'<'),('u16-strip-p2',16,48,2,False,'<'),
      ('u16-big-endian',16,24,2,False,'>'),('u8-tile',8,24,1,True,'<'),
      ('u16-tile-p2',16,24,2,True,'<'),('u8-explicit-depth1',8,24,1,False,'<')]
    for name,bits,frames,pred,tile,endian in specs:
        arr=pixels(frames,bits);p=root/(name+'.tiff')
        kwargs={'tile':(128,128)} if tile else {'rowsperstrip':16}
        if name=='u8-explicit-depth1':kwargs['extratags']=[(32997,'I',1,1,False)]
        with tifffile.TiffWriter(p,byteorder=endian) as w:
            for plane in arr:w.write(plane,compression='lzw',predictor=pred,photometric='minisblack',metadata=None,**kwargs)
        with tifffile.TiffFile(p) as tf:decoded=np.stack([page.asarray() for page in tf.pages])
        if decoded.dtype.kind!='u' or not np.array_equal(arr,decoded):raise RuntimeError('independent generated-source readback')
        rows.append(dict(name=name,path=p.name,sha256=sha(p),bits=bits,frames=frames,shape=list(arr.shape),predictor=pred,tile=tile,byteorder=endian,expected='eligible'))
    for name,arr,tags,photo in [('orientation-2',pixels(3,8),[(274,'H',1,2,False)],'minisblack'),
       ('miniswhite',pixels(3,8),[],'miniswhite'),('signed',pixels(3,16).astype(np.int16),[],'minisblack')]:
        p=root/(name+'.tiff')
        with tifffile.TiffWriter(p) as w:
            for plane in arr:w.write(plane,compression='lzw',rowsperstrip=16,photometric=photo,extratags=tags,metadata=None)
        rows.append(dict(name=name,path=p.name,sha256=sha(p),expected='refused'))
    p=root/'mixed-width.tiff'
    with tifffile.TiffWriter(p) as w:
        w.write(pixels(1,8)[0],compression='lzw',metadata=None)
        w.write(pixels(1,8)[0,:,:-1],compression='lzw',metadata=None)
    rows.append(dict(name='mixed-width',path=p.name,sha256=sha(p),expected='refused'))
    p=root/'volume-depth2.tiff'
    tifffile.imwrite(p,pixels(2,8),volumetric=True,photometric='minisblack',compression='lzw',rowsperstrip=16,metadata=None)
    with tifffile.TiffFile(p) as tf:
        if len(tf.pages)!=1 or tf.pages[0].tags[32997].value!=2:raise RuntimeError('actual volume tag fixture')
        if not np.array_equal(tf.pages[0].asarray(),pixels(2,8)):raise RuntimeError('volume independent readback')
    rows.append(dict(name='volume-depth2',path=p.name,sha256=sha(p),expected='refused'))
    (root/'manifest.json').write_text(json.dumps(dict(inputs=rows,versions={m.__name__:m.__version__ for m in [np,tifffile,imagecodecs]},trusted='generated pixels, all source readbacks exact'),indent=2)+'\n')
if __name__=='__main__':main()
