// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {IERC20, IFactory, IQuoter, IRouter} from "../interfaces/IHSKSwap.sol";

struct Market {
    address whsk;
    address usdt;
    address pool;
    IRouter router;
    IQuoter quoter;
}

library HSKMainnet {
    function market() internal pure returns (Market memory) {
        return Market(
            0xB210D2120d57b758EE163cFfb43e73728c471Cf1,
            0xF1B50eD67A9e2CC94Ad3c477779E2d4cBfFf9029,
            0x4ff515761864e7838B0AdB8b5b2B8B7A068905dC,
            IRouter(0x2c16f75b95Cf1390c328aB70e2CEE7f4b80bD8F3),
            IQuoter(0x603f70466fDdbE3F238220B9a74FFF419a2BbFDD)
        );
    }
}

abstract contract DexAdapter {
    address public immutable whsk;
    address public immutable usdt;
    address public immutable pool;
    IRouter public immutable router;
    IQuoter public immutable quoter;
    uint24 public constant POOL_FEE = 3000;
    uint256 public constant QUOTE_GAS = 450000;
    error InvalidMarket();
    error TransferMismatch();
    error QuoteUnavailable();

    constructor(Market memory m) {
        if (block.chainid == 177 && keccak256(abi.encode(m)) != keccak256(abi.encode(HSKMainnet.market()))) {
            revert InvalidMarket();
        }
        if (m.whsk == m.usdt || m.whsk.code.length == 0 || m.usdt.code.length == 0 || m.pool.code.length == 0) {
            revert InvalidMarket();
        }
        address factory = m.router.factory();
        if (factory != m.quoter.factory() || IFactory(factory).getPool(m.whsk, m.usdt, POOL_FEE) != m.pool) {
            revert InvalidMarket();
        }
        whsk = m.whsk;
        usdt = m.usdt;
        pool = m.pool;
        router = m.router;
        quoter = m.quoter;
    }

    function _quote(address input, address output, bool exactIn, uint256 fixedSize)
        internal
        virtual
        returns (uint256 amount)
    {
        IQuoter.Quote memory p = IQuoter.Quote(input, output, fixedSize, POOL_FEE, 0);
        uint160 end;
        if (exactIn) (amount, end,,) = quoter.quoteExactInputSingle{gas: QUOTE_GAS}(p);
        else (amount, end,,) = quoter.quoteExactOutputSingle{gas: QUOTE_GAS}(p);
        // At the limit an exact-input simulation can have unspent input.
        if (amount == 0 || end <= 4295128740 || end >= 1461446703485210103287273052203988822378723970341) {
            revert QuoteUnavailable();
        }
    }

    function _call(address token, bytes memory data) private {
        (bool ok, bytes memory result) = token.call(data);
        if (!ok || (result.length != 0 && !abi.decode(result, (bool)))) revert TransferMismatch();
    }

    function _move(address token, address from, address to, uint256 amount) internal {
        if (amount == 0) return;
        IERC20 t = IERC20(token);
        uint256 src = t.balanceOf(from);
        uint256 dst = t.balanceOf(to);
        if (from == address(this)) _call(token, abi.encodeCall(t.transfer, (to, amount)));
        else _call(token, abi.encodeCall(t.transferFrom, (from, to, amount)));
        if (t.balanceOf(from) + amount != src || t.balanceOf(to) != dst + amount) revert TransferMismatch();
    }

    // Caller funds this contract with exactly the input budget before the swap.
    function _swap(address input, address output, bool exactIn, uint256 size, uint256 limit)
        internal
        returns (uint256 spent, uint256 received)
    {
        uint256 budget = exactIn ? size : limit;
        IERC20 t = IERC20(input);
        uint256 src = t.balanceOf(address(this));
        uint256 dst = IERC20(output).balanceOf(address(this));
        _call(input, abi.encodeCall(t.approve, (address(router), budget)));
        IRouter.Swap memory p = IRouter.Swap(input, output, POOL_FEE, address(this), size, limit, 0);
        if (exactIn) {
            received = router.exactInputSingle(p);
            spent = size;
            if (received < limit) revert TransferMismatch();
        } else {
            spent = router.exactOutputSingle(p);
            received = size;
            if (spent > budget) revert TransferMismatch();
        }
        _call(input, abi.encodeCall(t.approve, (address(router), 0)));
        if (src != t.balanceOf(address(this)) + spent || IERC20(output).balanceOf(address(this)) != dst + received) {
            revert TransferMismatch();
        }
    }
}
