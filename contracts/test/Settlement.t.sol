// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import "./Fixture.sol";
import {OrderValidation} from "../src/OrderValidation.sol";
import {DexAdapter} from "../src/Market.sol";

contract Token is IERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 n) external {
        balanceOf[to] += n;
    }

    function approve(address to, uint256 n) external returns (bool) {
        allowance[msg.sender][to] = n;
        return true;
    }

    function transfer(address to, uint256 n) external returns (bool) {
        balanceOf[msg.sender] -= n;
        balanceOf[to] += n;
        return true;
    }

    function transferFrom(address from, address to, uint256 n) external returns (bool) {
        allowance[from][msg.sender] -= n;
        balanceOf[from] -= n;
        balanceOf[to] += n;
        return true;
    }
}

contract MockDex is IRouter, IQuoter {
    address public immutable factory = address(this);
    bool public failSwap;
    bool public failQuote;

    function getPool(address, address, uint24) external view returns (address) {
        return address(this);
    }

    function fail(bool swap, bool q) external {
        failSwap = swap;
        failQuote = q;
    }

    function quoteExactInputSingle(Quote calldata p) external view returns (uint256, uint160, uint32, uint256) {
        require(!failQuote);
        return (p.amount * 99 / 1e15, 2 ** 96, 0, 0);
    }

    function quoteExactOutputSingle(Quote calldata p) external view returns (uint256, uint160, uint32, uint256) {
        require(!failQuote);
        return (p.amount * 101 / 1e15, 2 ** 96, 0, 0);
    }

    function exactInputSingle(Swap calldata p) external payable returns (uint256 cash) {
        require(!failSwap);
        cash = p.amount * 99 / 1e15;
        require(cash >= p.limit);
        IERC20(p.tokenIn).transferFrom(msg.sender, address(this), p.amount);
        IERC20(p.tokenOut).transfer(p.recipient, cash);
    }

    function exactOutputSingle(Swap calldata p) external payable returns (uint256 cash) {
        require(!failSwap);
        cash = p.amount * 101 / 1e15;
        require(cash <= p.limit);
        IERC20(p.tokenIn).transferFrom(msg.sender, address(this), cash);
        IERC20(p.tokenOut).transfer(p.recipient, p.amount);
    }
}

contract SettlementTest is Fixture {
    MockDex dex;

    function setUp() public virtual {
        dex = new MockDex();
        m = Market(address(new Token()), address(new Token()), address(dex), dex, dex);
        s = new Settlement(m, address(this), address(this), TREASURY);
        for (uint256 i = A; i <= C; ++i) {
            Token(m.whsk).mint(vm.addr(i), 2000 ether);
            Token(m.usdt).mint(vm.addr(i), 2000e6);
            approveWallet(i);
        }
        Token(m.whsk).mint(address(dex), 2000 ether);
        Token(m.usdt).mint(address(dex), 2000e6);
    }

    function standard() internal view returns (Settlement.ExecutionPlan memory) {
        return plan(true, 600 ether, 60e6, 0);
    }

    function testFullDirectFeesRecipient() public {
        Settlement.ExecutionPlan memory p = plan(true, 1000 ether, 100e6, 0);
        p.legs[0].feeUSDT = 100;
        p.legs[1].feeUSDT = 200;
        require(s.settle(p) == Settlement.Result.Optimized);
        require(IERC20(m.usdt).balanceOf(RECIPIENT) == 100e6 - 100);
        require(IERC20(m.usdt).balanceOf(TREASURY) == 300);
        require(IERC20(m.usdt).balanceOf(vm.addr(B)) == 2000e6 - 100e6 - 200);
        clean();
    }

    function testPartialMultiAndReplay() public {
        Settlement.ExecutionPlan memory p = plan(true, 800 ether, 80e6, 0);
        Settlement.Leg[] memory legs = new Settlement.Leg[](3);
        legs[0] = p.legs[0];
        legs[1] = leg(B, false, 300 ether, 30e6, 300 ether);
        legs[2] = leg(C, false, 500 ether, 50e6, 500 ether);
        p.legs = legs;
        require(s.settle(p) == Settlement.Result.Optimized);
        require(s.filledAmount(s.orderHash(legs[0].signedOrder.order)) == 800 ether);
        clean();
        vm.expectRevert(Settlement.InvalidPlan.selector);
        s.settle(p);
        p.planId = bytes32(uint256(2));
        vm.expectRevert(OrderValidation.FillLimit.selector);
        s.settle(p);
    }

    function testHybridSell() public {
        Settlement.ExecutionPlan memory p = plan(true, 600 ether, 60e6, 400 ether);
        require(s.settle(p) == Settlement.Result.Optimized);
        require(IERC20(m.usdt).balanceOf(RECIPIENT) == 99600000);
        clean();
    }

    function testHybridBuyRefund() public {
        Settlement.ExecutionPlan memory p = plan(false, 600 ether, 60e6, 400 ether);
        require(s.settle(p) == Settlement.Result.Optimized);
        require(IERC20(m.usdt).balanceOf(vm.addr(A)) == 2000e6 - 100400000);
        require(Token(m.usdt).allowance(address(s), address(dex)) == 0);
        clean();
    }

    function testNoTradeAndFallbackPolicy() public {
        Settlement.ExecutionPlan memory p = plan(true, 600 ether, 80e6, 0);
        bytes32 peer = s.orderHash(p.legs[1].signedOrder.order);
        p.tryFallback = false;
        require(s.settle(p) == Settlement.Result.NoTrade && !s.executedPlan(p.planId));
        p.tryFallback = true;
        p.legs[0].signedOrder.order.immediate = false;
        resign(p, 0, A);
        require(s.settle(p) == Settlement.Result.NoTrade);
        p.legs[0].signedOrder.order.immediate = true;
        p.legs[0].signedOrder.order.allowDexFallback = false;
        resign(p, 0, A);
        require(s.settle(p) == Settlement.Result.NoTrade);
        p.legs[0].signedOrder.order.allowDexFallback = true;
        resign(p, 0, A);
        require(s.settle(p) == Settlement.Result.Fallback);
        require(s.filledAmount(peer) == 0 && IERC20(m.usdt).balanceOf(RECIPIENT) == 59400000);
        clean();
    }

    function testAtomicRouterFailure() public {
        Settlement.ExecutionPlan memory p = plan(true, 600 ether, 60e6, 400 ether);
        dex.fail(true, false);
        vm.expectRevert();
        s.settle(p);
        require(s.filledAmount(s.orderHash(p.legs[0].signedOrder.order)) == 0 && !s.executedPlan(p.planId));
        require(IERC20(m.whsk).balanceOf(vm.addr(A)) == 2000 ether && IERC20(m.usdt).balanceOf(vm.addr(B)) == 2000e6);
        clean();
    }

    function testQuoteFailure() public {
        Settlement.ExecutionPlan memory p = standard();
        dex.fail(false, true);
        vm.expectRevert();
        s.settle(p);
    }

    function testPartialDisabledAndFeeCap() public {
        Settlement.ExecutionPlan memory p = standard();
        p.legs[0].signedOrder.order.partiallyFillable = false;
        resign(p, 0, A);
        vm.expectRevert(OrderValidation.FillLimit.selector);
        s.settle(p);
        p = standard();
        p.legs[0].feeUSDT = 600001;
        vm.expectRevert(Settlement.FeeLimit.selector);
        s.settle(p);
    }

    function testSignatureDomains() public {
        Settlement.ExecutionPlan memory p = standard();
        vm.chainId(123);
        vm.expectRevert(OrderValidation.InvalidSignature.selector);
        s.settle(p);
        vm.chainId(31337);
        Settlement other = new Settlement(m, address(this), address(this), TREASURY);
        vm.expectRevert(OrderValidation.InvalidSignature.selector);
        other.settle(p);
        p.legs[0].signedOrder.order.recipient = vm.addr(B);
        vm.expectRevert(OrderValidation.InvalidSignature.selector);
        s.settle(p);
    }

    function testExpiryAndCancellation() public {
        Settlement.ExecutionPlan memory p = standard();
        p.executionDeadline += 2000;
        vm.prank(vm.addr(A));
        s.cancelOrder(p.legs[0].signedOrder.order);
        vm.expectRevert(OrderValidation.InactiveOrder.selector);
        s.settle(p);
        p.legs[0].signedOrder.order.nonce = 2;
        resign(p, 0, A);
        vm.prank(vm.addr(A));
        s.invalidateNonce(2);
        vm.expectRevert(OrderValidation.InactiveOrder.selector);
        s.settle(p);
        p.legs[0].signedOrder.order.nonce = 3;
        resign(p, 0, A);
        vm.warp(block.timestamp + 1001);
        vm.expectRevert(OrderValidation.InactiveOrder.selector);
        s.settle(p);
    }

    function testInvalidMarketRecipientOperatorAndPause() public {
        Settlement.ExecutionPlan memory p = standard();
        vm.prank(vm.addr(B));
        vm.expectRevert(Settlement.Forbidden.selector);
        s.settle(p);
        s.setPaused(true);
        vm.expectRevert(Settlement.Forbidden.selector);
        s.settle(p);
        s.setPaused(false);
        p.legs[0].signedOrder.order.recipient = address(0);
        resign(p, 0, A);
        vm.expectRevert(OrderValidation.InvalidOrder.selector);
        s.settle(p);
        p.legs[0].signedOrder.order.tokenIn = address(this);
        vm.expectRevert(DexAdapter.InvalidMarket.selector);
        s.settle(p);
        m.router = IRouter(address(new MockDex()));
        vm.expectRevert(DexAdapter.InvalidMarket.selector);
        new Settlement(m, address(this), address(this), TREASURY);
    }

    function testUnfundedOrRevokedRestores() public {
        Settlement.ExecutionPlan memory p = standard();
        vm.prank(vm.addr(B));
        IERC20(m.usdt).approve(address(s), 0);
        vm.expectRevert(DexAdapter.TransferMismatch.selector);
        s.settle(p);
        approveWallet(B);
        vm.prank(vm.addr(B));
        IERC20(m.usdt).transfer(RECIPIENT, 2000e6);
        vm.expectRevert(DexAdapter.TransferMismatch.selector);
        s.settle(p);
        require(IERC20(m.whsk).balanceOf(vm.addr(A)) == 2000 ether);
        clean();
    }

    function testHardPriceLimit() public {
        Settlement.ExecutionPlan memory p = standard();
        p.legs[0].signedOrder.order.amountOut = 101e6;
        resign(p, 0, A);
        require(
            s.settle(p) == Settlement.Result.NoTrade && s.filledAmount(s.orderHash(p.legs[0].signedOrder.order)) == 0
        );
    }

    function testBoundNonceAndFutureOrder() public {
        Settlement.ExecutionPlan memory p = standard();
        require(s.settle(p) == Settlement.Result.Optimized);
        p.planId = bytes32(uint256(43));
        p.legs[0].signedOrder.order.recipient = vm.addr(C);
        resign(p, 0, A);
        vm.expectRevert(OrderValidation.InactiveOrder.selector);
        s.settle(p);
        p.legs[0].signedOrder.order.nonce = 7;
        p.legs[0].signedOrder.order.validAfter = block.timestamp + 10;
        resign(p, 0, A);
        vm.expectRevert(OrderValidation.InactiveOrder.selector);
        s.settle(p);
    }

    function testSignedExecutorAndResidualPermission() public {
        Settlement.ExecutionPlan memory p = plan(true, 600 ether, 60e6, 400 ether);
        p.legs[0].signedOrder.order.allowedExecutor = vm.addr(C);
        resign(p, 0, A);
        vm.expectRevert(OrderValidation.InvalidOrder.selector);
        s.settle(p);
        p.legs[0].signedOrder.order.allowDex = false;
        resign(p, 0, A);
        vm.expectRevert(Settlement.InvalidPlan.selector);
        s.settle(p);
    }

    function testRetainsPreExistingBalancesAndHonorsImprovementFloor() public {
        Settlement.ExecutionPlan memory p = standard();
        Token(m.usdt).mint(address(s), 37);
        p.legs[0].signedOrder.order.minImprovementAmount = 600001;
        resign(p, 0, A);
        p.tryFallback = false;
        require(s.settle(p) == Settlement.Result.NoTrade);
        p.legs[0].signedOrder.order.minImprovementAmount = 600000;
        resign(p, 0, A);
        require(s.settle(p) == Settlement.Result.Optimized);
        require(IERC20(m.usdt).balanceOf(address(s)) == 37);
    }

    function testFuzzPartialBounds(uint96 raw) public {
        uint256 q = (1 + uint256(raw) % 1000) * 1 ether;
        Settlement.ExecutionPlan memory p = plan(true, q, q / 1e13, 0);
        require(s.settle(p) == Settlement.Result.Optimized);
        uint256 filled = s.filledAmount(s.orderHash(p.legs[0].signedOrder.order));
        require(filled == q && filled <= 1000 ether);
        require(IERC20(m.usdt).balanceOf(RECIPIENT) >= q / 1e15);
        clean();
    }
}
