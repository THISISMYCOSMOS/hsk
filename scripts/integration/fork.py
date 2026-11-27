"""Compare actual QuoterV2 return words on a local fork to the archive controls."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]


def rpc(url, method, params):
    req = urllib.request.Request(url, json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params)).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "HSK-Integration/1"})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = json.load(res)
    if data.get("error") or data.get("result") is None:
        raise RuntimeError(str(data.get("error", "missing RPC result")))
    return data["result"]


def main():
    with ZipFile(ROOT / "backtests/HSK_Session2_Quotes.zip") as archive:
        expected = json.loads(archive.read("quotes.json"))
    url = os.environ.get("HSK_FORK_RPC", "https://mainnet.hsk.xyz")
    if int(rpc(url, "eth_chainId", []), 16) != 177:
        raise RuntimeError("wrong upstream chain")
    block = expected["block"]
    if rpc(url, "eth_getBlockByNumber", [hex(block), False])["hash"] != expected["block_hash"]:
        raise RuntimeError("archived block hash mismatch")
    anvil = shutil.which("anvil") or str(Path.home() / ".foundry/bin/anvil")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as tmp:
        node = subprocess.Popen([anvil, "--silent", "--host", "127.0.0.1", "--port", str(port),
                                 "--fork-url", url, "--fork-block-number", str(block), "--chain-id", "31337",
                                 "--no-storage-caching"], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            local = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if node.poll() is not None:
                    raise RuntimeError("local Anvil fork startup failed")
                try:
                    chain = rpc(local, "eth_chainId", [])
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("fork startup timeout")
            if int(chain, 16) != 31337 or int(rpc(local, "eth_blockNumber", []), 16) != block:
                raise RuntimeError("unexpected local fork state")
            for q in expected["quotes"]:
                payload = q["request"]["params"][0]
                raw = rpc(local, "eth_call", [payload, "latest"])
                if len(raw) != 258:
                    raise RuntimeError("incomplete QuoterV2 return")
                variable = q["amount_out_raw" if q["kind"] == "exact_input" else "amount_in_raw"]
                if (int(raw[2:66],16), int(raw[66:130],16)) != (int(variable),int(q["sqrt_price_after_x96"])):
                    raise RuntimeError(f"fork quote differs for {q['id']}")
            print(f"FORK_SIMULATION · 3 QuoterV2 responses · upstream 177/{block} · local 31337")
        finally:
            node.terminate()
            node.wait(timeout=10)


if __name__ == "__main__":
    main()
