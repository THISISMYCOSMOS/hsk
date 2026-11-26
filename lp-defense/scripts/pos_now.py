import sys; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rpc import ecall
NPM='0xdf0a9b833db0e4ceea103a4408f3b68e7fc0cad5'
P={'0xefd4bc9afd210517803f293ababd701caeecdfd0':('WETH',18),'0xb210d2120d57b758ee163cffb43e73728c471cf1':('WHSK',18),'0x93919784c523f39cacaa98ee0a9d96c3f32b593f':('WBTC',8)}
import math
POOL={'WETH':'0xb92b79ed6b370d5cfee2e14b1d0983c258304c16','WHSK':'0x4ff515761864e7838b0adb8b5b2b8b7a068905dc'}
spot={}
for k,a in POOL.items():
    r=ecall(a,'0x3850c7bd'); spot[k]=int(r[2:66],16)/2**96
def s(t): return 1.0001**(t/2)
tot={}
for i in range(1,40):
    try: r=ecall(NPM,'0x99fbab88'+hex(i)[2:].rjust(64,'0'))
    except Exception: continue
    w=[r[2+64*j:2+64*(j+1)] for j in range(12)]
    t0='0x'+w[2][-40:]; lo=int(w[5],16); hi=int(w[6],16)
    lo=lo-(1<<256) if lo>=1<<255 else lo; hi=hi-(1<<256) if hi>=1<<255 else hi
    L=int(w[7],16)
    t1='0x'+w[3][-40:]; fee=int(w[4],16)
    if L==0 or t0 not in P or t1!='0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029' or fee!=3000: continue
    name,dec=P[t0]
    if name not in spot: continue
    sp=spot[name]; a,b=s(lo),s(hi); c=min(max(sp,a),b)
    x=L*(1/c-1/b); y=L*(c-a)
    val=x*sp*sp+y
    full= lo<=-887000
    print(f'#{i} {name} {"전구간" if full else "범위"} 가치 {val/1e6:,.2f} USDT  범위안 {a<=sp<=b}')
    key=(name,'전구간' if full else '범위'); tot[key]=tot.get(key,0)+val/1e6
print(tot)
