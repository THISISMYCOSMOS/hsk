import json
import unittest
from datetime import datetime
from unittest.mock import Mock
from backend.app.blockchain.rpc import A, ROOT, word
from backend.app.market_data.provider import MarketData
from backtest.collect import unpack
from backtest.market_study import replay

END = 30709982
RAW = ROOT / f"data/raw/{END}"
REPORTS = ROOT / "reports/economics"


def read(path):
    return json.loads(path.read_text())


class Regression(unittest.TestCase):
    def test_complete_window_receipts(self):
        c = read(RAW / "coverage.json")
        self.assertEqual(c["evidence"], "OBSERVED_MAINNET")
        self.assertEqual(c["gaps"], [])
        start = int(datetime.fromisoformat(c["utc_start_exclusive"]).timestamp())
        end = int(datetime.fromisoformat(c["utc_end_inclusive"]).timestamp())
        self.assertEqual(end - start, 30 * 86400)
        cursor = c["start_block"]
        raw = {}
        for p in sorted(RAW.glob("logs-*.json.gz")):
            lo, hi = map(int, p.name.split(".")[0].split("-")[1:])
            self.assertEqual(cursor, lo)
            cursor = hi + 1
            for r in unpack(p):
                self.assertTrue(lo <= int(r["blockNumber"], 16) <= hi)
                raw[(r["transactionHash"], int(r["logIndex"], 16))] = r
        self.assertEqual(cursor, END + 1)
        receipts = {
            r["transactionHash"]: r
            for p in RAW.glob("eth_getTransactionReceipt*.gz")
            for r in unpack(p)
        }
        clean = unpack(ROOT / c["processed"])
        self.assertEqual(len(clean), len(raw))
        for v in clean:
            tx = v["transaction_hash"]
            r = raw[tx, v["log_index"]]
            receipt = receipts[tx]
            self.assertEqual(int(r["blockTimestamp"], 16), v["timestamp"])
            self.assertTrue(start < v["timestamp"] <= end)
            self.assertEqual(receipt["blockHash"], v["block_hash"])
            self.assertEqual(int(receipt["status"], 16), 1)
            self.assertEqual(receipt["from"].lower(), v["transaction_sender"])
            data = bytes.fromhex(r["data"][2:])
            self.assertEqual(
                int.from_bytes(data[:32], "big", signed=True), int(v["amount0"])
            )
            self.assertEqual(
                int.from_bytes(data[32:64], "big", signed=True), int(v["amount1"])
            )

    def test_reorg_and_failure_have_no_balance(self):
        rpc = Mock(url="fixture")
        rpc.block.side_effect = [
            dict(number="0x1", hash="a"),
            dict(number="0x1", hash="b"),
        ]
        rpc.one.return_value = "0x" + word(0)
        p = MarketData(rpc)
        res = p.get_wallet_balance(A["router"], A["WHSK"], 1)
        self.assertIsNone(res["data"])
        self.assertIsNotNone(res["error"])
        rpc.block.side_effect = OSError("unavailable")
        self.assertIsNone(p.get_wallet_balance(A["router"], A["WHSK"], 1)["data"])

    def test_cache_is_keyed_by_hash_and_inputs(self):
        rpc = Mock(url="fixture")
        rpc.block.return_value = dict(number="0x1", hash="a")
        rpc.one.side_effect = ["0x" + word(x) for x in (2**180, 7, 9)]
        p = MarketData(rpc)
        args = (A["router"], A["WHSK"], 1)
        data = p.get_wallet_balance(*args)
        self.assertEqual(data["data"], str(2**180))
        self.assertEqual(p.get_wallet_balance(*args), data)
        self.assertEqual(p.get_wallet_balance(A["pool"], A["WHSK"], 1)["data"], "7")
        rpc.block.return_value = dict(number="0x1", hash="c")
        self.assertEqual(p.get_wallet_balance(*args)["data"], "9")
        self.assertEqual(rpc.one.call_count, 3)

    def test_no_self_match_expiry_or_future_users(self):
        def evt(t, sell, owner):
            return dict(
                timestamp=t,
                sqrt_price_x96=str(2**96),
                amount0="100000" if sell else "-100000",
                direction="sell_token0" if sell else "buy_token0",
                transaction_sender=owner,
            )

        rows = [
            evt(0, True, "a"),
            evt(1, False, "a"),
            evt(2, True, "a"),
            evt(3602, True, "b"),
        ]
        self.assertEqual(replay(rows, 4000, 1)["pair_fills"], 0)
        rows[-1]["timestamp"] = 3600
        self.assertEqual(replay(rows, 3600, 1)["pair_fills"], 1)
        self.assertEqual(replay(rows, 1, 1)["pair_fills"], 0)
        self.assertEqual(replay(rows, 4000, 0)["pair_fills"], 0)

    def test_ledger_conservation_and_version(self):
        for s in read(REPORTS / "preorders.json")["scenarios"]:
            rem = int(s["unmatched_whsk_raw"])
            self.assertEqual(
                rem + 2 * int(s["direct_whsk_once_raw"]), int(s["submitted_whsk_raw"])
            )
            self.assertEqual(
                rem,
                int(s["open_at_cutoff_whsk_raw"])
                + int(s["expired_or_immediate_unfilled_whsk_raw"]),
            )
            self.assertIsNone(s["realized_user_savings"])
        import hashlib

        data = read(REPORTS / "settlement_fork.json")
        self.assertEqual(
            data["settlement"]["artifact_sha256"],
            hashlib.sha256(
                (ROOT / "data/fixtures/market/settlement-build.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            int(data["scenarios"]["C_transfer_legs"]["joint_cash_usdt_raw"])
            - int(data["scenarios"]["A_sell_first"]["joint_cash_usdt_raw"]),
            291315,
        )
        c = data["settlement"]["results"]
        self.assertEqual(
            sum(int(d["USDT"]) for d in c["partial"]["wallet_deltas"].values()),
            32226965,
        )
        self.assertGreater(int(c["no_trade"]["gas_used"]), 0)
        self.assertGreater(int(c["expired"]["gas_used"]), 0)

    def test_schema_fixtures(self):
        from jsonschema import Draft202012Validator

        for name in ("MarketSnapshot", "DexQuote"):
            schema = read(ROOT / f"shared/proposals/agent-a-v1/{name}.schema.json")
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            fixture = read(ROOT / f"data/fixtures/market/{name}.json")
            validator.validate(fixture)
            validator.validate(
                {
                    **fixture,
                    "data": None,
                    "evidence": "UNVERIFIED",
                    "error": "unavailable",
                }
            )
            self.assertFalse(validator.is_valid({**fixture, "data": None}))


if __name__ == "__main__":
    unittest.main()
