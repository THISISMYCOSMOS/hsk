// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {INonfungiblePositionManager} from "./interfaces/INonfungiblePositionManager.sol";
import {IUniswapV3Factory} from "./interfaces/IUniswapV3Factory.sol";
import {IUniswapV3Pool} from "./interfaces/IUniswapV3Pool.sol";
import {ISwapRouter02} from "./interfaces/ISwapRouter02.sol";
import {IERC20Minimal} from "./interfaces/IERC20Minimal.sol";

/// @title LPGuardVault
/// @notice HSKSwap 범위 LP NFT를 맡아 두고, 가격이 범위 하단으로 내려갈 때 단계별로 회수·매도하는 금고.
/// @dev 11-26 범위: deposit, withdraw, 정책 검사, 조회. executeStep·sellPending·updatePolicy·setPaused는
///      `구현-계획.md` 3절 일정(11-27~)에 따라 이후에 추가한다. 관리자(owner) 변수는 두지 않는다.
contract LPGuardVault {
    // ---------------------------------------------------------------------
    // 자료형 (API-명세.md 1-2)
    // ---------------------------------------------------------------------

    struct Policy {
        uint160 refSqrtPriceX96; // 등록 기준가
        uint160[4] lineSqrtPriceX96; // 25·50·75·100% 회수선. 엄격히 감소. [3]은 범위 하단 가격.
        uint16[4] cumBps; // 누적 회수 비율(L0 기준). 증가, [3] == 10000
        uint16 maxSellLossBps; // 한 번 매도의 최대 손실. 최대 500
        uint16 maxOracleDevBps; // 풀 가격이 오라클보다 이만큼 넘게 낮으면 거부. 최대 1000
        uint32 oracleMaxAge; // 초. 1~600
        uint8 accelSteps; // 0 또는 1
        address keeper; // 0 주소면 소유자만 실행
        uint64 expiry; // 이 시각 이후 실행 불가(인출은 가능)
    }

    struct Position {
        address owner;
        address pool;
        address token0; // 위험자산
        uint128 L0; // 예치 시점 유동성
        uint128 removed; // 지금까지 뺀 유동성
        uint8 stepDone; // 0~4
        bool paused;
        uint256 pendingSell; // 팔지 못하고 금고에 남은 위험자산 양
        Policy policy;
    }

    // ---------------------------------------------------------------------
    // 정책 오류 코드 (InvalidPolicy(code))
    // ---------------------------------------------------------------------
    uint8 public constant POLICY_LINES = 1; // ref > line[0] > line[1] > line[2] > line[3] > 0 이 아님
    uint8 public constant POLICY_CUM_BPS = 2; // 0 < cum[0] < cum[1] < cum[2] < cum[3] == 10000 이 아님
    uint8 public constant POLICY_SELL_LOSS = 3; // maxSellLossBps > 500
    uint8 public constant POLICY_ORACLE_DEV = 4; // maxOracleDevBps > 1000
    uint8 public constant POLICY_ORACLE_AGE = 5; // oracleMaxAge 가 0 이거나 600 초과
    uint8 public constant POLICY_ACCEL = 6; // accelSteps > 1
    uint8 public constant POLICY_EXPIRY = 7; // expiry <= block.timestamp

    uint16 public constant MAX_SELL_LOSS_BPS = 500;
    uint16 public constant MAX_ORACLE_DEV_BPS = 1000;
    uint32 public constant MAX_ORACLE_AGE = 600;
    uint16 public constant BPS = 10_000;

    // ---------------------------------------------------------------------
    // 배포 시 고정값 (API-명세.md 1-1)
    // ---------------------------------------------------------------------
    INonfungiblePositionManager public immutable npm;
    ISwapRouter02 public immutable router;
    IUniswapV3Factory public immutable factory;
    address public immutable usdt;
    address public immutable supra;
    address public immutable poolA;
    address public immutable poolB;
    uint256 public immutable pairIndexA;
    uint256 public immutable pairIndexB;

    // ---------------------------------------------------------------------
    // 상태
    // ---------------------------------------------------------------------
    mapping(uint256 => Position) internal _positions;

    /// @dev deposit 도중에만 0이 아니다(tokenId + 1). onERC721Received가 이 값으로 들어오는 NFT를 확인한다.
    uint256 private transient _expectingTokenIdPlusOne;
    uint256 private transient _locked;

    // ---------------------------------------------------------------------
    // 이벤트·오류 (API-명세.md 1-5, 1-6)
    // ---------------------------------------------------------------------
    event Deposited(uint256 indexed tokenId, address indexed owner, address pool, uint128 L0, Policy policy);
    event Withdrawn(uint256 indexed tokenId, address indexed owner, uint256 pendingReturned);

    error NotOwner();
    error InvalidPolicy(uint8 code);
    error UnsupportedPool();
    error EmptyPosition();
    error UnexpectedNFT();
    error NotDeposited();
    error Reentrancy();
    error TransferFailed();
    error BadConfig(uint8 code);

    modifier nonReentrant() {
        if (_locked != 0) revert Reentrancy();
        _locked = 1;
        _;
        _locked = 0;
    }

    /// @param pools_ 등록할 두 풀(WETH/USDT 0.30%, WHSK/USDT 0.30%)
    /// @param pairIndexes_ 각 풀의 Supra 쌍 번호(WETH/USDT → 1, HSK/USDT → 517)
    constructor(
        INonfungiblePositionManager npm_,
        ISwapRouter02 router_,
        IUniswapV3Factory factory_,
        address usdt_,
        address supra_,
        address[2] memory pools_,
        uint256[2] memory pairIndexes_
    ) {
        // 주소 묶음이 서로 맞는지 배포 때 확인한다. 잘못된 주소로 배포하면 되돌린다.
        if (npm_.factory() != address(factory_)) revert BadConfig(1);
        if (router_.factory() != address(factory_)) revert BadConfig(2);
        if (supra_ == address(0) || supra_.code.length == 0) revert BadConfig(3);
        if (pools_[0] == pools_[1]) revert BadConfig(4);
        for (uint256 i; i < 2; ++i) {
            IUniswapV3Pool p = IUniswapV3Pool(pools_[i]);
            if (p.token1() != usdt_) revert BadConfig(5);
            if (factory_.getPool(p.token0(), p.token1(), p.fee()) != pools_[i]) revert BadConfig(6);
            if (pairIndexes_[i] == 0) revert BadConfig(7);
        }

        npm = npm_;
        router = router_;
        factory = factory_;
        usdt = usdt_;
        supra = supra_;
        poolA = pools_[0];
        poolB = pools_[1];
        pairIndexA = pairIndexes_[0];
        pairIndexB = pairIndexes_[1];
    }

    // ---------------------------------------------------------------------
    // 사용자 함수
    // ---------------------------------------------------------------------

    /// @notice NFT를 금고로 옮기고 보호를 켠다. 사전에 npm.approve(vault, tokenId) 또는 setApprovalForAll 필요.
    function deposit(uint256 tokenId, Policy calldata p) external nonReentrant {
        if (npm.ownerOf(tokenId) != msg.sender) revert NotOwner();

        (,, address token0, address token1, uint24 fee,,, uint128 liquidity,,,,) = npm.positions(tokenId);
        if (token1 != usdt) revert UnsupportedPool();
        address pool = factory.getPool(token0, token1, fee);
        if (!isSupportedPool(pool)) revert UnsupportedPool();
        if (liquidity == 0) revert EmptyPosition();

        uint8 code = policyError(p);
        if (code != 0) revert InvalidPolicy(code);

        Position storage pos = _positions[tokenId];
        pos.owner = msg.sender;
        pos.pool = pool;
        pos.token0 = token0;
        pos.L0 = liquidity;
        pos.removed = 0;
        pos.stepDone = 0;
        pos.paused = false;
        pos.pendingSell = 0;
        pos.policy = p;

        _expectingTokenIdPlusOne = tokenId + 1;
        npm.safeTransferFrom(msg.sender, address(this), tokenId);
        // onERC721Received가 성공하면 값을 지운다. 남아 있으면 콜백이 오지 않은 것이다.
        if (_expectingTokenIdPlusOne != 0) revert UnexpectedNFT();

        emit Deposited(tokenId, msg.sender, pool, liquidity, p);
    }

    /// @notice NFT와 금고에 남은 위험자산(pendingSell)을 소유자에게 돌려주고 기록을 지운다.
    /// 중지·만료와 상관없이 언제든 할 수 있다.
    function withdraw(uint256 tokenId) external nonReentrant {
        Position storage pos = _positions[tokenId];
        address owner_ = pos.owner;
        if (owner_ == address(0)) revert NotDeposited();
        if (owner_ != msg.sender) revert NotOwner();

        address token0 = pos.token0;
        uint256 pending = pos.pendingSell;
        delete _positions[tokenId];

        if (pending != 0) _safeTransfer(token0, owner_, pending);
        npm.safeTransferFrom(address(this), owner_, tokenId);

        emit Withdrawn(tokenId, owner_, pending);
    }

    /// @dev deposit 도중 NPM에서 오는, 기다리던 tokenId만 받는다. 그 밖의 NFT 직접 전송은 거부한다.
    function onERC721Received(address operator, address, uint256 tokenId, bytes calldata) external returns (bytes4) {
        if (msg.sender != address(npm) || operator != address(this) || _expectingTokenIdPlusOne != tokenId + 1) {
            revert UnexpectedNFT();
        }
        _expectingTokenIdPlusOne = 0;
        return this.onERC721Received.selector;
    }

    // ---------------------------------------------------------------------
    // 조회
    // ---------------------------------------------------------------------

    function getPosition(uint256 tokenId) external view returns (Position memory) {
        return _positions[tokenId];
    }

    function isSupportedPool(address pool) public view returns (bool) {
        return pool != address(0) && (pool == poolA || pool == poolB);
    }

    function pairIndexOf(address pool) public view returns (uint256) {
        if (pool == poolA) return pairIndexA;
        if (pool == poolB) return pairIndexB;
        revert UnsupportedPool();
    }

    /// @notice 정책 검사. 0이면 통과, 아니면 InvalidPolicy 코드.
    /// @dev line[3]이 NFT 범위 하단과 같은지는 계약에서 확인하지 않는다(TickMath를 들이지 않기 위해).
    ///      회수선은 소유자가 정하는 값이고, 화면·에이전트가 범위 하단으로 채운다.
    function policyError(Policy calldata p) public view returns (uint8) {
        if (p.lineSqrtPriceX96[3] == 0) return POLICY_LINES;
        if (p.refSqrtPriceX96 <= p.lineSqrtPriceX96[0]) return POLICY_LINES;
        for (uint256 i = 1; i < 4; ++i) {
            if (p.lineSqrtPriceX96[i - 1] <= p.lineSqrtPriceX96[i]) return POLICY_LINES;
        }

        if (p.cumBps[0] == 0 || p.cumBps[3] != BPS) return POLICY_CUM_BPS;
        for (uint256 i = 1; i < 4; ++i) {
            if (p.cumBps[i - 1] >= p.cumBps[i]) return POLICY_CUM_BPS;
        }

        if (p.maxSellLossBps > MAX_SELL_LOSS_BPS) return POLICY_SELL_LOSS;
        if (p.maxOracleDevBps > MAX_ORACLE_DEV_BPS) return POLICY_ORACLE_DEV;
        if (p.oracleMaxAge == 0 || p.oracleMaxAge > MAX_ORACLE_AGE) return POLICY_ORACLE_AGE;
        if (p.accelSteps > 1) return POLICY_ACCEL;
        if (p.expiry <= block.timestamp) return POLICY_EXPIRY;
        return 0;
    }

    // ---------------------------------------------------------------------
    // 내부
    // ---------------------------------------------------------------------

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory ret) = token.call(abi.encodeCall(IERC20Minimal.transfer, (to, amount)));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed();
    }
}
