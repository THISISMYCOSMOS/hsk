# Build 6-hourly (price, full-range liquidity) from pool Mint/Burn logs + swap prices (no extra RPC)
import json, bisect, datetime as dt
MB=json.load(open('mintburn.json')); S=json.load(open('swaps_all.json'))
def s(x):
    v=int(x,16); return v-2**256 if v>2**255 else v
out=[]
for n in ['WETH','WHSK']:
    ev=[]
    for l in MB[n]['mint']:
        if s(l['topics'][2])<-800000: ev.append((int(l['blockNumber'],16),int(l['data'][2+64:2+128],16)/1e12, int(l['timeStamp'],16)))
    for l in MB[n]['burn']:
        if s(l['topics'][2])<-800000: ev.append((int(l['blockNumber'],16),-int(l['data'][2:2+64],16)/1e12, int(l['timeStamp'],16)))
    ev.sort()
    sw=sorted((int(l['blockNumber'],16),(int(l['data'][2+128:2+192],16)/2**96)**2*1e12) for l in S[n])
    SB=[x[0] for x in sw]
    # block->time approx from events (2s blocks); anchor on last swap time unknown -> use mint timestamps for anchor
    b0,t0=ev[0][0],ev[0][2]
    L=0.0; j=0; first=sw[0][0]; last=max(sw[-1][0],ev[-1][0])
    for b in range(first,last+1,10800):
        while j<len(ev) and ev[j][0]<=b: L+=ev[j][1]; j+=1
        i=bisect.bisect_right(SB,b)-1
        if i<0: continue
        out.append((n,b,t0+(b-b0)*2,sw[i][1],max(L,0.0)))
json.dump(out,open('liq_6h.json','w')); print(len(out))
