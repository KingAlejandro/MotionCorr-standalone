#!/usr/bin/env python3
"""Readable CSVs and a standalone scientific figure from the frozen census."""
import csv,gzip,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
s=json.loads(gzip.decompress((ROOT/'SUMMARY.json.gz').read_bytes()))

def write(name,rows):
 with (ROOT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
 rows=[]
 for r in s['rows']:
  row={k:r[k] for k in ['condition','seed','arm','global_converged','local_enabled','patches_converged','patches_total','field_distance_status','sampling_status']}
  for family in ['field','global','local']:
   for unit,scale in [('px',1.),('angstrom',.885)]:
    for stat,v in r[family+'_px'].items():row[f'{family}_{stat}_{unit}']=v*scale
  row['star_roundtrip_max_px']=r['star_roundtrip_loss_px']['max'];rows.append(row)
 write('accuracy_per_seed.csv',rows)
 rows=[]
 for r in s['table']:
  row={k:v for k,v in r.items() if not isinstance(v,dict)}
  for key in ['median_field_px','median_field_angstrom']:
   for stat,v in r[key].items():row[key+'_'+stat]=v
  rows.append(row)
 write('accuracy_per_arm.csv',rows)
 rows=[]
 for r in s['paired']:
  for metric,m in r['metrics'].items():rows.append(dict(condition=r['condition'],baseline=r['baseline'],candidate=r['candidate'],metric=metric,**m))
 write('paired_seed_statistics.csv',rows)
 rows=[]
 for r in s['temporal']:
  row={k:r[k] for k in ['condition','arm','frame']}
  for family in ['field','global_trajectory','local_component']:
   for stat,v in r[family+'_median_px'].items():
    row[family+'_median_'+stat+'_px']=v;row[family+'_median_'+stat+'_angstrom']=v*.885
  rows.append(row)
 write('time_errors.csv',rows)
 for key,name,columns in [('backend_agreement','backend_agreement.csv',['condition','seed','dc']),('double_reference_distance','double_reference_distance.csv',['condition','seed','arm','within_descriptive_001px'])]:
  rows=[]
  for r in s[key]:
   row={k:r[k] for k in columns}
   for unit in ['px','angstrom']:
    for stat,v in r['field_distance'][unit].items():row[unit+'_'+stat]=v
   rows.append(row)
  write(name,rows)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,2,figsize=(10,3.5),constrained_layout=True)
 colors={'cpu-none':'#b4532c','cpu-both':'#2669a5','cpu-double':'#202020'}
 for ax,condition,title in zip(axes,['dose1','pedestal32'],['Baseline pedestal 1','High pedestal 32']):
  for arm,label in [('cpu-none','No conditioning'),('cpu-both','Global + local DC conditioning'),('cpu-double','Double CCF reference')]:
   rr=sorted([r for r in s['temporal'] if r['condition']==condition and r['arm']==arm],key=lambda r:r['frame'])
   ax.plot([r['frame'] for r in rr],[r['field_median_px']['rms'] for r in rr],label=label,color=colors[arm],linestyle='--' if arm=='cpu-double' else '-',linewidth=1.6)
  ax.set(title=title,xlabel='Frame (1-based)',ylabel='Median per-seed field RMS (px)',xlim=(1,40),ylim=(0,None))
  ax.grid(alpha=.2)
 axes[0].legend(fontsize=8,loc='lower right')
 fig.suptitle('Truth error versus time · 10 matched Poisson seeds · 0.885 Å/px',fontsize=11)
 fig.savefig(ROOT/'field_error_time.svg');fig.savefig(ROOT/'field_error_time.png',dpi=170);plt.close(fig)

if __name__=='__main__':main()
