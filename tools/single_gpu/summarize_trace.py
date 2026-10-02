#!/usr/bin/env python3
"""Summarize overlapping NVTX/API intervals; never present them as additive wall."""
import json,sqlite3,sys
from collections import defaultdict
c=sqlite3.connect(sys.argv[1]);strings=dict(c.execute('select id,value from StringIds'))
ranges=[];groups=defaultdict(lambda:{'count':0,'inclusive_seconds':0.0})
for start,end,text,textid,tid in c.execute('select start,end,text,textId,globalTid from NVTX_EVENTS where end is not null'):
 name=text or strings.get(textid,str(textid));groups[name]['count']+=1;groups[name]['inclusive_seconds']+=(end-start)/1e9
 ranges.append((start,end,name,tid))
api=[]
for name,count,ns in c.execute('select nameId,count(*),sum(end-start) from CUPTI_ACTIVITY_KIND_RUNTIME group by nameId'):
 api.append({'name':strings[name],'count':count,'inclusive_seconds':ns/1e9})
kernels=[]
for name,count,ns in c.execute('select demangledName,count(*),sum(end-start) from CUPTI_ACTIVITY_KIND_KERNEL group by demangledName'):
 kernels.append({'name':strings[name],'count':count,'summed_gpu_seconds':ns/1e9})
intervals=list(c.execute('select start,end from CUPTI_ACTIVITY_KIND_KERNEL order by start'))
union=0;lo=hi=None
for a,b in intervals:
 if hi is None:lo,hi=a,b
 elif a<=hi:hi=max(hi,b)
 else:union+=hi-lo;lo,hi=a,b
if hi is not None:union+=hi-lo
ops=dict(c.execute('select id,label from ENUM_CUDA_DEV_MEM_EVENT_OPER'));kinds=dict(c.execute('select id,label from ENUM_CUDA_MEM_KIND'))
live={};tot=defaultdict(int);peaks=defaultdict(int);dups=0;unmatched=0
for pid,ctx,dev,addr,size,op,kind in c.execute('select globalPid,contextId,deviceId,address,bytes,memoryOperationType,memKind from CUDA_GPU_MEMORY_USAGE_EVENTS order by start'):
 key=(pid,ctx,dev,addr,kind);cat=kinds[kind]
 if ops[op]=='Allocation':
  if key in live:
   if cat=='Device Static' and live[key]==size:dups+=1;continue
   raise RuntimeError('duplicate live allocation '+str(key))
  live[key]=size;tot[cat]+=size;peaks[cat]=max(peaks[cat],tot[cat])
 elif ops[op]=='Deallocation':
  if key not in live:unmatched+=1;continue
  tot[cat]-=live.pop(key)
 else:raise RuntimeError('unknown event '+str(ops[op]))
result={'classification':'MEASURED trace intervals and traced allocations; not unprofiled application timing','range_scope':'overlapping inclusive CPU ranges; do not sum','ranges':dict(groups),'cuda_apis':sorted(api,key=lambda d:-d['inclusive_seconds']),'kernels':sorted(kernels,key=lambda d:-d['summed_gpu_seconds']),'kernel_busy_union_seconds':union/1e9,'traced_allocation_peak_bytes_by_kind':dict(peaks),'duplicate_static_events':dups,'unmatched_frees':unmatched,'memory_scope':'trace excludes untraced driver/context/device reservations; pinned trace is reservation, not host RSS'}
print(json.dumps(result,indent=2))
