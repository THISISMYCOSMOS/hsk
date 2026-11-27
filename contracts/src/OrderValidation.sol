// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {FullMath} from "./FullMath.sol";

struct Order {
    address owner;
    address recipient;
    address tokenIn;
    address tokenOut;
    uint8 orderKind;
    uint256 amountIn;
    uint256 amountOut;
    uint256 validAfter;
    uint256 deadline;
    uint256 nonce;
    bool partiallyFillable;
    bool allowDexFallback;
    uint8 executionPriority;
    uint256 maxFeeAmount;
    uint256 minImprovementAmount;
    address allowedExecutor;
    bool allowDex;
    bool immediate;
}

struct SignedOrder {
    Order order;
    bytes signature;
}

abstract contract OrderValidation {
    bytes32 public constant ORDER_TYPEHASH = keccak256(
        "Order(address owner,address recipient,address tokenIn,address tokenOut,uint8 orderKind,uint256 amountIn,uint256 amountOut,uint256 validAfter,uint256 deadline,uint256 nonce,bool partiallyFillable,bool allowDexFallback,uint8 executionPriority,uint256 maxFeeAmount,uint256 minImprovementAmount,address allowedExecutor,bool allowDex,bool immediate)"
    );
    bytes32 private constant DOMAIN =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    mapping(bytes32 => uint256) public filledAmount;
    mapping(bytes32 => bool) public isOrderCancelled;
    mapping(address => mapping(uint256 => bool)) public invalidNonce;
    mapping(address => mapping(uint256 => bytes32)) public nonceOrder;
    error InvalidSignature();
    error InvalidOrder();
    error InactiveOrder();
    error FillLimit();
    event Cancelled(bytes32 indexed digest, address indexed owner);
    event NonceInvalidated(address indexed owner, uint256 indexed nonce);

    function domainSeparator() public view returns (bytes32) {
        return
            keccak256(
                abi.encode(DOMAIN, keccak256("HSK Smart Execution"), keccak256("1"), block.chainid, address(this))
            );
    }

    function orderHash(Order calldata o) public view returns (bytes32) {
        return keccak256(abi.encodePacked(hex"1901", domainSeparator(), keccak256(abi.encode(ORDER_TYPEHASH, o))));
    }

    function cancelOrder(Order calldata o) external {
        if (msg.sender != o.owner) revert InvalidOrder();
        bytes32 digest = orderHash(o);
        isOrderCancelled[digest] = true;
        emit Cancelled(digest, msg.sender);
    }

    function invalidateNonce(uint256 nonce) external {
        invalidNonce[msg.sender][nonce] = true;
        emit NonceInvalidated(msg.sender, nonce);
    }

    function _validate(SignedOrder calldata signed, uint256 quantity) internal view returns (bytes32 digest) {
        Order calldata o = signed.order;
        if (
            o.owner == address(0) || o.owner == address(this) || o.recipient == address(0)
                || o.recipient == address(this) || o.amountIn == 0 || o.amountOut == 0 || o.orderKind > 1
                || o.executionPriority > 1 || (o.allowedExecutor != address(0) && o.allowedExecutor != msg.sender)
        ) revert InvalidOrder();
        digest = orderHash(o);
        bytes32 bound = nonceOrder[o.owner][o.nonce];
        if (
            block.timestamp < o.validAfter || block.timestamp > o.deadline || isOrderCancelled[digest]
                || invalidNonce[o.owner][o.nonce] || (bound != 0 && bound != digest)
        ) revert InactiveOrder();
        bytes calldata sig = signed.signature;
        if (sig.length != 65) revert InvalidSignature();
        uint8 v = uint8(sig[64]);
        bytes32 s = bytes32(sig[32:64]);
        if (
            (v != 27 && v != 28) || uint256(s) > 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0
                || ecrecover(digest, v, bytes32(sig[:32]), s) != o.owner
        ) revert InvalidSignature();
        uint256 total = _total(o);
        if (quantity == 0 || quantity > total - filledAmount[digest] || (!o.partiallyFillable && quantity != total)) {
            revert FillLimit();
        }
    }

    function _total(Order calldata o) internal pure returns (uint256) {
        return o.orderKind == 0 ? o.amountIn : o.amountOut;
    }

    function _cashLimit(Order calldata o, uint256 quantity) internal pure returns (uint256) {
        if (o.orderKind == 0) return FullMath.mulDivRoundingUp(quantity, o.amountOut, o.amountIn);
        return FullMath.mulDiv(quantity, o.amountIn, o.amountOut);
    }
}
