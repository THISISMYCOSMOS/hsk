// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import {IToken} from "../src/DirectSettlement.sol";

// From HSK_A_Session1/test/Fixture.sol. Used only by local tests.
contract Token is IToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    uint8 public immutable decimals;

    constructor(uint8 d) {
        decimals = d;
    }

    function mint(address to, uint256 n) external {
        balanceOf[to] += n;
    }

    function approve(address spender, uint256 n) external {
        allowance[msg.sender][spender] = n;
    }

    function transferFrom(address from, address to, uint256 n) external returns (bool) {
        require(allowance[from][msg.sender] >= n, "allowance");
        require(balanceOf[from] >= n, "inventory");
        allowance[from][msg.sender] -= n;
        balanceOf[from] -= n;
        balanceOf[to] += n;
        return true;
    }
}
