"""Verify at one block using only eth_call and eth_getCode.

Usage: python verify_deployment.py RPC MANIFEST.json
Requires eth-abi and eth-utils. Run forge build first.
"""

import json
import sys
import urllib.request
from pathlib import Path
from eth_abi import encode
from eth_utils import keccak


def rpc(url, method, params):
    req = urllib.request.Request(
        url,
        json.dumps(dict(id=1, jsonrpc="2.0", method=method, params=params)).encode(),
        {"Content-Type": "application/json", "User-Agent": "HSK-code-verifier/1"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        obj = json.load(response)
    if "error" in obj:
        raise ValueError(obj["error"])
    return obj["result"]


def verify(url, manifest):
    artifact = json.loads(
        (
            Path(__file__).resolve().parents[1] / "out/Settlement.sol/Settlement.json"
        ).read_text()
    )
    block = hex(manifest["blockNumber"])
    assert int(rpc(url, "eth_chainId", []), 16) == manifest["chainId"]
    assert (
        rpc(url, "eth_getBlockByNumber", [block, False])["hash"]
        == manifest["blockHash"]
    )
    m = manifest["addresses"]
    args = [
        tuple(m[k] for k in ("whsk", "usdt", "pool", "router", "quoter")),
        m["admin"],
        m["operator"],
        m["feeRecipient"],
    ]
    encoded = encode(
        ["(address,address,address,address,address)", "address", "address", "address"],
        args,
    )
    init = artifact["bytecode"]["object"] + encoded.hex()
    runtime = rpc(url, "eth_call", [{"data": init}, block])
    actual = rpc(url, "eth_getCode", [m["settlement"], block])
    assert actual != "0x" and actual == runtime, (
        "runtime bytecode or immutable configuration mismatch"
    )
    for field in (
        "whsk",
        "usdt",
        "pool",
        "router",
        "quoter",
        "admin",
        "operator",
        "feeRecipient",
    ):
        data = "0x" + keccak(text=field + "()")[:4].hex()
        assert int(
            rpc(url, "eth_call", [{"to": m["settlement"], "data": data}, block]), 16
        ) == int(m[field], 16)
    return "0x" + keccak(bytes.fromhex(actual[2:])).hex()


if __name__ == "__main__":
    print(verify(sys.argv[1], json.loads(Path(sys.argv[2]).read_text())))
