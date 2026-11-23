import requests, json, time
RPC="https://mainnet.hsk.xyz"
BS="https://hsk.blockscout.com/api/v2"
def rpc(method, params):
    for i in range(5):
        try:
            r=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":method,"params":params},timeout=30).json()
            if 'error' in r: raise Exception(r['error'])
            return r['result']
        except Exception as e:
            if i==4: raise
            time.sleep(1+i)
def call(to,data,block="latest"):
    if isinstance(block,int): block=hex(block)
    return rpc("eth_call",[{"to":to,"data":data},block])
def words(h):
    h=h[2:]; return [h[i:i+64] for i in range(0,len(h),64)]
def toint(w,signed=False):
    v=int(w,16)
    if signed and v>=2**255: v-=2**256
    return v
def addr(w): return "0x"+w[-40:]
def bs(path,params=None):
    for i in range(6):
        try:
            r=requests.get(BS+path,params=params,timeout=60)
            if r.status_code==200: return r.json()
            time.sleep(2+i)
        except Exception as e:
            time.sleep(2+i)
    raise Exception("bs fail "+path)
