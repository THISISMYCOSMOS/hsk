// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import {FullMath} from "../src/FullMath.sol";

contract MathTest {
    function testUint256AndFractionalRounding() public pure {
        uint256 m = type(uint256).max;
        require(FullMath.mulDiv(m, m - 1, m) == m - 1);
        require(FullMath.mulDiv(m - 1, m - 1, m) == m - 2);
        require(FullMath.mulDivRoundingUp(m - 1, m - 1, m) == m - 1);
        require(FullMath.mulDivRoundingUp(3, 5, 2) == 8 && FullMath.mulDiv(3, 5, 2) == 7);
    }
}
