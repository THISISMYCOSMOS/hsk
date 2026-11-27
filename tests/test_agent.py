import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hsk import agent
from hsk.economics import quote


def simulated(snapshot, side, value):
    if side == "sell":
        return value * 9 // (10 * 10**12)
    return value * 9 * 10**12 // 10


def simulated_quote(*args, **kwargs):
    return quote(*args, **kwargs, quote_fn=simulated)


class AgentTests(unittest.TestCase):
    def cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = agent.main(args)
        return status, out.getvalue(), err.getvalue()

    def test_module_and_archived_data_are_separate(self):
        result = subprocess.run([sys.executable, "-m", "hsk", "--archive", "--json"],
                                capture_output=True, text=True, check=True)
        result = json.loads(result.stdout)
        self.assertEqual(result["evidence_mode"], "archived_state_reconstruction")
        self.assertEqual(result["quotes"][0]["amount_out_raw"], "80558131")
        self.assertEqual(self.cli(["sell", "10", "--archive"])[0], 1)

    def test_supported_amounts_and_ambiguous_requests(self):
        self.assertEqual(agent.intent(["1 USDT로 WHSK 매수"]), ("USDT", [10**6]))
        self.assertEqual(agent.intent(["10 WHSK 매도"]), ("WHSK", [10**19]))
        self.assertEqual(agent.amount(1000001, "USDT"), "1.000001 USDT")
        for value in ("1 WHSK 매수", "sell 1.0000000000000000001", "buy 1e-4", "매도 0"):
            with self.assertRaises(ValueError):
                agent.intent([value])

    def test_sweep_and_hypothetical_scenario(self):
        snapshot = {"block_number": 1, "block_hash": "fixture"}
        with tempfile.TemporaryDirectory() as tmp, patch.object(agent, "get_snapshot", return_value=snapshot) as read, \
                patch.object(agent, "quote", simulated_quote):
            file = Path(tmp, "orders.json")
            file.write_text(json.dumps({"token_in": "WHSK", "orders": [
                {"id":"demo", "offer": 1_000_000, "want": 10**18}
            ]}))
            code, text, _ = self.cli(["sell", "1", "2", "--scenario", str(file), "--block", "1", "--json"])
            self.assertEqual(code, 0)
            rows = json.loads(text)["rows"]
            self.assertEqual([r["candidate"]["route"] for r in rows], ["direct", "hybrid"])
            self.assertIsNone(rows[0]["candidate"]["net_saving"])
            read.assert_called_once_with(1)
            self.assertEqual(self.cli(["buy", "1", "--scenario", str(file)])[0], 1)
            code, text, _ = self.cli(["buy", "1", "2", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual([r["decision"] for r in json.loads(text)["rows"]], ["dex_benchmark"] * 2)
            file.write_text(json.dumps({"token_in": "USDT", "orders": [
                {"id": "demo", "offer": 2 * 10**18, "want": 2_000_000, "cost": 1}
            ], "costs": {"dex": 0, "hybrid": 1, "direct": 1, "per_order": 0}}))
            code, text, _ = self.cli(["buy", "2", "1", "--scenario", str(file), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text)["minimum_tested_input"]["amount_in"], 1_000_000)

    def test_rpc_failure_has_no_fallback_quote(self):
        with patch.object(agent, "get_snapshot", side_effect=ConnectionError("rpc unreachable")):
            code, out, err = self.cli(["sell", "1"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("rpc unreachable", err)

    def test_watch_requotes_only_on_changes(self):
        blocks = [{"block_number": n, "block_hash": str(n)} for n in [1, 1, 2, 2]]
        scenarios = [{}, {}, {}, {"min_out": 1}]
        with patch.object(agent, "get_snapshot", side_effect=blocks), \
                patch.object(agent, "load_scenario", side_effect=scenarios), \
                patch.object(agent, "quote", simulated_quote), \
                patch.object(agent.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt()]):
            code, text, _ = self.cli(["buy", "1", "--watch", "1", "--json"])
        self.assertEqual(code, 130)
        self.assertEqual([json.loads(r)["market"]["block_number"] for r in text.splitlines()], [1, 2, 2])


if __name__ == "__main__":
    unittest.main()
