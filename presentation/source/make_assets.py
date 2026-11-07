from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, shift
root=Path(__file__).resolve().parents[1]; out=root/'assets'
rng=np.random.default_rng(20260924)
n=640; y,x=np.mgrid[:n,:n]; clean=np.zeros((n,n),np.float64)
# Synthetic detector field: repeated asymmetric macromolecule-like projections.
for k in range(70):
 cx,cy=rng.uniform(20,n-20,2); scale=rng.uniform(0.8,1.65); a=rng.uniform(0,2*np.pi)
 for dx,dy,sig,amp in [(-5,0,3.8,.7),(4,1,4.5,1.0),(0,7,3.3,.65),(0,-5,2.8,.5),(7,-5,2.5,.4)]:
  xx=cx+scale*(dx*np.cos(a)-dy*np.sin(a)); yy=cy+scale*(dx*np.sin(a)+dy*np.cos(a))
  clean+=amp*np.exp(-((x-xx)**2+(y-yy)**2)/(2*(sig*scale)**2))
clean=gaussian_filter(clean,.4)
shifts=[(-10,-7),(-7,-3),(-4,1),(-1,3),(2,5),(5,7),(8,8),(11,10)]
frames=[shift(clean,(sy,sx),order=3,mode='wrap')+rng.normal(0,.23,(n,n)) for sx,sy in shifts]
blur=np.mean(frames,axis=0)
align=np.mean([shift(f,(-sy,-sx),order=3,mode='wrap') for f,(sx,sy) in zip(frames,shifts)],axis=0)
def save(a,name):
 a=np.clip(190-105*a,12,238); rgb=np.stack([a*.93,a*.96,a],axis=-1).astype('uint8')
 Image.fromarray(rgb).save(out/name)
save(clean+rng.normal(0,.10,(n,n)),'micrograph-reference.png')
save(blur,'micrograph-unaligned.png');save(align,'micrograph-aligned.png')
for i,f in enumerate(frames):save(f,f'frame-{i}.png')
# Weighted correlation illustration, explicitly not experimental data.
y2,x2=np.mgrid[:340,:340]; corr=np.exp(-((x2-170)**2+(y2-172)**2)/(2*22**2))
corr+=.12*np.cos(x2/8)*np.cos(y2/9)*np.exp(-((x2-170)**2+(y2-172)**2)/(2*90**2))
v=np.clip(corr,0,1)[...,None]; col=np.array([66,133,244]);bg=np.array([21,30,44]);rgb=bg+(col-bg)*v
Image.fromarray(rgb.astype('uint8')).save(out/'correlation.png')
print('Synthetic microscopy assets written.')
