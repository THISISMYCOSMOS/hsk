import json, urllib.request, urllib.error, sys
RPC="https://mainnet.hsk.xyz"
def call(method, params):
    import time
    for i in range(6):
        try: return _call(method, params)
        except urllib.error.HTTPError as e:
            if e.code==400: raise
            time.sleep(2*(i+1))
        except (urllib.error.URLError, ConnectionError, TimeoutError): time.sleep(2*(i+1))
    return _call(method, params)
def _call(method, params):
    req=urllib.request.Request(RPC, data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(), headers={"content-type":"application/json","user-agent":"research-script"})
    r=json.load(urllib.request.urlopen(req, timeout=60))
    if "error" in r: raise Exception(r["error"])
    return r["result"]
def ecall(to, data, block="latest"):
    return call("eth_call",[{"to":to,"data":data},block])
def addr(x): return "0x"+x[-40:]
def bs(path):
    import time
    for i in range(8):
        try:
            req=urllib.request.Request("https://hsk.blockscout.com"+path, headers={"accept":"application/json","user-agent":"research-script"})
            r=json.load(urllib.request.urlopen(req, timeout=60)); time.sleep(2); return r
        except urllib.error.HTTPError as e:
            if e.code!=429: raise
            time.sleep(10*(i+1))
    raise Exception("rate limited")
