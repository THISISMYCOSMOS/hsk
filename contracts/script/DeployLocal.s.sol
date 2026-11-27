// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import {DeployVm} from "./Deploy.s.sol";
import {MockDex, Token} from "../test/Settlement.t.sol";
import {Settlement} from "../src/Settlement.sol";
import {Market} from "../src/Market.sol";

contract DeployLocal {
    DeployVm constant vm = DeployVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (Settlement settlement) {
        require(block.chainid == 31337, "local mock chain only");
        address sender = vm.envAddress("DEPLOYER");
        vm.startBroadcast(sender);
        MockDex dex = new MockDex();
        Market memory m = Market(address(new Token()), address(new Token()), address(dex), dex, dex);
        settlement = new Settlement(m, sender, sender, address(0));
        vm.stopBroadcast();
    }
}
