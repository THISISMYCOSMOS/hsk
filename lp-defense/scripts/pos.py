from rpc import *
import json, math
mb=json.load(open('mintburn.json'))
INC='0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f'
def s(x): 
    v=int(x,16); return v-2**256 if v>2**255 else v
npm=set(); tokens={}
for pool in mb:
    for lg in mb[pool]['mint']:
        owner=addr(lg['topics'][1]); npm.add(owner)
        rc=call('eth_getTransactionReceipt',[lg['transactionHash']])
        for l in rc['logs']:
            if l['topics'][0]==INC:
                tokens.setdefault(pool,set()).add((l['address'],int(l['topics'][1],16)))
print('mint owners',npm)
out={}
for pool,ts in tokens.items():
    out[pool]=[]
    for (nm,tid) in sorted(ts,key=lambda x:x[1]):
        try: own=addr(ecall(nm,'0x6352211e'+hex(tid)[2:].rjust(64,'0')))
        except Exception as e: own='burned'
        try:
            p=ecall(nm,'0x99fbab88'+hex(tid)[2:].rjust(64,'0'))
            w=[p[2+64*i:2+64*(i+1)] for i in range(12)]
            tl=s(w[5]); tu=s(w[6]); L=int(w[7],16); o0=int(w[10],16); o1=int(w[11],16)
        except Exception: tl=tu=None; L=0; o0=o1=0
        out[pool].append(dict(npm=nm,id=tid,owner=own,tl=tl,tu=tu,L=L,owed0=o0,owed1=o1))
        print(pool,tid,own,tl,tu,L)
json.dump(out,open('positions.json','w'),indent=1)
