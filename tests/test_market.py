import unittest
from unittest.mock import patch

from backend.app.blockchain.rpc import A, word
from hsk import market


def encoded(*values):
    return "0x" + "".join(word(value) for value in values)


class MarketTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("hsk.market.RPC")
        self.addCleanup(patcher.stop)
        self.rpc = patcher.start().return_value
        self.header = dict(number="0x2a", hash="0x" + "11"*32, timestamp="0x100")
        self.rpc.block.return_value = self.header
        self.identity = [encoded(18), encoded(6), encoded(A["factory"]), encoded(0),
                         encoded(0), encoded(A["pool"]), encoded(0)]
        self.pool = [encoded(A["WHSK"]), encoded(A["USDT"]), encoded(3000), encoded(A["factory"]),
                     encoded(100), encoded(2**96, 2**256-3, 1, 1, 1, 0, 1)]

    def test_pinned_identity_and_metadata(self):
        self.rpc.batch.side_effect = [self.identity, self.pool]
        snapshot = market.get_snapshot(42)
        self.assertEqual(snapshot["pools"][0]["address"], A["pool"])
        self.assertEqual(snapshot["pools"][0]["tick"], -3)
        self.assertEqual(snapshot["block_hash"], self.header["hash"])
        self.assertEqual(snapshot["decimals_usdt"], 6)
        for batch in self.rpc.batch.call_args_list:
            self.assertTrue(all(row[1][-1] == "0x2a" for row in batch.args[0]))

    def test_wrong_pool_token_rejected(self):
        self.pool[1] = encoded(A["WHSK"])
        self.rpc.batch.side_effect = [self.identity, self.pool]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            market.get_snapshot(42)

    def test_quote_picks_best_in_and_out_and_rejects_reorg(self):
        snapshot = dict(chain_id=177, block_number=42, block_hash=self.header["hash"],
                        pools=[{"fee": 500}, {"fee": 3000}])
        data = [encoded(305, 2**96, 1, 100), encoded(309, 2**96, 1, 100), self.header]
        self.rpc.batch.return_value = data
        self.assertEqual(market.quote_exact_input(snapshot, "sell", 13), 309)
        req = self.rpc.batch.call_args.args[0][0][1][0]["data"]
        self.assertEqual(req, "0xc6a5026a" + encoded(A["WHSK"], A["USDT"], 13, 500, 0)[2:])
        self.assertEqual(market.quote_exact_output(snapshot, "buy", 13), 305)
        req = self.rpc.batch.call_args.args[0][0][1][0]["data"]
        self.assertEqual(req, "0xbd21704a" + encoded(A["USDT"], A["WHSK"], 13, 500, 0)[2:])
        self.header["hash"] = "0x" + "22"*32
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            market.quote_exact_input(snapshot, "sell", 13)

    def test_one_candidate_failure_invalidates_comparison(self):
        snapshot = dict(chain_id=177, block_number=42, block_hash=self.header["hash"],
                        pools=[{"fee": 500}, {"fee": 3000}])
        self.rpc.batch.return_value = [encoded(3, 2**96, 0, 100), "0x", self.header]
        with self.assertRaises(ValueError):
            market.quote_exact_input(snapshot, "sell", 13)
        self.rpc.batch.return_value = [encoded(3, 2**96, 0, 100),
                                      encoded(1, market.MIN_SQRT_RATIO + 1, 0, 100), self.header]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            market.quote_exact_input(snapshot, "sell", 13)


if __name__ == "__main__":
    unittest.main()
