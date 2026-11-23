from rpc import *
import json, sys
from concurrent.futures import ThreadPoolExecutor
start=int(sys.argv[1]); end=int(sys.argv[2]); out=sys.argv[3]; topics=json.loads(sys.argv[4])
addr_=sys.argv[5] if len(sys.argv)>5 else None
STEP=5000
def job(a):
    f={"fromBlock":hex(a),"toBlock":hex(min(a+STEP-1,end)),"topics":topics}
    if addr_: f["address"]=addr_
    return rpc("eth_getLogs",[f])
res=[]
with ThreadPoolExecutor(12) as ex:
    for r in ex.map(job, range(start,end+1,STEP)): res.extend(r)
json.dump(res,open(out,'w')); print(len(res))
