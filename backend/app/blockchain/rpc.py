"""Read-only JSON-RPC transport. Batch results are ordered by request ID."""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[3]
CONFIG = json.loads((ROOT / "config/network/mainnet.json").read_text())
A = CONFIG["addresses"]
SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
CREATED = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
READ = {
    "eth_chainId",
    "eth_getBlockByNumber",
    "eth_getCode",
    "eth_call",
    "eth_estimateGas",
    "eth_gasPrice",
    "eth_getTransactionReceipt",
    "eth_getLogs",
    "eth_getBalance",
    "eth_getBlockByHash",
    "eth_getStorageAt",
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, data=None):
    for attempt in range(3):
        try:
            request = Request(
                url,
                data=None if data is None else json.dumps(data).encode(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "HSK-Smart-Execution/1",
                },
            )
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            if (
                attempt == 2
                or isinstance(exc, HTTPError)
                and exc.code not in (429, 502, 503, 504)
            ):
                raise
            time.sleep(2**attempt)


class RPC:
    def __init__(self, url=CONFIG["rpc"]):
        self.url = url
        if int(self.one("eth_chainId", []), 16) != CONFIG["chain_id"]:
            raise ValueError("chain ID mismatch")

    def batch(self, calls):
        if not calls:
            return []
        if any(m not in READ for m, _ in calls):
            raise ValueError("unsupported RPC method")
        req = [
            dict(id=i, jsonrpc="2.0", method=m, params=p)
            for i, (m, p) in enumerate(calls)
        ]
        items = fetch(self.url, req)
        if not isinstance(items, list):
            raise ValueError(f"invalid batch response: {items}")
        by_id = {item["id"]: item for item in items}
        if len(items) != len(req) or set(by_id) != set(range(len(req))):
            raise ValueError("incomplete RPC batch")
        for item in items:
            if "error" in item:
                raise ValueError(f"{req[item['id']]['method']}: {item['error']}")
        return [by_id[i]["result"] for i in range(len(req))]

    def one(self, method, params):
        return self.batch([(method, params)])[0]

    def block(self, ref):
        return self.one(
            "eth_getBlockByNumber", [hex(ref) if isinstance(ref, int) else ref, False]
        )


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("invalid address")
    return value.lower()


def word(value):
    if isinstance(value, str):
        value = int(address(value), 16)
    if type(value) is not int or not 0 <= value < 2**256:
        raise ValueError("invalid uint256")
    return f"{value:064x}"


def words(result):
    if not re.fullmatch(r"0x(?:[0-9a-fA-F]{64})+", result):
        raise ValueError("malformed ABI response")
    return [int(result[i : i + 64], 16) for i in range(2, len(result), 64)]


def signed(value):
    return value - 2**256 if value >= 2**255 else value


def addr_word(value):
    return address(f"0x{value:040x}")


def call(target, selector, *args, block):
    return "eth_call", [
        {"to": address(target), "data": "0x" + selector + "".join(map(word, args))},
        block,
    ]


def logs(target, topic, lo, hi):
    return "eth_getLogs", [
        dict(address=target, topics=[topic], fromBlock=hex(lo), toBlock=hex(hi))
    ]
