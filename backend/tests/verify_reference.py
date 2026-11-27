"""Read-only recheck of archived calldata against Agent A's chain-bound provider."""

import argparse
import json
import sys
import zipfile
from pathlib import Path


def run(provider_root):
    sys.path.insert(0, str(provider_root.resolve()))
    from backend.app.market_data.provider import MarketData

    root = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(root / "backtests/HSK_Session2_Quotes.zip") as archive:
        ref = json.loads(archive.read("quotes.json"))
    provider = MarketData()
    evidence = []
    for r in ref["quotes"]:
        buy = r["kind"] == "exact_output"
        read = provider.get_dex_quote_exact_out if buy else provider.get_dex_quote_exact_in
        size = int(r["amount_out_raw" if buy else "amount_in_raw"])
        result = read(r["token_in"], r["token_out"], size, ref["block"])
        assert not result["error"] and result["block_hash"] == ref["block_hash"], result
        for key in ("amount_in", "amount_out"):
            assert result["data"][key] == r[key + "_raw"]
        evidence.append(result)
    return evidence


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--provider-root", type=Path, default=Path.cwd())
    print(json.dumps(run(p.parse_args().provider_root), indent=2))
