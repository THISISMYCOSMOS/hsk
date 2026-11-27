// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "./Fixture.sol";
import {Token, MockDex} from "./Settlement.t.sol";

contract SeriesHandler is Fixture {
    uint256 public charged;
    uint256 public matched;
    bool public stopped;
    bool public failedInvariant;

    constructor() {
        MockDex d = new MockDex();
        m = Market(address(new Token()), address(new Token()), address(d), d, d);
        s = new Settlement(m, address(this), address(this), TREASURY);
        for (uint256 i = A; i <= B; ++i) {
            Token(m.whsk).mint(vm.addr(i), 1000 ether);
            Token(m.usdt).mint(vm.addr(i), 1000e6);
            approveWallet(i);
        }
    }

    function cancel() external {
        vm.prank(vm.addr(A));
        s.invalidateNonce(1);
        stopped = true;
    }

    function fill(uint32 random, uint16 feeSeed) external {
        uint256 q = (uint256(random) % 650 + 1) * 1 ether;
        uint256 fee = uint256(feeSeed) % (q / 1e15 + 1);
        Settlement.ExecutionPlan memory p = plan(true, q, q / 1e13, 0);
        p.planId = bytes32(matched + 1);
        p.tryFallback = false;
        p.legs[0].feeUSDT = fee;
        bytes32 h = s.orderHash(p.legs[0].signedOrder.order);
        uint256 oldFilled = s.filledAmount(h);
        uint256 oldCash = IERC20(m.usdt).balanceOf(RECIPIENT);
        try s.settle(p) returns (Settlement.Result r) {
            if (r == Settlement.Result.Optimized) {
                matched += q;
                charged += fee;
                if (
                    stopped || s.filledAmount(h) != oldFilled + q
                        || IERC20(m.usdt).balanceOf(RECIPIENT) != oldCash + q / 1e13 - fee
                ) failedInvariant = true;
            }
        } catch {
            if (s.filledAmount(h) != oldFilled || IERC20(m.usdt).balanceOf(RECIPIENT) != oldCash) {
                failedInvariant = true;
            }
        }
    }

    function consistent() external view returns (bool) {
        clean();
        return !failedInvariant && matched <= 1000 ether && charged <= 1e6
            && IERC20(m.usdt).balanceOf(TREASURY) == charged
            && IERC20(m.whsk).balanceOf(vm.addr(B)) == 1000 ether + matched
            && IERC20(m.whsk).balanceOf(vm.addr(A)) == 1000 ether - matched
            && IERC20(m.usdt).balanceOf(RECIPIENT) == matched / 1e13 - charged;
    }
}

contract InvariantTest {
    SeriesHandler handler;
    address[] targets;

    function setUp() public {
        handler = new SeriesHandler();
        targets.push(address(handler));
    }

    function targetContracts() external view returns (address[] memory) {
        return targets;
    }

    function invariant_accounting() public view {
        require(handler.consistent());
    }
}
