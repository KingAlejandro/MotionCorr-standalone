import concurrent.futures
from generate_campaign_parallel import one,ROOT
if __name__=='__main__':
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
  for row in pool.map(one,[('pedestal32',s,str(ROOT/'expectations/inmodel.npy')) for s in range(10)]):print(row,flush=True)
