from rpc import *
import json, sys
from concurrent.futures import ThreadPoolExecutor
addr_=sys.argv[1]; start=int(sys.argv[2]); end=int(sys.argv[3]); out=sys.argv[4]
topics=json.loads(sys.argv[5]) if len(sys.argv)>5 else None
STEP=5000
def job(a):
    f={"address":addr_,"fromBlock":hex(a),"toBlock":hex(min(a+STEP-1,end))}
    if topics: f["topics"]=topics
    return rpc("eth_getLogs",[f])
res=[]
with ThreadPoolExecutor(12) as ex:
    for r in ex.map(job, range(start,end+1,STEP)): res.extend(r)
json.dump(res,open(out,'w')); print(len(res))
