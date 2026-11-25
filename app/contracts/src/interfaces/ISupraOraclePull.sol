// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Supra Pull Oracle(0x16f7…C3dD). timestamp는 밀리초(11-25 확인).
interface ISupraOraclePull {
    struct PriceInfo {
        uint256[] pairs;
        uint256[] prices;
        uint256[] timestamp;
        uint256[] decimal;
        uint256[] round;
    }

    function verifyOracleProofV2(bytes calldata _bytesProof) external returns (PriceInfo memory);
}
