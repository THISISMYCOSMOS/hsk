// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import "./Fixture.sol";
import "./GuardResearch.sol";

interface IPool {
    function slot0() external view returns (uint160, int24, uint16, uint16, uint16, uint8, bool);
    function liquidity() external view returns (uint128);
    function mint(address, int24, int24, uint128, bytes calldata) external returns (uint256, uint256);
}

/// Run only on a pinned, local Foundry fork. Wallet balances below are synthetic.
contract ForkTest is Fixture {
    event Sample(string scenario, uint256 callGas, uint256 calldataBytes);
    event Quotes(string scenario, uint256 beforeCash, uint256 afterCash);

    function setUp() public {
        vm.skip(!vm.envOr("HSK_FORK_TEST", false));
        require(block.chainid == 177 && block.number == 30592078, "pinned fork");
        m = HSKMainnet.market();
        s = new Settlement(m, address(this), address(this), address(0));
        for (uint256 i = A; i <= C; ++i) {
            fund(m.whsk, vm.addr(i), 3000 ether);
            fund(m.usdt, vm.addr(i), 2000e6);
            approveWallet(i);
        }
    }

    // Find the synthetic wallet's balance slot by observing balanceOf. Restore
    // unsuccessful candidates (including proxy slots) before continuing.
    function fund(address token, address owner, uint256 value) private {
        vm.record();
        IERC20(token).balanceOf(owner);
        (bytes32[] memory reads,) = vm.accesses(token);
        for (uint256 i = reads.length; i > 0; --i) {
            bytes32 slot = reads[i - 1];
            bytes32 old = vm.load(token, slot);
            vm.store(token, slot, bytes32(value));
            (bool ok, bytes memory ret) = token.staticcall(abi.encodeCall(IERC20.balanceOf, (owner)));
            if (ok && ret.length == 32 && abi.decode(ret, (uint256)) == value) return;
            vm.store(token, slot, old);
        }
        revert("balance slot");
    }

    function mid(uint256 qty) internal returns (uint256) {
        return (quote(true, qty) + quote(false, qty)) / 2;
    }

    function execute(string memory label, Settlement.ExecutionPlan memory p)
        internal
        returns (Settlement.Result result)
    {
        bytes memory data = abi.encodeCall(s.settle, (p));
        uint256 start = gasleft();
        result = s.settle(p);
        uint256 gasUsed = start - gasleft();
        emit Sample(label, gasUsed, data.length);
        clean();
    }

    function dexTrade(bool sell, uint256 qty, uint256 limit) internal returns (uint256 cash) {
        address owner = vm.addr(C);
        address input = sell ? m.whsk : m.usdt;
        vm.prank(owner);
        IERC20(input).approve(address(m.router), sell ? qty : limit);
        IRouter.Swap memory p = IRouter.Swap(input, sell ? m.usdt : m.whsk, 3000, owner, qty, limit, 0);
        vm.prank(owner);
        uint256 start = gasleft();
        if (sell) cash = m.router.exactInputSingle(p);
        else cash = m.router.exactOutputSingle(p);
        uint256 used = start - gasleft();
        emit Sample(sell ? "dex-sell" : "dex-buy", used, 228);
    }

    function testForkQuotedAndSequential() public {
        require(quote(true, 1 ether) == 80573 && quote(false, 1 ether) == 81061);
        uint256 q = 1000 ether;
        uint256 sell = quote(true, q);
        uint256 buy = quote(false, q);

        uint256 snap = vm.snapshotState();
        require(dexTrade(false, q, buy) == buy);
        require(vm.revertToState(snap));
        require(dexTrade(true, q, sell) == sell);
        uint256 second = quote(false, q);
        require(dexTrade(false, q, second) == second);
        require(second != buy);
        emit Quotes("independent-buy-vs-sequential-buy", buy, second);
    }

    function testForkHybridAndExactOut() public {
        uint256 qty = 600 ether;
        uint256 cash = mid(qty);
        Settlement.ExecutionPlan memory p = plan(true, qty, cash, 400 ether);
        uint256 sell = quote(true, 400 ether);
        require(execute("hybrid-sell", p) == Settlement.Result.Optimized);
        require(IERC20(m.usdt).balanceOf(RECIPIENT) == cash + sell);
    }

    function testForkHybridBuyRefund() public {
        uint256 qty = 600 ether;
        uint256 cash = mid(qty);
        uint256 dex = quote(false, 400 ether);
        Settlement.ExecutionPlan memory p = plan(false, qty, cash, 400 ether);
        uint256 beforeBal = IERC20(m.usdt).balanceOf(vm.addr(A));
        require(execute("hybrid-buy", p) == Settlement.Result.Optimized);
        require(beforeBal - IERC20(m.usdt).balanceOf(vm.addr(A)) == cash + dex);
    }

    function testForkSingleBandResearch() public {
        SingleBandResearch research = new SingleBandResearch(m, address(this));
        for (uint256 i = 1; i <= 1000; i *= 10) {
            uint256 qty = i * 1 ether;
            require(research.intervalQuote(true, qty) == quote(true, qty));
            require(research.intervalQuote(false, qty) == quote(false, qty));
        }
        vm.expectRevert();
        research.intervalQuote(true, 1_000_000 ether);
        s = research;
        approveWallet(A);
        approveWallet(B);
        require(
            execute("single-band-direct", plan(true, 1000 ether, mid(1000 ether), 0)) == Settlement.Result.Optimized
        );
    }

    function testForkStateMatchResearch() public {
        s = new StateMatchResearch(m, address(this), 1000 ether);
        approveWallet(A);
        approveWallet(B);
        Settlement.ExecutionPlan memory p = plan(true, 1000 ether, mid(1000 ether), 0);
        uint256 snap = vm.snapshotState();
        require(execute("interval-state-match-direct", p) == Settlement.Result.Optimized);
        require(vm.revertToState(snap));
        dexTrade(true, 1 ether, 1);
        vm.expectRevert();
        s.settle(p);
    }

    function testForkSignedOnlyResearch() public {
        s = new SignedOnlyResearch(m, address(this));
        approveWallet(A);
        approveWallet(B);
        require(
            execute("signed-limits-only-direct", plan(true, 1000 ether, mid(1000 ether), 0))
                == Settlement.Result.Optimized
        );
    }

    function testForkDirect() public {
        uint256 qty = 1000 ether;
        require(execute("direct", plan(true, qty, mid(qty), 0)) == Settlement.Result.Optimized);
    }

    function testForkMulti() public {
        Settlement.ExecutionPlan memory p = plan(true, 800 ether, 0, 0);
        Settlement.Leg[] memory legs = new Settlement.Leg[](3);
        legs[0] = p.legs[0];
        legs[1] = leg(B, false, 300 ether, mid(300 ether), 300 ether);
        legs[2] = leg(C, false, 500 ether, mid(500 ether), 500 ether);
        legs[0].directUSDT = legs[1].directUSDT + legs[2].directUSDT;
        p.legs = legs;
        require(execute("multi", p) == Settlement.Result.Optimized);
    }

    function testForkRequoteAndConditionalFallback() public {
        uint256 qty = 1 ether;
        uint256 old = quote(true, qty);
        Settlement.ExecutionPlan memory p = plan(true, qty, old + 1, 0);
        p.tryFallback = false;
        uint256 snap = vm.snapshotState();
        require(execute("before-market-update", p) == Settlement.Result.Optimized);
        require(vm.revertToState(snap));
        dexTrade(false, 1000 ether, 200e6);
        uint256 current = quote(true, qty);
        emit Quotes("sell-after-intervening-swap", old, current);
        require(current > old + 1 && execute("no-trade", p) == Settlement.Result.NoTrade);
        require(s.filledAmount(s.orderHash(p.legs[0].signedOrder.order)) == 0);
        p.tryFallback = true;
        require(execute("fallback", p) == Settlement.Result.Fallback);
        require(IERC20(m.usdt).balanceOf(RECIPIENT) == current);
    }

    function testForkLiquidityUpdate() public {
        uint256 qty = 1000 ether;
        uint256 beforeCash = quote(true, qty);
        (uint160 beforePrice, int24 tick,,,,,) = IPool(m.pool).slot0();
        uint128 oldL = IPool(m.pool).liquidity();
        int24 lower = (tick / 60 - 1) * 60;
        fund(m.whsk, address(this), 5000 ether);
        fund(m.usdt, address(this), 1000e6);
        IPool(m.pool).mint(address(this), lower, lower + 120, 1e16, "");
        (uint160 price,,,,,,) = IPool(m.pool).slot0();
        uint256 nowCash = quote(true, qty);
        require(price == beforePrice && IPool(m.pool).liquidity() > oldL && nowCash > beforeCash);
        emit Quotes("sell-after-LP-deposit", beforeCash, nowCash);
        Settlement.ExecutionPlan memory p = plan(true, qty, beforeCash + 1, 0);
        p.tryFallback = false;
        require(execute("requote-after-LP-deposit", p) == Settlement.Result.NoTrade);
    }

    function uniswapV3MintCallback(uint256 amount0, uint256 amount1, bytes calldata) external {
        require(msg.sender == m.pool);
        if (amount0 > 0) IERC20(m.whsk).transfer(m.pool, amount0);
        if (amount1 > 0) IERC20(m.usdt).transfer(m.pool, amount1);
    }

    function testForkRevertBenchmark() public {
        Settlement.ExecutionPlan memory p = plan(true, 600 ether, mid(600 ether), 0);
        vm.prank(vm.addr(B));
        IERC20(m.usdt).approve(address(s), 0);
        bytes memory data = abi.encodeCall(s.settle, (p));
        uint256 start = gasleft();
        (bool ok,) = address(s).call(data);
        uint256 used = start - gasleft();
        require(!ok && s.filledAmount(s.orderHash(p.legs[0].signedOrder.order)) == 0);
        emit Sample("revert-revoked-approval", used, data.length);
        clean();
    }
}
