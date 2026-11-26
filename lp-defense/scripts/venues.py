# 최근 30일 WHSK·USDT Transfer 로그에서 두 토큰을 모두 주고받은 주소(거래처 후보)를 찾는다
import json,sys,collections as C
from concurrent.futures import ThreadPoolExecutor
import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rpc import call
WHSK='0xb210d2120d57b758ee163cffb43e73728c471cf1'; USDT='0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029'
TR='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
end=int(call('eth_blockNumber',[]),16)-5; start=end-30*43200
def chunk(b):
    for i in range(8):
        try: return call('eth_getLogs',[{'address':[WHSK,USDT],'topics':[TR],'fromBlock':hex(b),'toBlock':hex(min(b+4999,end))}])
        except Exception: import time; time.sleep(3*(i+1))
    raise Exception(b)
with ThreadPoolExecutor(8) as ex: logs=[l for p in ex.map(chunk,range(start,end+1,5000)) for l in p]
print('logs',len(logs))
st=C.defaultdict(lambda:{'w_in':0,'w_out':0,'u_in':0,'u_out':0,'n':0})
for l in logs:
    a=l['address'].lower(); f='0x'+l['topics'][1][-40:]; t='0x'+l['topics'][2][-40:]; v=int(l['data'],16)
    k='w' if a==WHSK else 'u'; v=v/1e18 if k=='w' else v/1e6
    st[f][k+'_out']+=v; st[t][k+'_in']+=v; st[f]['n']+=1; st[t]['n']+=1
json.dump({k:v for k,v in st.items()},open(sys.argv[1],'w'))
cand=[(a,s) for a,s in st.items() if s['w_in']>0 and s['w_out']>0 and s['u_in']>0 and s['u_out']>0]
cand.sort(key=lambda x:-(x[1]['u_in']+x[1]['u_out']))
for a,s in cand[:25]:
    print(a, f"USDT in {s['u_in']:,.0f} out {s['u_out']:,.0f} | WHSK in {s['w_in']:,.0f} out {s['w_out']:,.0f} | n {s['n']}")
