// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import {Settlement} from "../src/Settlement.sol";
import {Market, HSKMainnet} from "../src/Market.sol";
import {IRouter, IQuoter} from "../interfaces/IHSKSwap.sol";

interface DeployVm {
    function envAddress(string calldata name) external view returns (address);
    function envUint(string calldata name) external view returns (uint256);
    function startBroadcast(address sender) external;
    function stopBroadcast() external;
}

contract Deploy {
    DeployVm constant vm = DeployVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    /// Chain 177 only supports a simulated CREATE here. Local Anvil or HSK
    /// testnet broadcasts additionally require the caller's --broadcast flag.
    function run() external returns (Settlement deployed) {
        require(block.chainid == vm.envUint("EXPECTED_CHAIN_ID"), "chain id");
        bool mainnet = block.chainid == 177;
        require(mainnet || block.chainid == 31337 || block.chainid == 133, "unsupported network");
        address sender = vm.envAddress("DEPLOYER");
        address admin = vm.envAddress("PAUSE_ADMIN");
        address operator = vm.envAddress("SETTLE_OPERATOR");
        address collector = vm.envAddress("FEE_RECIPIENT");
        uint256 gasBudget = vm.envUint("DEPLOY_BUDGET_WEI");
        uint256 gasPriceCap = vm.envUint("GAS_PRICE_CAP_WEI");
        require(sender != address(0) && admin != address(0) && operator != address(0), "roles");
        require(
            gasBudget > 0 && sender.balance >= gasBudget && gasPriceCap > 0 && tx.gasprice <= gasPriceCap,
            "budget/price"
        );
        Market memory market;
        if (mainnet) {
            market = HSKMainnet.market();
        } else {
            market = Market(
                vm.envAddress("WHSK"),
                vm.envAddress("USDT"),
                vm.envAddress("POOL"),
                IRouter(vm.envAddress("ROUTER")),
                IQuoter(vm.envAddress("QUOTER"))
            );
        }
        if (!mainnet) vm.startBroadcast(sender);
        uint256 start = gasleft();
        deployed = new Settlement(market, admin, operator, collector);
        uint256 estimate = (start - gasleft() + 53000) * gasPriceCap;
        if (!mainnet) vm.stopBroadcast();
        require(estimate <= gasBudget, "estimated deployment cost exceeds budget");
        require(deployed.admin() == admin && deployed.operator() == operator && !deployed.paused(), "config");
    }
}
