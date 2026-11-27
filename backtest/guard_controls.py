"""Re-run C's isolated guard comparisons against the pinned fork in a disposable build directory."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from eth_abi import decode
from eth_utils import keccak
from backend.app.blockchain.rpc import CONFIG, ROOT
from backtest.collect import save


def controls(repo, commit):
    with tempfile.TemporaryDirectory() as d:
        proc = subprocess.Popen(
            ["git", "-C", str(repo), "archive", commit, "contracts"],
            stdout=subprocess.PIPE,
        )
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            archive.extractall(d, filter="data")
        if proc.wait() != 0:
            raise RuntimeError("could not read Agent C snapshot")
        exe = shutil.which("forge") or str(Path.home() / ".foundry/bin/forge")
        args = [
            exe,
            "test",
            "--match-contract",
            "ForkTest",
            "--fork-url",
            CONFIG["rpc"],
            "--fork-block-number",
            "30592078",
            "--offline",
            "--no-storage-caching",
            "-vvvv",
            "--json",
        ]
        result = subprocess.check_output(
            args,
            cwd=Path(d) / "contracts",
            env={**os.environ, "HSK_FORK_TEST": "true"},
            timeout=300,
        )
        suite = next(iter(json.loads(result).values()))["test_results"]
        rows = []
        topic = "0x" + keccak(text="Sample(string,uint256,uint256)").hex()
        for name, v in suite.items():
            if v["status"] != "Success":
                raise ValueError(name)
            for kind, trace in v["traces"]:
                if kind != "Execution":
                    continue
                for log in trace["arena"][0]["logs"]:
                    e = log.get("raw_log", log)
                    if e["topics"][0] != topic:
                        continue
                    label, gas, size = decode(
                        ["string", "uint256", "uint256"], bytes.fromhex(e["data"][2:])
                    )
                    rows.append(
                        dict(
                            test=name,
                            scenario=label,
                            call_gas=str(gas),
                            calldata_bytes=size,
                        )
                    )
        if not {
            "interval-state-match-direct",
            "single-band-direct",
            "signed-limits-only-direct",
            "direct",
        } <= {r["scenario"] for r in rows}:
            raise ValueError("missing guard comparison")
        save(
            ROOT / "reports/economics/guard_controls.json",
            dict(
                commit=commit,
                block=30592078,
                evidence="FORK_SIMULATION",
                scope="Caller gas delta inside Foundry test transaction, excludes initial cache build and L1",
                tests=len(suite),
                rows=rows,
            ),
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    controls(a.repo, a.commit)
