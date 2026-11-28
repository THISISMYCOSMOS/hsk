"""Order limits and price comparison from the archived bilateral analysis."""

A_MIN = 81_000_000
B_MAX = 49_200_000


def compare(q, a_extra, b_extra):
    seller_benchmark = max(q["seller_first"], q["seller_second"])
    buyer_benchmark = min(q["buyer_first"], q["buyer_second"])
    seller_floor = seller_benchmark + a_extra - q["residual"]
    buyer_ceiling = buyer_benchmark - b_extra
    lower = max(0, A_MIN - q["residual"], seller_floor + 1)
    upper = min(B_MAX, buyer_ceiling - 1)
    case = {"a_incremental_cost": a_extra, "b_incremental_cost": b_extra, "lower": lower, "upper": upper}
    if lower > upper:
        if seller_floor + 1 > buyer_ceiling - 1:
            reason = "net_improvement_unavailable"
        elif A_MIN - q["residual"] > buyer_ceiling - 1:
            reason = "seller_signed_minimum"
        else:
            reason = "buyer_signed_maximum"
        return case | {"eligible": False, "reason": reason, "equal_to_token_unit": False}

    equal_target = (seller_floor + buyer_ceiling) // 2
    payment = min(upper, max(lower, equal_target))
    gain_a = payment - seller_floor
    gain_b = buyer_ceiling - payment
    assert payment + q["residual"] >= A_MIN and payment <= B_MAX
    assert gain_a > 0 and gain_b > 0
    assert gain_a + gain_b == buyer_ceiling - seller_floor
    return case | {
        "eligible": True,
        "payment": payment,
        "a_net_gain": gain_a,
        "b_net_gain": gain_b,
        "equal_to_token_unit": abs(gain_a - gain_b) <= 1,
    }
