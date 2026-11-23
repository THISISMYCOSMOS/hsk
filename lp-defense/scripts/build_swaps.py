# whsk.json(decode.py 결과)에서 스왑 표를 만든다. 블록 시간은 2.0초로 환산한다(실측 평균 2.0초).
import json, pandas as pd
from rpc import rpc
L = json.load(open('whsk.json'))
sw = [d for d in L if d['ev'] == 'Swap']
b0, b1 = 17714162, 30553002
t0 = int(rpc("eth_getBlockByNumber", [hex(b0), False])['timestamp'], 16)
t1 = int(rpc("eth_getBlockByNumber", [hex(b1), False])['timestamp'], 16)
df = pd.DataFrame(sw)
df['ts'] = pd.to_datetime(t0 + (df.block - b0) * (t1 - t0) / (b1 - b0), unit='s')
df['px'] = (df.sqrtP / 2**96) ** 2 * 1e12      # USDT per WHSK (WHSK 18, USDT 6 decimals)
df['usd'] = df.a1.abs() / 1e6                    # 거래 규모(USDT)
df['Lk'] = df.L
df.to_pickle('whsk_sw.pkl')
print(len(df))
