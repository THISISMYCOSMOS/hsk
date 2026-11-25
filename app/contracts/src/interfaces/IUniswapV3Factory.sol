// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice HSKSwap Factory(0x972c…c742) 읽기 전용 부분.
interface IUniswapV3Factory {
    function getPool(address tokenA, address tokenB, uint24 fee) external view returns (address pool);
    function feeAmountTickSpacing(uint24 fee) external view returns (int24);
}
