// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IToken {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// A trusted, pair-specific read-only adapter must return a current exact-input DEX quote.
interface IDexQuote {
    function amountOut(address sellToken, uint128 amountIn) external view returns (uint256);
}

contract DirectSettlement {
    struct Order {
        address maker;
        address sellToken;
        uint128 sellAmount;
        uint128 minBuyAmount;
        uint128 minFill;
        uint128 costBufferPerFill; // Buy-token base units, fixed per fill
        uint64 deadline;
        bytes32 salt;
    }

    struct Signature {
        uint8 v;
        bytes32 r;
        bytes32 s;
    }

    bytes32 public constant ORDER_TYPEHASH = keccak256(
        "Order(address maker,address sellToken,uint128 sellAmount,uint128 minBuyAmount,uint128 minFill,uint128 costBufferPerFill,uint64 deadline,bytes32 salt)"
    );
    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    uint256 private constant HALF_CURVE_ORDER = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    address public immutable whsk;
    address public immutable usdt;
    IDexQuote public immutable dex;
    mapping(bytes32 => uint128) public filled;
    mapping(bytes32 => bool) public cancelled;
    bool private entered;

    error InvalidOrder();
    error InvalidSignature();
    error InactiveOrder();
    error Uneconomic();
    error TransferMismatch();
    error Reentry();

    event Cancelled(bytes32 indexed digest, address indexed maker);
    event Matched(bytes32 indexed left, bytes32 indexed right, uint128 leftSold, uint128 rightSold);

    constructor(address whsk_, address usdt_, IDexQuote dex_) {
        if (whsk_ == usdt_ || whsk_.code.length == 0 || usdt_.code.length == 0 || address(dex_).code.length == 0) {
            revert InvalidOrder();
        }
        whsk = whsk_;
        usdt = usdt_;
        dex = dex_;
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("HSK Smart Execution"), keccak256("1"), block.chainid, address(this))
        );
    }

    function orderDigest(Order calldata order) public view returns (bytes32) {
        return keccak256(abi.encodePacked(hex"1901", domainSeparator(), keccak256(abi.encode(ORDER_TYPEHASH, order))));
    }

    function cancel(Order calldata order) external {
        if (msg.sender != order.maker) revert InvalidOrder();
        bytes32 digest = orderDigest(order);
        cancelled[digest] = true;
        emit Cancelled(digest, order.maker);
    }

    function matchOrders(
        Order calldata left,
        Signature calldata leftSignature,
        uint128 leftSold,
        Order calldata right,
        Signature calldata rightSignature,
        uint128 rightSold
    ) external {
        if (entered) revert Reentry();
        entered = true;
        bool isPair =
            (left.sellToken == whsk && right.sellToken == usdt) || (left.sellToken == usdt && right.sellToken == whsk);
        if (!isPair || left.maker == right.maker) revert InvalidOrder();
        bytes32 leftDigest = consume(left, leftSignature, leftSold, rightSold);
        bytes32 rightDigest = consume(right, rightSignature, rightSold, leftSold);

        transferExact(IToken(left.sellToken), left.maker, right.maker, leftSold);
        transferExact(IToken(right.sellToken), right.maker, left.maker, rightSold);

        emit Matched(leftDigest, rightDigest, leftSold, rightSold);
        entered = false;
    }

    function consume(Order calldata order, Signature calldata signature, uint128 sold, uint128 bought)
        private
        returns (bytes32 digest)
    {
        digest = orderDigest(order);
        if (cancelled[digest] || block.timestamp > order.deadline) revert InactiveOrder();
        if (
            order.maker == address(0) || order.minFill == 0 || order.minBuyAmount == 0 || sold < order.minFill
                || uint256(filled[digest]) + sold > order.sellAmount
        ) revert InvalidOrder();
        if (
            (signature.v != 27 && signature.v != 28) || uint256(signature.s) > HALF_CURVE_ORDER
                || ecrecover(digest, signature.v, signature.r, signature.s) != order.maker
        ) revert InvalidSignature();
        if (uint256(bought) * order.sellAmount < uint256(order.minBuyAmount) * sold) revert InvalidOrder();

        uint256 benchmark = dex.amountOut(order.sellToken, sold);
        if (benchmark == 0 || bought <= benchmark || bought - benchmark <= order.costBufferPerFill) {
            revert Uneconomic();
        }
        filled[digest] += sold;
    }

    // Both balance deltas must match, including for ERC-20s with an empty return value.
    function transferExact(IToken token, address from, address to, uint128 amount) private {
        uint256 fromBefore = token.balanceOf(from);
        uint256 toBefore = token.balanceOf(to);
        (bool ok, bytes memory data) = address(token).call(abi.encodeCall(token.transferFrom, (from, to, amount)));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TransferMismatch();
        uint256 fromAfter = token.balanceOf(from);
        uint256 toAfter = token.balanceOf(to);
        if (
            fromAfter > fromBefore || fromBefore - fromAfter != amount || toAfter < toBefore
                || toAfter - toBefore != amount
        ) {
            revert TransferMismatch();
        }
    }
}
