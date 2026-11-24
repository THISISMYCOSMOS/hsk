from rpc import *
import json, math
H=json.load(open('hist.json'))
pools={'WETH':('0xb92b79ed6b370d5cfee2e14b1d0983c258304c16',18,6),'WHSK':('0x4ff515761864e7838b0adb8b5b2b8b7a068905dc',18,6),'WBTC':('0xd9ea2ce468957ba49ccc38c4758ed6ecd561449a',8,6)}
cur={}
for n,(a,d0,d1) in pools.items():
    r=ecall(a,'0x3850c7bd'); cur[n]=(int(r[2:66],16)/2**96)**2*10**(d0-d1)
pos=json.load(open('positions.json'))
live={str(q['id']):q for n in pos for q in pos[n]}
print('id pool owner | 넣은 USDT가치 | 끝(회수시점 또는 현재) LP가치+수수료 | 그대로 들고 있었으면 | 차이(LP-보유) | 원금대비')
for tid,t in H.items():
    p=t['pool']; a,d0,d1=pools[p]
    ev=sorted(t['ev'],key=lambda e:(e[1],['tr','inc','dec','col'].index(e[0])))
    x=y=0.0; dep=0.0; got_x=got_y=0.0; dec_x=dec_y=0.0; owner=None; last=None
    for e in ev:
        if e[0]=='tr':
            if e[3].endswith('0'*40): owner=e[4]
            continue
        a0=e[4]/10**d0; a1=e[5]/10**d1
        if e[0]=='inc': x+=a0; y+=a1
        if e[0]=='dec': x-=a0; y-=a1; dec_x+=a0; dec_y+=a1   # principal leaving -> reduce hodl basis
        if e[0]=='col': got_x+=a0; got_y+=a1
        last=e
    # net hodl basis = deposits - principal withdrawn (approx: treat withdrawals at that time as leaving both strategies equally) 
    closed = live.get(tid,{}).get('L',0)==0
    if closed:
        P=None
        # price at final dec
        decs=[e for e in ev if e[0]=='dec']; blk=decs[-1][1]
        r=ecall(a,'0x3850c7bd',hex(blk)); P=(int(r[2:66],16)/2**96)**2*10**(d0-d1)
        lp_val=(got_x)*P+got_y   # all collected (principal+fees) since everything withdrawn
        when=decs[-1][2]
    else:
        P=cur[p]; q=live[tid]
        sa=math.sqrt(1.0001**q['tl']); sb=math.sqrt(1.0001**q['tu']); sp=math.sqrt(P/10**(d0-d1))
        s=min(max(sp,sa),sb); L=q['L']
        ix=L*(sb-s)/(s*sb)/10**d0; iy=L*(s-sa)/10**d1
        lp_val=(ix+got_x)*P+iy+got_y; when='현재'
    # deposits in tokens
    inx=sum(e[4]/10**d0 for e in ev if e[0]=='inc'); iny=sum(e[5]/10**d1 for e in ev if e[0]=='inc')
    # deposit value at deposit times
    depv=0
    for e in ev:
        if e[0]=='inc':
            r=ecall(a,'0x3850c7bd',hex(e[1])); Pd=(int(r[2:66],16)/2**96)**2*10**(d0-d1); depv+=e[4]/10**d0*Pd+e[5]/10**d1
    hodl=inx*P+iny
    # for positions that withdrew and re-added mid-way, compare totals of tokens (in - collected) — approximate
    print(f'#{tid} {p} {owner[:10] if owner else "?"} | {depv:,.2f} | {lp_val:,.2f} ({when}) | {hodl:,.2f} | {lp_val-hodl:+,.2f} ({(lp_val/hodl-1)*100:+.2f}%) | {(lp_val/depv-1)*100:+.1f}%')
