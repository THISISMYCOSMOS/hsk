// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import "./Fixture.sol";
import {OrderValidation} from "../src/OrderValidation.sol";

contract VectorTest is Fixture {
    function testWalletVectors() public {
        vm.chainId(31337);
        address verifier = address(0x1234);
        vm.etch(verifier, type(HashHarness).runtimeCode);
        Order memory o;
        o.owner = 0xE6b3367318C5e11a6eED3Cd0D850eC06A02E9b90;
        o.recipient = 0x000000000000000000000000000000000000bEEF;
        o.tokenIn = 0xB210D2120d57b758EE163cFfb43e73728c471Cf1;
        o.tokenOut = 0xF1B50eD67A9e2CC94Ad3c477779E2d4cBfFf9029;
        o.orderKind = 0;
        o.amountIn = 1000000000000000000000;
        o.amountOut = 80000000;
        o.validAfter = 1;
        o.deadline = 2000000000;
        o.nonce = 1;
        o.partiallyFillable = true;
        o.allowDexFallback = true;
        o.executionPriority = 1;
        o.maxFeeAmount = 100;
        o.minImprovementAmount = 2;
        o.allowedExecutor = 0x0000000000000000000000000000000000000000;
        o.allowDex = true;
        o.immediate = true;
        require(
            HashHarness(verifier).orderHash(o) == 0xe9b4da4f7d7a255883e3ab74f0d94806404952abcdb35949492698a80c6e0a4d
        );
        o.owner = 0x88C0e901bd1fd1a77BdA342f0d2210fDC71Cef6B;
        o.recipient = 0x000000000000000000000000000000000000bEEF;
        o.tokenIn = 0xF1B50eD67A9e2CC94Ad3c477779E2d4cBfFf9029;
        o.tokenOut = 0xB210D2120d57b758EE163cFfb43e73728c471Cf1;
        o.orderKind = 1;
        o.amountIn = 90000000;
        o.amountOut = 1000000000000000000000;
        o.validAfter = 1;
        o.deadline = 2000000000;
        o.nonce = 1;
        o.partiallyFillable = true;
        o.allowDexFallback = true;
        o.executionPriority = 1;
        o.maxFeeAmount = 100;
        o.minImprovementAmount = 2;
        o.allowedExecutor = 0x0000000000000000000000000000000000000000;
        o.allowDex = true;
        o.immediate = true;
        require(
            HashHarness(verifier).orderHash(o) == 0xf1d3e20a38934117749c54aaadddaeb5c2a94f981b5e6897a44f7c170cafb459
        );
    }
}

contract HashHarness is OrderValidation {}
