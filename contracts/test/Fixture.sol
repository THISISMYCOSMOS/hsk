// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Settlement} from "../src/Settlement.sol";
import {Market, HSKMainnet} from "../src/Market.sol";
import {Order, SignedOrder} from "../src/OrderValidation.sol";
import {IERC20, IRouter, IQuoter} from "../interfaces/IHSKSwap.sol";

interface Vm {
    function addr(uint256) external pure returns (address);
    function sign(uint256, bytes32) external pure returns (uint8, bytes32, bytes32);
    function prank(address) external;
    function warp(uint256) external;
    function chainId(uint256) external;
    function expectRevert(bytes4) external;
    function expectRevert() external;
    function record() external;
    function accesses(address) external returns (bytes32[] memory, bytes32[] memory);
    function load(address, bytes32) external view returns (bytes32);
    function store(address, bytes32, bytes32) external;
    function etch(address, bytes calldata) external;
    function snapshotState() external returns (uint256);
    function revertToState(uint256) external returns (bool);
    function skip(bool) external;
    function envOr(string calldata, bool) external view returns (bool);
    function targetContract(address) external;
    function cool(address) external;
}

abstract contract Fixture {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant A = 101;
    uint256 constant B = 102;
    uint256 constant C = 103;
    address constant RECIPIENT = address(0xBEEF);
    address constant TREASURY = address(0xFEE);
    Settlement s;
    Market m;

    function signOrder(Order memory o, uint256 key) internal view returns (SignedOrder memory) {
        (uint8 v, bytes32 r, bytes32 ss) = vm.sign(key, s.orderHash(o));
        return SignedOrder(o, abi.encodePacked(r, ss, v));
    }

    function leg(uint256 key, bool sell, uint256 qty, uint256 cash, uint256 total)
        internal
        view
        returns (Settlement.Leg memory)
    {
        Order memory o;
        o.owner = vm.addr(key);
        o.recipient = key == A ? RECIPIENT : o.owner;
        o.orderKind = sell ? 0 : 1;
        o.tokenIn = sell ? m.whsk : m.usdt;
        o.tokenOut = sell ? m.usdt : m.whsk;
        o.amountIn = sell ? total : total / 1e12;
        o.amountOut = sell ? total / 1e15 : total;
        o.deadline = block.timestamp + 1000;
        o.partiallyFillable = true;
        o.allowDex = true;
        o.allowDexFallback = true;
        o.immediate = true;
        o.executionPriority = 1;
        o.nonce = 1;
        o.allowedExecutor = address(this);
        o.maxFeeAmount = total / 1e15;
        return Settlement.Leg(signOrder(o, key), qty, cash, 0);
    }

    function plan(bool sell, uint256 direct, uint256 cash, uint256 dex)
        internal
        view
        returns (Settlement.ExecutionPlan memory p)
    {
        p.planId = bytes32(uint256(42));
        p.executionDeadline = block.timestamp + 100;
        p.legs = new Settlement.Leg[](direct == 0 ? 1 : 2);
        uint256 total = 1000 ether;
        p.legs[0] = leg(A, sell, direct, cash, total);
        if (direct != 0) p.legs[1] = leg(B, !sell, direct, cash, total);
        p.dexWHSK = dex;
        p.dexCashLimit = dex == 0 ? 0 : sell ? 1 : dex / 1e12;
        p.tryFallback = true;
    }

    function resign(Settlement.ExecutionPlan memory p, uint256 i, uint256 key) internal view {
        p.legs[i].signedOrder = signOrder(p.legs[i].signedOrder.order, key);
    }

    function approveWallet(uint256 key) internal {
        address owner = vm.addr(key);
        vm.prank(owner);
        IERC20(m.whsk).approve(address(s), 2000 ether);
        vm.prank(owner);
        IERC20(m.usdt).approve(address(s), 2000e6);
    }

    function quote(bool sell, uint256 qty) internal returns (uint256 cash) {
        IQuoter.Quote memory q = IQuoter.Quote(sell ? m.whsk : m.usdt, sell ? m.usdt : m.whsk, qty, 3000, 0);
        if (sell) (cash,,,) = m.quoter.quoteExactInputSingle(q);
        else (cash,,,) = m.quoter.quoteExactOutputSingle(q);
    }

    function clean() internal view {
        require(IERC20(m.whsk).balanceOf(address(s)) == 0 && IERC20(m.usdt).balanceOf(address(s)) == 0, "residue");
    }
}
