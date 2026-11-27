"""Read-only HSK deployment identity and periphery checks at the fixture block."""

import datetime
import json
import sys
import urllib.request
from pathlib import Path

RPC = "https://mainnet.hsk.xyz"
BLOCK = 30592078
HASH = "0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda"
ADDRESSES = dict(
    whsk="0xb210d2120d57b758ee163cffb43e73728c471cf1",
    usdt="0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029",
    factory="0x972ca9d1662f5e029cd18327d29026532e84c742",
    pool="0x4ff515761864e7838b0adb8b5b2b8b7a068905dc",
    router="0x2c16f75b95cf1390c328ab70e2cee7f4b80bd8f3",
    quoter="0x603f70466fddbe3f238220b9a74fff419a2bbfdd",
)


def rpc(method, params):
    req = urllib.request.Request(
        RPC,
        json.dumps(dict(id=1, jsonrpc="2.0", method=method, params=params)).encode(),
        {"Content-Type": "application/json", "User-Agent": "HSK-Settlement-readonly/1"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        obj = json.load(response)
    if "error" in obj:
        raise RuntimeError(obj["error"])
    return obj["result"]


def observe():
    block = hex(BLOCK)
    b = rpc("eth_getBlockByNumber", [block, False])
    assert b["hash"] == HASH and int(rpc("eth_chainId", []), 16) == 177

    def call(name, data):
        return rpc("eth_call", [dict(to=ADDRESSES[name], data=data), block])

    def word(i):
        return f"{i:064x}"

    args = "".join(word(int(ADDRESSES[n], 16)) for n in ("whsk", "usdt"))
    reads = {}
    for n in ("router", "quoter", "pool"):
        reads[n + "Factory"] = call(n, "0xc45a0155")
        assert int(reads[n + "Factory"], 16) == int(ADDRESSES["factory"], 16)
    reads["pool"] = call("factory", "0x1698ee82" + args + word(3000))
    assert int(reads["pool"], 16) == int(ADDRESSES["pool"], 16)
    for n, d in [("whsk", 18), ("usdt", 6)]:
        reads[n + "Decimals"] = call(n, "0x313ce567")
        assert int(reads[n + "Decimals"], 16) == d
    quotes = {}
    for side, selector, assets in [
        ("sell", "c6a5026a", ("whsk", "usdt")),
        ("buy", "bd21704a", ("usdt", "whsk")),
    ]:
        payload = (
            "0x"
            + selector
            + "".join(word(int(ADDRESSES[n], 16)) for n in assets)
            + word(10**18)
            + word(3000)
            + word(0)
        )
        reply = call("quoter", payload)
        assert len(reply) == 258
        quotes[side] = dict(
            calldata=payload,
            result=reply,
            fixedWHSK=str(10**18),
            cashUSDT=str(int(reply[2:66], 16)),
        )
    return dict(
        version="1",
        evidence="OBSERVED_MAINNET",
        chainId=177,
        blockNumber=BLOCK,
        blockHash=HASH,
        observedUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        rpc=RPC,
        addresses=ADDRESSES,
        rawReads=reads,
        quotes=quotes,
    )


if __name__ == "__main__":
    result = json.dumps(observe(), indent=2) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(result)
    else:
        print(result)
