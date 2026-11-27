// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {FullMath} from "./FullMath.sol";
import {Market, DexAdapter} from "./Market.sol";
import {Order, SignedOrder, OrderValidation} from "./OrderValidation.sol";

/// Single WHSK/USDT pool. The first order can cross multiple opposite orders
/// and send its remaining fixed WHSK amount to the DEX in the same transaction.
contract Settlement is OrderValidation, DexAdapter {
    struct Leg {
        SignedOrder signedOrder;
        uint256 directWHSK;
        uint256 directUSDT;
        uint256 feeUSDT;
    }

    struct ExecutionPlan {
        bytes32 planId;
        uint256 executionDeadline;
        Leg[] legs;
        uint256 dexWHSK;
        uint256 dexCashLimit;
        bool tryFallback;
    }

    struct Check {
        bytes32 digest;
        uint256 quantity;
        uint256 benchmark;
        uint256 cashLimit;
    }
    enum Result {
        NoTrade,
        Optimized,
        Fallback
    }

    address public immutable admin;
    address public immutable operator;
    address public immutable feeRecipient;
    mapping(bytes32 => bool) public executedPlan;
    bool public paused;
    bool private entered;
    error Forbidden();
    error InvalidPlan();
    error FeeLimit();
    error PriceLimit();
    error Uneconomic();
    event PauseChanged(bool paused);
    event PlanResult(bytes32 indexed planId, Result result);
    event OrderFilled(
        bytes32 indexed planId,
        bytes32 indexed digest,
        address indexed owner,
        address recipient,
        uint256 spent,
        uint256 received,
        uint256 feeUSDT,
        uint256 cumulativeWHSK,
        uint256 benchmarkUSDT
    );
    event DexTrade(bytes32 indexed planId, address indexed pool, uint256 whsk, uint256 usdt);
    event DirectTrade(
        bytes32 indexed planId, bytes32 indexed primary, bytes32 indexed opposite, uint256 whsk, uint256 usdt
    );

    constructor(Market memory market, address admin_, address operator_, address feeRecipient_) DexAdapter(market) {
        if (admin_ == address(0) || operator_ == address(0) || feeRecipient_ == address(this)) revert Forbidden();
        admin = admin_;
        operator = operator_;
        feeRecipient = feeRecipient_;
    }

    function setPaused(bool value) external {
        if (msg.sender != admin) revert Forbidden();
        paused = value;
        emit PauseChanged(value);
    }

    function settle(ExecutionPlan calldata p) external returns (Result result) {
        if (msg.sender != operator || paused || entered) revert Forbidden();
        if (
            p.planId == 0 || executedPlan[p.planId] || p.executionDeadline < block.timestamp || p.legs.length == 0
                || p.legs.length > 8
        ) revert InvalidPlan();
        entered = true;
        result = _settle(p);
        if (result != Result.NoTrade) executedPlan[p.planId] = true;
        emit PlanResult(p.planId, result);
        entered = false;
    }

    function _settle(ExecutionPlan calldata p) private returns (Result) {
        Leg calldata primary = p.legs[0];
        Order calldata o = primary.signedOrder.order;
        bool sell = o.orderKind == 0;
        if ((p.dexWHSK == 0) != (p.dexCashLimit == 0) || (p.dexWHSK > 0 && !o.allowDex)) revert InvalidPlan();
        Check[] memory checks = new Check[](p.legs.length);
        uint256 whskSum;
        uint256 cashSum;
        bool economic = p.legs.length > 1;
        for (uint256 i; i < checks.length; ++i) {
            Leg calldata leg = p.legs[i];
            Order calldata order = leg.signedOrder.order;
            bool legSell = order.orderKind == 0;
            if (order.tokenIn != (legSell ? whsk : usdt) || order.tokenOut != (legSell ? usdt : whsk)) {
                revert InvalidMarket();
            }
            if (i != 0) {
                if (legSell == sell || leg.directWHSK == 0 || leg.directUSDT == 0) revert InvalidPlan();
                for (uint256 j; j < i; ++j) {
                    if (order.owner == p.legs[j].signedOrder.order.owner) revert InvalidPlan();
                }
                whskSum += leg.directWHSK;
                cashSum += leg.directUSDT;
            }
            uint256 qty = leg.directWHSK + (i == 0 ? p.dexWHSK : 0);
            bytes32 digest = _validate(leg.signedOrder, qty);
            if (
                leg.feeUSDT != 0
                    && (feeRecipient == address(0)
                        || leg.feeUSDT > FullMath.mulDiv(order.maxFeeAmount, qty, _total(order)))
            ) revert FeeLimit();
            checks[i] = Check(digest, qty, _quote(order.tokenIn, order.tokenOut, legSell, qty), _cashLimit(order, qty));
            if (i != 0 && !_acceptable(leg, checks[i], leg.directUSDT)) economic = false;
        }
        if (whskSum != primary.directWHSK || cashSum != primary.directUSDT) revert InvalidPlan();
        uint256 dexCash;
        if (p.dexWHSK > 0) {
            dexCash =
                p.dexWHSK == checks[0].quantity ? checks[0].benchmark : _quote(o.tokenIn, o.tokenOut, sell, p.dexWHSK);
            if (sell ? dexCash < p.dexCashLimit : dexCash > p.dexCashLimit) economic = false;
        }
        if (!_acceptable(primary, checks[0], primary.directUSDT + dexCash)) economic = false;
        if (!economic) {
            if (!p.tryFallback || !o.immediate || !o.allowDex || !o.allowDexFallback || o.executionPriority != 1) {
                return Result.NoTrade;
            }
            Check memory c = checks[0];
            if (sell ? c.benchmark < c.cashLimit : c.benchmark > c.cashLimit) return Result.NoTrade;
            _consume(o, c);
            // Fallback charges zero service fee. The user signs permission for this exception to the improvement target.
            uint256 cash = _trade(p.planId, o, c.quantity, c.cashLimit);
            _payout(p.planId, primary, c, cash, 0);
            return Result.Fallback;
        }

        for (uint256 i; i < checks.length; ++i) {
            Leg calldata leg = p.legs[i];
            Order calldata order = leg.signedOrder.order;
            _consume(order, checks[i]);
            _move(
                order.tokenIn,
                order.owner,
                address(this),
                order.orderKind == 0 ? leg.directWHSK : leg.directUSDT + leg.feeUSDT
            );
        }
        if (p.dexWHSK != 0) {
            // Do not pull more than the signed remaining budget, even temporarily.
            uint256 bound = p.dexCashLimit;
            if (!sell) {
                uint256 available = checks[0].cashLimit - primary.directUSDT - primary.feeUSDT;
                if (bound > available) bound = available;
            }
            dexCash = _trade(p.planId, o, p.dexWHSK, bound);
        }
        for (uint256 i; i < checks.length; ++i) {
            Leg calldata leg = p.legs[i];
            uint256 cash = leg.directUSDT + (i == 0 ? dexCash : 0);
            if (!_acceptable(leg, checks[i], cash)) revert Uneconomic();
            _payout(p.planId, leg, checks[i], cash, leg.feeUSDT);
            if (i != 0) emit DirectTrade(p.planId, checks[0].digest, checks[i].digest, leg.directWHSK, leg.directUSDT);
        }
        return Result.Optimized;
    }

    function _consume(Order calldata o, Check memory c) private {
        filledAmount[c.digest] += c.quantity;
        nonceOrder[o.owner][o.nonce] = c.digest;
    }

    function _acceptable(Leg calldata leg, Check memory c, uint256 gross) internal pure virtual returns (bool) {
        Order calldata o = leg.signedOrder.order;
        if (o.orderKind == 0) {
            if (gross < leg.feeUSDT) return false;
            uint256 net = gross - leg.feeUSDT;
            return net >= c.cashLimit && net > c.benchmark && net - c.benchmark >= o.minImprovementAmount;
        }
        uint256 spend = gross + leg.feeUSDT;
        return spend <= c.cashLimit && spend < c.benchmark && c.benchmark - spend >= o.minImprovementAmount;
    }

    function _trade(bytes32 id, Order calldata o, uint256 qty, uint256 limit) private returns (uint256 cash) {
        bool sell = o.orderKind == 0;
        uint256 budget = sell ? qty : limit;
        _move(o.tokenIn, o.owner, address(this), budget);
        (uint256 spent, uint256 received) = _swap(o.tokenIn, o.tokenOut, sell, qty, limit);
        if (spent < budget) _move(o.tokenIn, address(this), o.owner, budget - spent);
        cash = sell ? received : spent;
        emit DexTrade(id, pool, qty, cash);
    }

    function _payout(bytes32 id, Leg calldata leg, Check memory c, uint256 cash, uint256 fee) private {
        Order calldata o = leg.signedOrder.order;
        bool sell = o.orderKind == 0;
        uint256 spent = sell ? c.quantity : cash + fee;
        uint256 received = sell ? cash - fee : c.quantity;
        if (sell ? received < c.cashLimit : spent > c.cashLimit) revert PriceLimit();
        _move(o.tokenOut, address(this), o.recipient, received);
        _move(usdt, address(this), feeRecipient, fee);
        emit OrderFilled(id, c.digest, o.owner, o.recipient, spent, received, fee, filledAmount[c.digest], c.benchmark);
    }
}
