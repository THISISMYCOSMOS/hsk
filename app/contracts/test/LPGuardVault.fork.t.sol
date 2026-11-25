// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {LPGuardVault} from "../src/LPGuardVault.sol";
import {INonfungiblePositionManager} from "../src/interfaces/INonfungiblePositionManager.sol";
import {IUniswapV3Factory} from "../src/interfaces/IUniswapV3Factory.sol";
import {IUniswapV3Pool} from "../src/interfaces/IUniswapV3Pool.sol";
import {ISwapRouter02} from "../src/interfaces/ISwapRouter02.sol";
import {IQuoterV2} from "../src/interfaces/IQuoterV2.sol";
import {IERC20Minimal} from "../src/interfaces/IERC20Minimal.sol";
import {HskAddresses as A} from "./HskAddresses.sol";

/// @notice 메인넷 포크 시험 F1~F3 (구현-계획.md 4절) + deposit·withdraw·정책 검사 거부 경로.
/// 실행: forge test --match-path test/LPGuardVault.fork.t.sol -vv
/// 기본으로 https://mainnet.hsk.xyz 의 FORK_BLOCK에서 포크한다. 바꾸려면 HSK_RPC, FORK_BLOCK 환경변수.
contract LPGuardVaultForkTest is Test {
    uint256 internal constant DEFAULT_FORK_BLOCK = 30_620_000; // 2026-11-25 고정

    INonfungiblePositionManager internal npm = INonfungiblePositionManager(A.NPM);
    IUniswapV3Factory internal factory = IUniswapV3Factory(A.FACTORY);
    LPGuardVault internal vault;

    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    function setUp() public {
        string memory rpc = vm.envOr("HSK_RPC", string("https://mainnet.hsk.xyz"));
        uint256 blk = vm.envOr("FORK_BLOCK", DEFAULT_FORK_BLOCK);
        vm.createSelectFork(rpc, blk);
        assertEq(block.chainid, 177, "chain id");

        vault = new LPGuardVault(
            npm,
            ISwapRouter02(A.ROUTER),
            factory,
            A.USDT,
            A.SUPRA_PULL,
            [A.POOL_WETH_USDT, A.POOL_WHSK_USDT],
            [A.PAIR_ETH_USDT, A.PAIR_HSK_USDT]
        );
    }

    // ------------------------------------------------------------------
    // F1 주소 대조와 읽기
    // ------------------------------------------------------------------

    function test_F1_addresses() public view {
        assertEq(npm.factory(), A.FACTORY, "npm.factory");
        assertEq(ISwapRouter02(A.ROUTER).factory(), A.FACTORY, "router.factory");
        assertEq(IQuoterV2(A.QUOTER).factory(), A.FACTORY, "quoter.factory");
        assertEq(npm.WETH9(), A.WHSK, "npm.WETH9");
        assertEq(ISwapRouter02(A.ROUTER).WETH9(), A.WHSK, "router.WETH9");

        _checkPool(A.POOL_WETH_USDT, A.WETH);
        _checkPool(A.POOL_WHSK_USDT, A.WHSK);

        assertGt(A.SUPRA_PULL.code.length, 0, "supra code");
        assertEq(IERC20Minimal(A.USDT).decimals(), 6, "usdt decimals");
    }

    function _checkPool(address pool, address token0) internal view {
        IUniswapV3Pool p = IUniswapV3Pool(pool);
        assertEq(p.factory(), A.FACTORY, "pool.factory");
        assertEq(p.token0(), token0, "pool.token0");
        assertEq(p.token1(), A.USDT, "pool.token1");
        assertEq(p.fee(), A.FEE, "pool.fee");
        assertEq(p.tickSpacing(), 60, "pool.tickSpacing");
        assertEq(factory.getPool(token0, A.USDT, A.FEE), pool, "factory.getPool");
        (uint160 sqrtP,,,,,, bool unlocked) = p.slot0();
        assertGt(sqrtP, 0, "slot0.sqrtPriceX96");
        assertTrue(unlocked, "slot0.unlocked");
    }

    function test_F1_readExistingPositions() public view {
        uint256 total = _totalSupply();
        assertGt(total, 0, "npm has NFTs");
        // 첫 NFT를 읽어 형식이 맞는지 본다(소각된 번호는 건너뜀).
        uint256 found;
        for (uint256 id = 1; id <= 40 && found == 0; ++id) {
            try npm.ownerOf(id) returns (address o) {
                (,, address t0, address t1, uint24 fee, int24 lo, int24 hi,,,,,) = npm.positions(id);
                assertTrue(o != address(0));
                assertTrue(t0 < t1, "token order");
                assertTrue(lo < hi, "tick order");
                assertGt(fee, 0);
                found = id;
            } catch {}
        }
        assertGt(found, 0, "no readable position");
    }

    function _totalSupply() internal view returns (uint256 s) {
        (bool ok, bytes memory ret) = A.NPM.staticcall(abi.encodeWithSignature("totalSupply()"));
        require(ok, "totalSupply");
        s = abi.decode(ret, (uint256));
    }

    // ------------------------------------------------------------------
    // F2 NFT 준비: 공식 토큰을 deal로 받고 NPM mint
    // ------------------------------------------------------------------

    function test_F2_mintWhsk() public {
        (uint256 id, uint128 liq) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        assertGt(liq, 0, "liquidity");
        assertEq(npm.ownerOf(id), alice);
        emit log_named_uint("WHSK/USDT tokenId", id);
        emit log_named_uint("WHSK/USDT liquidity", liq);
    }

    function test_F2_mintWeth() public {
        (uint256 id, uint128 liq) = _mintAround(alice, A.POOL_WETH_USDT, A.WETH, 0.1e18, 200e6);
        assertGt(liq, 0, "liquidity");
        assertEq(npm.ownerOf(id), alice);
        emit log_named_uint("WETH/USDT tokenId", id);
        emit log_named_uint("WETH/USDT liquidity", liq);
    }

    // ------------------------------------------------------------------
    // F3 예치 → getPosition → 인출
    // ------------------------------------------------------------------

    function test_F3_depositWithdraw() public {
        (uint256 id, uint128 liq) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);

        vm.startPrank(alice);
        npm.approve(address(vault), id);
        vault.deposit(id, p);
        vm.stopPrank();

        assertEq(npm.ownerOf(id), address(vault), "vault holds NFT");
        LPGuardVault.Position memory pos = vault.getPosition(id);
        assertEq(pos.owner, alice);
        assertEq(pos.pool, A.POOL_WHSK_USDT);
        assertEq(pos.token0, A.WHSK);
        assertEq(pos.L0, liq);
        assertEq(pos.removed, 0);
        assertEq(pos.stepDone, 0);
        assertEq(pos.pendingSell, 0);
        assertEq(pos.policy.cumBps[3], 10_000);
        assertEq(pos.policy.keeper, p.keeper);
        assertEq(vault.pairIndexOf(pos.pool), A.PAIR_HSK_USDT);

        vm.prank(alice);
        vault.withdraw(id);

        assertEq(npm.ownerOf(id), alice, "NFT back to owner");
        (,,,,,,, uint128 liqAfter,,,,) = npm.positions(id);
        assertEq(liqAfter, liq, "liquidity untouched");
        assertEq(vault.getPosition(id).owner, address(0), "record deleted");
    }

    function test_F3_depositWithdraw_weth_setApprovalForAll() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WETH_USDT, A.WETH, 0.1e18, 200e6);
        vm.startPrank(alice);
        npm.setApprovalForAll(address(vault), true);
        vault.deposit(id, _defaultPolicy(A.POOL_WETH_USDT));
        assertEq(vault.getPosition(id).pool, A.POOL_WETH_USDT);
        vault.withdraw(id);
        vm.stopPrank();
        assertEq(npm.ownerOf(id), alice);
    }

    // ------------------------------------------------------------------
    // 거부 경로
    // ------------------------------------------------------------------

    function test_deposit_revert_notOwner() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        vm.prank(alice);
        npm.approve(address(vault), id);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.prank(bob);
        vm.expectRevert(LPGuardVault.NotOwner.selector);
        vault.deposit(id, p);
    }

    function test_deposit_revert_notApproved() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.prank(alice);
        vm.expectRevert(bytes("ERC721: transfer caller is not owner nor approved"));
        vault.deposit(id, p);
        assertEq(npm.ownerOf(id), alice);
    }

    function test_deposit_revert_unsupportedPool_otherFeeTier() public {
        // WHSK/USDT 1% 풀(포크 블록에는 없음)을 만들어 같은 토큰쌍의 다른 풀을 거부하는지 본다.
        IUniswapV3Pool ref = IUniswapV3Pool(A.POOL_WHSK_USDT);
        (uint160 sqrtP,,,,,,) = ref.slot0();
        npm.createAndInitializePoolIfNecessary(A.WHSK, A.USDT, 10_000, sqrtP);
        address pool = factory.getPool(A.WHSK, A.USDT, 10_000);
        (uint256 id,) = _mintAroundFee(alice, pool, A.WHSK, 10_000, 2_000e18, 200e6);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.startPrank(alice);
        npm.approve(address(vault), id);
        vm.expectRevert(LPGuardVault.UnsupportedPool.selector);
        vault.deposit(id, p);
        vm.stopPrank();
    }

    function test_deposit_revert_unsupportedPool_notUsdt() public {
        // WHSK/WETH 0.30% 풀(포크 블록에는 없음): token1이 USDT가 아니다.
        (uint160 sqrtP,,,,,,) = IUniswapV3Pool(A.POOL_WHSK_USDT).slot0();
        npm.createAndInitializePoolIfNecessary(A.WHSK, A.WETH, A.FEE, sqrtP);
        address pool = factory.getPool(A.WHSK, A.WETH, A.FEE);
        (uint256 id,) = _mintAroundFee(alice, pool, A.WHSK, A.FEE, 1_000e18, 1e18);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.startPrank(alice);
        npm.approve(address(vault), id);
        vm.expectRevert(LPGuardVault.UnsupportedPool.selector);
        vault.deposit(id, p);
        vm.stopPrank();
    }

    function test_deposit_revert_emptyPosition() public {
        (uint256 id, uint128 liq) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        vm.startPrank(alice);
        npm.decreaseLiquidity(INonfungiblePositionManager.DecreaseLiquidityParams(id, liq, 0, 0, block.timestamp));
        npm.approve(address(vault), id);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.expectRevert(LPGuardVault.EmptyPosition.selector);
        vault.deposit(id, p);
        vm.stopPrank();
    }

    function test_deposit_revert_invalidPolicy_allCodes() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        vm.prank(alice);
        npm.approve(address(vault), id);
        LPGuardVault.Policy memory base = _defaultPolicy(A.POOL_WHSK_USDT);
        LPGuardVault.Policy memory p;

        // 1: 회수선
        p = _copy(base);
        p.refSqrtPriceX96 = p.lineSqrtPriceX96[0];
        _expectPolicy(id, p, 1);
        p = _copy(base);
        p.lineSqrtPriceX96[2] = p.lineSqrtPriceX96[1];
        _expectPolicy(id, p, 1);
        p = _copy(base);
        p.lineSqrtPriceX96[3] = 0;
        _expectPolicy(id, p, 1);
        // 2: 누적 비율
        p = _copy(base);
        p.cumBps[3] = 9_999;
        _expectPolicy(id, p, 2);
        p = _copy(base);
        p.cumBps[0] = 0;
        _expectPolicy(id, p, 2);
        p = _copy(base);
        p.cumBps[2] = p.cumBps[1];
        _expectPolicy(id, p, 2);
        // 3~7
        p = _copy(base);
        p.maxSellLossBps = 501;
        _expectPolicy(id, p, 3);
        p = _copy(base);
        p.maxOracleDevBps = 1_001;
        _expectPolicy(id, p, 4);
        p = _copy(base);
        p.oracleMaxAge = 0;
        _expectPolicy(id, p, 5);
        p = _copy(base);
        p.oracleMaxAge = 601;
        _expectPolicy(id, p, 5);
        p = _copy(base);
        p.accelSteps = 2;
        _expectPolicy(id, p, 6);
        p = _copy(base);
        p.expiry = uint64(block.timestamp);
        _expectPolicy(id, p, 7);

        // 경계값은 통과
        p = _copy(base);
        p.maxSellLossBps = 500;
        p.maxOracleDevBps = 1_000;
        p.oracleMaxAge = 600;
        p.accelSteps = 1;
        p.cumBps = [uint16(4_000), 7_000, 9_000, 10_000];
        assertEq(vault.policyError(p), 0);
        vm.prank(alice);
        vault.deposit(id, p);
        assertEq(npm.ownerOf(id), address(vault));
    }

    function test_directTransfer_rejected() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        vm.prank(alice);
        vm.expectRevert(LPGuardVault.UnexpectedNFT.selector);
        npm.safeTransferFrom(alice, address(vault), id);
        assertEq(npm.ownerOf(id), alice);
    }

    function test_onERC721Received_directCall_rejected() public {
        vm.expectRevert(LPGuardVault.UnexpectedNFT.selector);
        vault.onERC721Received(address(vault), alice, 1, "");
    }

    function test_withdraw_revert_notOwner_and_notDeposited() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.startPrank(alice);
        npm.approve(address(vault), id);
        vault.deposit(id, p);
        vm.stopPrank();

        vm.prank(bob);
        vm.expectRevert(LPGuardVault.NotOwner.selector);
        vault.withdraw(id);

        vm.prank(alice);
        vault.withdraw(id);

        vm.prank(alice);
        vm.expectRevert(LPGuardVault.NotDeposited.selector);
        vault.withdraw(id);
    }

    function test_withdraw_afterExpiry() public {
        (uint256 id,) = _mintAround(alice, A.POOL_WHSK_USDT, A.WHSK, 2_000e18, 200e6);
        LPGuardVault.Policy memory p = _defaultPolicy(A.POOL_WHSK_USDT);
        vm.startPrank(alice);
        npm.approve(address(vault), id);
        vault.deposit(id, p);
        vm.warp(uint256(p.expiry) + 1);
        vault.withdraw(id);
        vm.stopPrank();
        assertEq(npm.ownerOf(id), alice);
    }

    function test_constructor_badConfig() public {
        vm.expectRevert(abi.encodeWithSelector(LPGuardVault.BadConfig.selector, uint8(5)));
        new LPGuardVault(
            npm,
            ISwapRouter02(A.ROUTER),
            factory,
            A.WETH,
            A.SUPRA_PULL,
            [A.POOL_WETH_USDT, A.POOL_WHSK_USDT],
            [A.PAIR_ETH_USDT, A.PAIR_HSK_USDT]
        );
        vm.expectRevert(abi.encodeWithSelector(LPGuardVault.BadConfig.selector, uint8(4)));
        new LPGuardVault(
            npm,
            ISwapRouter02(A.ROUTER),
            factory,
            A.USDT,
            A.SUPRA_PULL,
            [A.POOL_WHSK_USDT, A.POOL_WHSK_USDT],
            [A.PAIR_HSK_USDT, A.PAIR_HSK_USDT]
        );
    }

    // ------------------------------------------------------------------
    // 도우미
    // ------------------------------------------------------------------

    function _mintAround(address who, address pool, address token0, uint256 amt0, uint256 amt1)
        internal
        returns (uint256 id, uint128 liq)
    {
        return _mintAroundFee(who, pool, token0, A.FEE, amt0, amt1);
    }

    /// 현재 틱 주변 ±10 tickSpacing 범위로 mint한다.
    function _mintAroundFee(address who, address pool, address token0, uint24 fee, uint256 amt0, uint256 amt1)
        internal
        returns (uint256 id, uint128 liq)
    {
        INonfungiblePositionManager.MintParams memory mp = _mintParams(who, pool, token0, fee, amt0, amt1);
        deal(mp.token0, who, amt0);
        deal(mp.token1, who, amt1);
        assertEq(IERC20Minimal(mp.token0).balanceOf(who), amt0, "deal token0");
        assertEq(IERC20Minimal(mp.token1).balanceOf(who), amt1, "deal token1");

        vm.startPrank(who);
        IERC20Minimal(mp.token0).approve(A.NPM, amt0);
        IERC20Minimal(mp.token1).approve(A.NPM, amt1);
        (id, liq,,) = npm.mint(mp);
        vm.stopPrank();
    }

    function _mintParams(address who, address pool, address token0, uint24 fee, uint256 amt0, uint256 amt1)
        internal
        view
        returns (INonfungiblePositionManager.MintParams memory mp)
    {
        IUniswapV3Pool p = IUniswapV3Pool(pool);
        (, int24 tick,,,,,) = p.slot0();
        int24 sp = p.tickSpacing();
        int24 base = tick / sp * sp;
        if (tick < 0 && tick % sp != 0) base -= sp;
        mp.token0 = token0;
        mp.token1 = p.token1();
        mp.fee = fee;
        mp.tickLower = base - 10 * sp;
        mp.tickUpper = base + 10 * sp;
        mp.amount0Desired = amt0;
        mp.amount1Desired = amt1;
        mp.recipient = who;
        mp.deadline = block.timestamp;
    }

    /// 현재 가격을 기준가로, sqrt 가격 1.5%씩(가격 약 3%씩) 아래를 회수선으로 둔 시험용 정책.
    function _defaultPolicy(address pool) internal view returns (LPGuardVault.Policy memory p) {
        (uint160 sqrtP,,,,,,) = IUniswapV3Pool(pool).slot0();
        p.refSqrtPriceX96 = sqrtP;
        for (uint256 i; i < 4; ++i) {
            p.lineSqrtPriceX96[i] = uint160(uint256(sqrtP) * (1000 - 15 * (i + 1)) / 1000);
        }
        p.cumBps = [uint16(2_500), 5_000, 7_500, 10_000];
        p.maxSellLossBps = 150;
        p.maxOracleDevBps = 300;
        p.oracleMaxAge = 120;
        p.accelSteps = 0;
        p.keeper = bob;
        p.expiry = uint64(block.timestamp + 7 days);
    }

    function _copy(LPGuardVault.Policy memory a) internal pure returns (LPGuardVault.Policy memory b) {
        b = abi.decode(abi.encode(a), (LPGuardVault.Policy));
    }

    function _expectPolicy(uint256 id, LPGuardVault.Policy memory p, uint8 code) internal {
        assertEq(vault.policyError(p), code, "policyError");
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(LPGuardVault.InvalidPolicy.selector, code));
        vault.deposit(id, p);
    }
}
