// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        address verifier = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
        new TerraCycleEscrow(verifier);
        vm.stopBroadcast();
    }
}
