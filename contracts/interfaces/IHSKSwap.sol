// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20 {
    function balanceOf(address owner) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function approve(address spender, uint256 value) external returns (bool);
}
interface IFactory {
    function getPool(address, address, uint24) external view returns (address);
}
interface IPeriphery {
    function factory() external view returns (address);
}
interface IRouter is IPeriphery {
    struct Swap {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amount;
        uint256 limit;
        uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(Swap calldata params) external payable returns (uint256);
    function exactOutputSingle(Swap calldata params) external payable returns (uint256);
}
interface IQuoter is IPeriphery {
    struct Quote {
        address tokenIn;
        address tokenOut;
        uint256 amount;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }
    function quoteExactInputSingle(Quote calldata params) external returns (uint256,uint160,uint32,uint256);
    function quoteExactOutputSingle(Quote calldata params) external returns (uint256,uint160,uint32,uint256);
}
