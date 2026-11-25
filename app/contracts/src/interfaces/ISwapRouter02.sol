// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice HSKSwap SwapRouter02(0x2c16…D8F3). exactInputSingle 구조체에 deadline이 없다(7개 필드).
interface ISwapRouter02 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function factory() external view returns (address);
    function WETH9() external view returns (address);
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}
