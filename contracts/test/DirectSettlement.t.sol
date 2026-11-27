// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {DirectSettlement, IDexQuote} from "../src/DirectSettlement.sol";
import {Token} from "./FixtureToken.sol";

interface Vm {
    function addr(uint256 fixtureActor) external returns (address);
    function sign(uint256 fixtureActor, bytes32 digest) external returns (uint8, bytes32, bytes32);
    function prank(address sender) external;
    function warp(uint256 timestamp) external;
    function chainId(uint256 chain) external;
    function expectRevert(bytes4 selector) external;
}

contract FixedQuote is IDexQuote {
    uint16 public rateBps = 9500;

    function setRate(uint16 rate) external {
        rateBps = rate;
    }

    function amountOut(address, uint128 sold) external view returns (uint256) {
        return uint256(sold) * rateBps / 10000;
    }
}

contract DirectSettlementTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    Token private base;
    Token private quote;
    FixedQuote private dex;
    DirectSettlement private settlement;
    DirectSettlement.Order private left;
    DirectSettlement.Order private right;
    DirectSettlement.Signature private leftSig;
    DirectSettlement.Signature private rightSig;

    function setUp() external {
        vm.chainId(31337);
        base = new Token(18);
        quote = new Token(6);
        dex = new FixedQuote();
        settlement = new DirectSettlement(address(base), address(quote), dex);
        // All quantities are base units. The synthetic price deliberately ignores display decimals.
        left = order(vm.addr(101), address(base));
        right = order(vm.addr(102), address(quote));
        leftSig = sign(101, left);
        rightSig = sign(102, right);
        base.mint(left.maker, 1000);
        quote.mint(right.maker, 1000);
        vm.prank(left.maker);
        base.approve(address(settlement), 1000);
        vm.prank(right.maker);
        quote.approve(address(settlement), 1000);
    }

    function order(address who, address token) private view returns (DirectSettlement.Order memory) {
        return
            DirectSettlement.Order(who, token, 1000, 980, 100, 2, uint64(block.timestamp + 1000), bytes32(uint256(1)));
    }

    function sign(uint256 fixtureActor, DirectSettlement.Order memory o)
        private
        returns (DirectSettlement.Signature memory signature)
    {
        (signature.v, signature.r, signature.s) = vm.sign(fixtureActor, settlement.orderDigest(o));
    }

    function trade(uint128 give, uint128 take) private {
        settlement.matchOrders(left, leftSig, give, right, rightSig, take);
    }

    function assertUnfilled() private view {
        require(settlement.filled(settlement.orderDigest(left)) == 0);
        require(settlement.filled(settlement.orderDigest(right)) == 0);
        require(base.balanceOf(right.maker) == 0 && quote.balanceOf(left.maker) == 0);
    }

    function testFullMatch() external {
        trade(1000, 1000);
        require(base.balanceOf(right.maker) == 1000 && quote.balanceOf(left.maker) == 1000);
        require(base.balanceOf(left.maker) == 0 && quote.balanceOf(right.maker) == 0);
        vm.expectRevert(DirectSettlement.InvalidOrder.selector);
        trade(100, 100);
    }

    function testPartialThenComplete() external {
        trade(600, 600);
        trade(400, 400);
        require(settlement.filled(settlement.orderDigest(left)) == 1000);
        require(quote.balanceOf(left.maker) == 1000);
    }

    function testCancellationRetainsPartialFill() external {
        trade(400, 400);
        vm.prank(left.maker);
        settlement.cancel(left);
        vm.expectRevert(DirectSettlement.InactiveOrder.selector);
        trade(600, 600);
        require(settlement.filled(settlement.orderDigest(left)) == 400);
    }

    function testOnlyMakerCanCancel() external {
        vm.expectRevert(DirectSettlement.InvalidOrder.selector);
        settlement.cancel(left);
    }

    function testExpired() external {
        vm.warp(left.deadline + 1);
        vm.expectRevert(DirectSettlement.InactiveOrder.selector);
        trade(100, 100);
    }

    function testSignedLimit() external {
        vm.expectRevert(DirectSettlement.InvalidOrder.selector);
        trade(1000, 970);
        assertUnfilled();
    }

    function testSignedMinimumFill() external {
        vm.expectRevert(DirectSettlement.InvalidOrder.selector);
        trade(99, 99);
    }

    function testChangedQuoteAtExecution() external {
        dex.setRate(9980); // 1000 - 998 equals costBufferPerFill. Zero net gain must fail.
        vm.expectRevert(DirectSettlement.Uneconomic.selector);
        trade(1000, 1000);
        assertUnfilled();
    }

    function testMissingQuote() external {
        dex.setRate(0);
        vm.expectRevert(DirectSettlement.Uneconomic.selector);
        trade(1000, 1000);
    }

    function testRevokedAllowanceRollsBackBothTransfers() external {
        vm.prank(right.maker);
        quote.approve(address(settlement), 0);
        vm.expectRevert(DirectSettlement.TransferMismatch.selector);
        trade(100, 100);
        assertUnfilled();
        require(base.allowance(left.maker, address(settlement)) == 1000);
    }

    function testBalanceChangedRollsBack() external {
        vm.prank(right.maker);
        quote.approve(address(this), 950);
        quote.transferFrom(right.maker, address(this), 950);
        vm.expectRevert(DirectSettlement.TransferMismatch.selector);
        trade(100, 100);
        assertUnfilled();
    }

    function testRejectChangedOrder() external {
        left.minBuyAmount = 900;
        vm.expectRevert(DirectSettlement.InvalidSignature.selector);
        trade(100, 100);
    }

    function testRejectForeignDomain() external {
        vm.chainId(31338);
        vm.expectRevert(DirectSettlement.InvalidSignature.selector);
        trade(100, 100);
    }

    function testRejectForeignVerifyingContract() external {
        DirectSettlement other = new DirectSettlement(address(base), address(quote), dex);
        vm.expectRevert(DirectSettlement.InvalidSignature.selector);
        other.matchOrders(left, leftSig, 100, right, rightSig, 100);
    }
}
