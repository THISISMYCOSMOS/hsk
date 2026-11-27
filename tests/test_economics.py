import unittest

from hsk.economics import minimum_economic_amount, quote


SNAPSHOT = {"block_number": 101}
COSTS = {"dex": 1, "direct": 2, "hybrid": 3, "per_order": 1}


def simulated(block, side, amount):
    assert block is SNAPSHOT
    assert side in ("buy", "sell") and amount > 0
    return amount * 9 // 10


def order(key, amount, **kwargs):
    return dict(id=key, offer=amount, want=amount, **kwargs)


def preview(amount, orders=(), **kwargs):
    return quote(SNAPSHOT, "WHSK", amount, orders, quote_fn=simulated, **kwargs)


class EconomicsTests(unittest.TestCase):
    def test_empty_book(self):
        result = preview(100)
        self.assertEqual(result["decision"], "dex_benchmark")
        self.assertEqual(result["baseline_out"], 90)
        self.assertIsNone(result["candidate"]["net_saving"])
        self.assertIsNone(result["realized_saving"])

    def test_cheaper_combination(self):
        result = preview(100, [order("a", 60, cost=2), order("b", 40, cost=1)], costs=COSTS,
                         operator={"revenue_usdt": 20, "cost_usdt": 25})
        choice = result["candidate"]
        self.assertEqual((choice["route"], choice["matched_in"], choice["out"]), ("direct", 100, 100))
        self.assertEqual(choice["net_saving"], 7)
        self.assertEqual(choice["fills"][0]["maker_net_saving"], 4)
        self.assertEqual(result["operator_profit_usdt_raw"], -5)
        self.assertIsNone(result["sequential_baseline_out"])

    def test_partial_hold_benchmark_uses_only_executed_size(self):
        choice = preview(100, [order("m", 40)], remainder="hold")["candidate"]
        self.assertEqual((choice["benchmark_out"], choice["held_in"], choice["gross_saving"]), (36, 60, 4))
        self.assertIsNone(choice["fills"][0]["maker_net_saving"])
        self.assertEqual(preview(100, [order("m", 40)], remainder="hold", min_out=101)["decision"], "hold")

    def test_hybrid_and_expensive_route(self):
        choice = preview(100, [order("m", 60)], costs=COSTS)["candidate"]
        self.assertEqual((choice["route"], choice["dex_in"], choice["gross_saving"], choice["net_saving"]),
                         ("hybrid", 40, 6, 3))
        no_gain = preview(100, [order("m", 60)], costs=dict(COSTS, hybrid=60))
        self.assertEqual(no_gain["decision"], "dex_benchmark")
        self.assertLess(no_gain["candidates"][1]["net_saving"], 0)

    def test_no_maker_subsidy(self):
        result = preview(100, [dict(id="a", want=100, offer=150)])
        self.assertEqual(result["candidates"][1]["exclusion"], "maker_no_positive_saving")
        self.assertEqual(result["decision"], "dex_benchmark")

    def test_rounding_minimum_fill_and_dedup(self):
        row = dict(id="a", want=103, offer=101)
        fill = preview(52, [row])["candidate"]["fills"][0]
        self.assertGreaterEqual(fill["taker_in"] * row["offer"], fill["taker_out"] * row["want"])
        self.assertLess((fill["taker_in"] - 1) * row["offer"], fill["taker_out"] * row["want"])
        self.assertEqual(preview(52, [dict(row, min_fill=51)])["decision"], "dex_benchmark")
        with self.assertRaises(ValueError):
            preview(52, [row, row])

    def test_reverse_quotes_and_integer_validation(self):
        result = quote(SNAPSHOT, "USDT", 100, [order("m", 200)], quote_fn=simulated)
        self.assertEqual(result["token_out"], "WHSK")
        self.assertEqual(result["candidate"]["out"], 100)
        for bad in (-1, True, 2.0, 0, 2**256):
            with self.assertRaises(ValueError):
                preview(bad)

    def test_grid_requires_positive_taker_and_maker_net(self):
        def threshold(rows, costs):
            return minimum_economic_amount(SNAPSHOT, "WHSK", [100, 20, 40], rows,
                                           costs=costs, quote_fn=simulated)
        self.assertEqual(threshold([order("a", 100, cost=3)], COSTS)["amount_in"], 40)
        self.assertEqual(threshold([order("a", 100)], COSTS)["status"], "costs_unmeasured")
        self.assertIsNone(threshold([order("a", 100, cost=20)], COSTS)["amount_in"])

    def test_archive_carries_first_trade_price_to_second_trade(self):
        from hsk.historical_comparison import replay
        data = replay()
        sell_buy, buy_sell = data["comparisons"]
        self.assertEqual(data["payment_usdt_raw"], 48486163)
        self.assertEqual(sell_buy["total_gross_saving"], 291315)
        self.assertEqual(buy_sell["total_gross_saving"], 291372)
        self.assertIsNone(buy_sell["net_saving"])

    def test_rpc_failure_never_synthesizes_an_output(self):
        def failing(snapshot, side, amount):
            if side == "buy":
                raise ConnectionError("RPC unavailable")
            return amount * 9 // 10
        with self.assertRaises(ConnectionError):
            quote(SNAPSHOT, "WHSK", 100, [order("m", 100)], quote_fn=failing)


if __name__ == "__main__":
    unittest.main()
