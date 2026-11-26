import json,sys
D=sys.argv[1]; S=json.load(open(f'{D}/swaps_all.json')); X=json.load(open(f'{D}/ext.json'))
def i256(h):
    v=int(h,16); return v-(1<<256) if v>=1<<255 else v
now=max(int(l['timeStamp'],16) for n in S for l in S[n])
for n,k in (('WETH','eth_1m'),('WHSK','hsk_1m')):
    em=dict(X[k]); t0=max(min(em),now-60*86400); row=[]
    for lag in (-5,-1,0,1,5):
        tot=0
        for l in S[n]:
            t=int(l['timeStamp'],16)
            if t<t0: continue
            d=l['data'][2:]; a0=i256(d[:64])/1e18; a1=i256(d[64:128])/1e6
            c=em.get((t//60+lag)*60)
            if c: tot+=a0*c+a1
        row.append(f'{lag:+d}분 {tot:+.0f}')
    print(n,' / '.join(row))
