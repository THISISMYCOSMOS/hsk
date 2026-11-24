from rpc import *
import json, math
pos=json.load(open('positions.json'))
pools={'WETH':('0xb92b79ed6b370d5cfee2e14b1d0983c258304c16',18,6),'WHSK':('0x4ff515761864e7838b0adb8b5b2b8b7a068905dc',18,6),'WBTC':('0xd9ea2ce468957ba49ccc38c4758ed6ecd561449a',8,6)}
for n,(p,d0,d1) in pools.items():
    s0=ecall(p,'0x3850c7bd'); sp=int(s0[2:66],16)/2**96
    price=sp**2*10**(d0-d1)
    tot=0
    for q in pos[n]:
        if not q['L']: continue
        sa=math.sqrt(1.0001**q['tl']); sb=math.sqrt(1.0001**q['tu'])
        L=q['L']; s=min(max(sp,sa),sb)
        a0=L*(sb-s)/(s*sb)/10**d0; a1=L*(s-sa)/10**d1
        v=a0*price+a1; tot+=v
        lo=1.0001**q['tl']*10**(d0-d1); hi=1.0001**q['tu']*10**(d0-d1)
        rng='full' if q['tl']<-800000 else f'{lo:.5g}~{hi:.5g}'
        print(n,q['id'],q['owner'][:10],rng,'in' if sa<=sp<=sb else 'OUT', f'{v:,.2f} USDT', f'tok {a0:.6g} usdt {a1:.2f}')
    print(n,'price',round(price,6),'total',f'{tot:,.0f}')
