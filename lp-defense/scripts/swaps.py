import json, datetime as dt, urllib.request
S=json.load(open('swaps.json'))
t0=dt.datetime(2026,10,24,15,tzinfo=dt.timezone.utc).timestamp(); t1=dt.datetime(2026,11,23,15,tzinfo=dt.timezone.utc).timestamp()
def s(x):
    v=int(x,16); return v-2**256 if v>2**255 else v
out={}
for n,L in S.items():
    rows=[]
    for l in L:
        ts=int(l['timeStamp'],16)
        if not (t0<=ts<t1): continue
        d=l['data'][2:]; a0=s(d[0:64])/1e18; a1=s(d[64:128])/1e6; sp=int(d[128:192],16)/2**96
        rows.append(dict(ts=ts,blk=int(l['blockNumber'],16),a0=a0,a1=a1,px=sp**2*1e12,tx=l['transactionHash'],sender=l['topics'][1][-40:],rcpt=l['topics'][2][-40:]))
    rows.sort(key=lambda r:(r['blk']))
    vol=sum(abs(r['a1']) for r in rows)
    px=[r['px'] for r in rows]
    print(n,'swaps',len(rows),'volume USDT',round(vol),'fees(0.3%)',round(vol*0.003,1),'start',round(px[0],5),'end',round(px[-1],5),'min',round(min(px),5),'max',round(max(px),5),'recipients',len(set(r['rcpt'] for r in rows)))
    big=sorted(rows,key=lambda r:-abs(r['a1']))[:3]
    for b in big: print('  big',dt.datetime.fromtimestamp(b['ts'],dt.timezone.utc).isoformat(),round(b['a1'],1),round(b['px'],5))
    out[n]=rows
json.dump(out,open('swaps_parsed.json','w'))
