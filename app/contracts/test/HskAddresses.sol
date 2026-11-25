// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice 체인 177 주소. 개발-가이드.md 3절(11-25 확인)과 같다.
library HskAddresses {
    address internal constant WHSK = 0xB210D2120d57b758EE163cFfb43e73728c471Cf1;
    address internal constant WETH = 0xefd4bC9afD210517803f293ABABd701CaeeCdfd0;
    address internal constant USDT = 0xF1B50eD67A9e2CC94Ad3c477779E2d4cBfFf9029;
    address internal constant FACTORY = 0x972cA9D1662F5e029cD18327D29026532E84c742;
    address internal constant NPM = 0xDF0A9b833Db0E4CeEa103A4408f3B68e7FC0cad5;
    address internal constant ROUTER = 0x2c16f75b95Cf1390c328aB70e2CEE7f4b80bD8F3;
    address internal constant QUOTER = 0x603f70466fDdbE3F238220B9a74FFF419a2BbFDD;
    address internal constant POOL_WETH_USDT = 0xb92b79ed6b370D5cFee2E14B1D0983C258304C16;
    address internal constant POOL_WHSK_USDT = 0x4ff515761864e7838B0AdB8b5b2B8B7A068905dC;
    address internal constant SUPRA_PULL = 0x16f70cAD28dd621b0072B5A8a8c392970E87C3dD;

    uint256 internal constant PAIR_ETH_USDT = 1;
    uint256 internal constant PAIR_HSK_USDT = 517;
    uint24 internal constant FEE = 3000;
}
