// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import {TickMath} from "./TickMath.sol";
import {Market, DexAdapter} from "../src/Market.sol";
import {Settlement} from "../src/Settlement.sol";

interface IRangePool {
    function slot0() external view returns (uint160, int24, uint16, uint16, uint16, uint8, bool);
    function liquidity() external view returns (uint128);
    function tickSpacing() external view returns (int24);
    function token0() external view returns (address);
}

/// Experimental comparison only. One interval, token0 fixed, checked products.
contract SingleBandResearch is Settlement {
    uint256 constant Q96 = 2 ** 96;
    IRangePool immutable rangePool;
    int24 immutable spacing;
    error OutsideInterval();

    constructor(Market memory m, address operator) Settlement(m, operator, operator, address(0)) {
        rangePool = IRangePool(m.pool);
        spacing = rangePool.tickSpacing();
        require(spacing > 0 && rangePool.token0() == m.whsk);
    }

    function ceilDiv(uint256 n, uint256 d) internal pure returns (uint256) {
        return n / d + (n % d == 0 ? 0 : 1);
    }

    function intervalQuote(bool sell, uint256 qty) public view returns (uint256 cash) {
        (uint160 price, int24 tick,,,,,) = rangePool.slot0();
        uint256 liquidity = rangePool.liquidity();
        int24 band = tick / spacing;
        if (tick < 0 && tick % spacing != 0) --band;
        uint160 lower = TickMath.getSqrtRatioAtTick(band * spacing);
        uint160 upper = TickMath.getSqrtRatioAtTick((band + 1) * spacing);
        if (price <= lower || price >= upper || liquidity == 0) revert OutsideInterval();
        uint256 numerator = liquidity * Q96;
        uint256 net = sell ? qty * 997000 / 1000000 : qty;
        uint256 step = net * price;
        if (!sell && step >= numerator) revert OutsideInterval();
        uint256 end = ceilDiv(numerator * price, sell ? numerator + step : numerator - step);
        if (end <= lower || end >= upper) revert OutsideInterval();
        cash =
            sell ? liquidity * (price - end) / Q96 : ceilDiv(ceilDiv(liquidity * (end - price), Q96) * 1000000, 997000);
        if (cash == 0) revert OutsideInterval();
    }

    function _quote(address, address, bool sell, uint256 qty) internal view virtual override returns (uint256) {
        return intervalQuote(sell, qty);
    }
}

/// Method A comparator. Only two on-chain, interval-certified, fixed-size cached quotes.
contract StateMatchResearch is SingleBandResearch {
    bytes32 immutable fingerprint;
    uint256 immutable size;
    uint256 immutable sellCash;
    uint256 immutable buyCash;

    constructor(Market memory m, address op, uint256 qty) SingleBandResearch(m, op) {
        size = qty;
        sellCash = intervalQuote(true, qty);
        buyCash = intervalQuote(false, qty);
        fingerprint = state();
    }

    function state() internal view returns (bytes32) {
        (uint160 price, int24 tick,,,,,) = rangePool.slot0();
        return keccak256(abi.encode(price, tick, rangePool.liquidity()));
    }

    function _quote(address, address, bool sell, uint256 qty) internal view override returns (uint256) {
        require(qty == size && state() == fingerprint);
        return sell ? sellCash : buyCash;
    }
}

/// Signed hard limits only. Test tree only, never export/deploy this comparator.
contract SignedOnlyResearch is Settlement {
    constructor(Market memory m, address op) Settlement(m, op, op, address(0)) {}

    function _quote(address, address, bool, uint256) internal pure override returns (uint256) {
        return 0;
    }

    function _acceptable(Leg calldata leg, Check memory c, uint256 gross) internal pure override returns (bool) {
        if (leg.signedOrder.order.orderKind == 0) return gross >= leg.feeUSDT && gross - leg.feeUSDT >= c.cashLimit;
        return gross + leg.feeUSDT <= c.cashLimit;
    }
}
