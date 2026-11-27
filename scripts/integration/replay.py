"""Run retained upstream tests in disposable directories; export only reproduced outputs."""
import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / "backtests"
PUBLIC = ROOT / "frontend/public/evidence"
SCENARIOS = ("direct", "too_costly", "no_opposite", "no_fill", "buy_direct")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")
    os.chmod(out.name, 0o644)
    os.replace(out.name, path)


def replay():
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        a_path = ARCHIVES / "HSK_A_Session1.zip"
        b_path = ARCHIVES / "HSK_B_Session1_Verified.zip"
        with ZipFile(a_path) as archive:
            archive.extractall(stage)
        with ZipFile(b_path) as archive:
            archive.extractall(stage / "b")
        a = stage / "HSK_A_Session1"
        subprocess.run([sys.executable, "-m", "unittest", "-v", "test_routes"], cwd=a, check=True)
        subprocess.run([sys.executable, "routes.py"], cwd=a, check=True)
        with ZipFile(a_path) as original:
            scenarios = {}
            for name in SCENARIOS:
                member = f"fixtures/plans/{name}.json"
                data = json.loads((a / member).read_text())
                if data != json.loads(original.read(f"HSK_A_Session1/{member}")):
                    raise ValueError(f"regenerated plan differs: {name}")
                scenarios[name] = data
        subprocess.run([sys.executable, "verify.py"], cwd=stage / "b", check=True)
        summary = json.loads((stage / "b/data/summary.json").read_text())
        daily = defaultdict(lambda: {"buy": 0, "sell": 0, "count": 0})
        with (a / "upstream/swaps.csv").open() as stream:
            for row in csv.DictReader(stream):
                if row["base"] != "WHSK":
                    continue
                bucket = daily[row["utc"][:10]]
                usdt = int(row["amount1_raw"])
                bucket["buy" if usdt > 0 else "sell"] += abs(usdt)
                bucket["count"] += 1
        if sum(bucket["count"] for bucket in daily.values()) != summary["raw_swap_log_matches"]:
            raise ValueError("independent archive counts disagree")
        quote_path = ARCHIVES / "HSK_Session2_Quotes.zip"
        with ZipFile(quote_path) as archive:
            archive.extractall(stage / "q")
            previous = json.loads(archive.read("quotes.json"))
        fresh = json.loads(subprocess.check_output([sys.executable, "quotes.py"], cwd=stage / "q"))
        if fresh["quotes"] != previous["quotes"]:
            raise ValueError("archived quote reconstruction changed")
        return {"version": "agent-d-replay/1", "source": "BACKTEST", "archiveHashes": {
            p.name: sha256(p.read_bytes()).hexdigest() for p in (a_path, b_path, quote_path)},
            "market": {"matchedLogs": summary["raw_swap_log_matches"], "accepted": summary["by_reason"]["accepted"]["count"],
                       "days": [{"day": day, "buy": str(row["buy"]), "sell": str(row["sell"]), "count": row["count"]}
                                for day, row in sorted(daily.items())]},
            "quotes": fresh, "scenarios": {"source": "SYNTHETIC", "plans": scenarios},
            "executionReceipt": None, "realizedSavings": None}


if __name__ == "__main__":
    report = replay()
    write(PUBLIC / "replay.json", report)
    print(f"Reproduced {report['market']['matchedLogs']} archived logs and {len(SCENARIOS)} scenario fixtures.")
