// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice HSKSwap QuoterV2(0x603f…bFDD). 상태를 바꾸는 형식이지만 eth_call로만 부른다.
interface IQuoterV2 {
    struct QuoteExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }

    function factory() external view returns (address);

    function quoteExactInputSingle(QuoteExactInputSingleParams memory params)
        external
        returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate);
}
