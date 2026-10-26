"""Standalone scientific figure from sealed diagnostic scores; no new estimates."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

P=Path(__file__).parent
a=json.loads((P/'SCORE.json').read_text())
b=json.loads(Path('/tmp/mc-local-physical-frequency-parent-20261026/SCORE.json').read_text())
plt.rcParams.update({'font.size':10,'font.family':'DejaVu Sans','svg.fonttype':'none','svg.hashsalt':'mc-local-objective-20261026'})
fig,axes=plt.subplots(1,2,figsize=(9,4.7),layout='constrained')
labels=['Native trajectory','Joint optimization\ninherited weights','Joint optimization\nfull-width local weights']
for ax,metric,title in zip(axes,['rms','max'],['Five-frame center RMS error','Five-frame center maximum error']):
    for cy,color,label in [(79,'#27618c','Bad patch (62,79)'),(47,'#bd6526','Central patch (62,47)')]:
        native=next(r for r in a['rows'] if r['patch_y']==cy and r['label']=='baseline:native_final')
        old=next(r for r in a['rows'] if r['patch_y']==cy and r['selected'])
        new=next(r for r in b['rows'] if r['patch_y']==cy and r['selected'])
        ys=[r['physical_error_px'][metric] for r in [native,old,new]]
        ax.plot(range(3),ys,marker='o',lw=2,color=color,label=label)
        for i,y in enumerate(ys):
            # Display only the two diagnostic endpoints to reduce overlap.
            if i in [1,2]:ax.annotate(f'{y:.3f}',(i,y),xytext=(0,8 if cy==79 else -16),textcoords='offset points',ha='center',color=color,fontsize=9)
    ax.set_xticks(range(3),labels,fontsize=8.5)
    ax.set_xlim(-.15,2.15);ax.set_ylim(bottom=0)
    ax.set_ylabel('Physical unwrapped error (px)');ax.set_title(title,loc='left',fontsize=12,pad=12)
    ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
axes[0].annotate('Bad patch (62,79)', (0,6.703455452385791), xytext=(10,-18), textcoords='offset points', color='#27618c', fontsize=9)
axes[0].annotate('Central patch (62,47)', (0,1.1899721874942137), xytext=(10,12), textcoords='offset points', color='#bd6526', fontsize=9)
fig.suptitle('Local frequency weighting changes trajectory recovery',fontsize=16,fontweight='bold',ha='left',x=.03)
fig.supxlabel('Two exposed noisy patches · fixed captured spectra/global trajectory · 11 truth-free starts per patch\nPoint-center diagnostics only; full-ROI scientific gates and native changed-weight tests are unrun.',fontsize=8.5)
fig.savefig(P/'trajectory-diagnostic.png',dpi=180)
fig.savefig(P/'trajectory-diagnostic.svg')
print('wrote standalone PNG/SVG')
