// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        // Two DISTINCT roles, both set once, at deployment:
        //   verifier   - may sign settlement attestations (EIP-712)
        //   registrar  - may register commitments
        // For the local MVP these are two different Anvil development accounts
        // so that the roles are demonstrably separate.
        address verifier = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
        address registrar = 0x90F79bf6EB2c4f870365E785982E1f101E93b906;
        new TerraCycleEscrow(verifier, registrar, "TerraCycleEscrow", "1");
        vm.stopBroadcast();
    }
}
