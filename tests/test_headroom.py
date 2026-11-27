import unittest

from hsk.headroom import compare


class HeadroomTest(unittest.TestCase):
    def test_archive_scenario(self):
        # Three independent quotations reconstructed in HSK_Session2_Quotes.zip.
        unit = 10**18
        snapshot = {"decimals_whsk": 18, "decimals_usdt": 6}
        bids = {("sell", 1000 * unit): 80558131, ("sell", 400 * unit): 32226965}
        asks = {("buy", 600 * unit): 48641160}
        result = compare(snapshot, "WHSK", ["1000"], 6000,
                         lambda s, direction, quantity: bids[direction, quantity],
                         lambda s, direction, quantity: asks[direction, quantity])
        self.assertEqual(result["rows"][0]["shared_gross_margin_raw"], "309994")
        self.assertIsNone(result["participant_net_saving"])
        self.assertIsNone(result["rows"][0]["conditional_net_margin_raw"])

    def test_full_match_and_reverse_direction(self):
        calls = []

        def read(s, direction, amount):
            calls.append((direction, amount))
            return 100

        row = compare({"decimals_usdt": 6}, "USDT", ["0.1"], 10000, read, read, extra_cost=5)
        self.assertEqual(calls, [("buy", 100000), ("sell", 100000)])
        self.assertEqual(row["report_token"], "WHSK")
        self.assertEqual(row["rows"][0]["shared_gross_margin_raw"], "0")
        self.assertEqual(row["rows"][0]["conditional_net_margin_raw"], "-5")

    def test_amount_must_fit_token(self):
        for value in ("-1", "0", "1.0000001", "1e-100000", "nan", "inf", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare({}, "USDT", [value], 6000, None, None)
