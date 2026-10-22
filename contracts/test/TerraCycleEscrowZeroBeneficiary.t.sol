// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";

/**
 * @title TerraCycleEscrowZeroBeneficiaryTest
 * @notice TASK-004B.2A - zero-address payout protection.
 *
 * @dev A commitment whose beneficiary is `address(0)` makes the settlement
 *      transfer the escrowed reward to the zero address. `payable(address(0))
 *      .call{value: amount}("")` SUCCEEDS, so the funds leave the escrow, the
 *      accounting marks the commitment as `Paid`, and the money is
 *      irrecoverable: nobody controls `address(0)`.
 *
 *      The beneficiary can only be supplied once, in `registerCommitment`, and
 *      there is no setter, so registration is the earliest and only boundary
 *      where the value can be rejected.
 */
contract TerraCycleEscrowZeroBeneficiaryTest is Test {
    TerraCycleEscrow public escrow;
    BalanceProbe public probe;

    uint256 public constant VERIFIER_KEY = 0xA11CE;
    address public verifier;
    address public beneficiary;
    address public funder;

    bytes32 public constant PARCEL_ID = bytes32(uint256(0x1111));
    bytes32 public constant SEASON_ID = bytes32(uint256(0x2222));
    bytes32 public constant PLAN_HASH = keccak256("plan-document");
    bytes32 public constant EVIDENCE_HASH = keccak256("evidence-document");
    uint256 public constant REWARD = 1 ether;

    string public constant DOMAIN_NAME = "TerraCycleEscrow";
    string public constant DOMAIN_VERSION = "1";

    /// @dev Computed locally so this file compiles against the contract both
    ///      before and after the fix.
    bytes4 internal constant ZERO_BENEFICIARY_SELECTOR = bytes4(keccak256("ZeroBeneficiary()"));

    function setUp() public {
        verifier = vm.addr(VERIFIER_KEY);
        beneficiary = makeAddr("beneficiary");
        funder = makeAddr("funder");

        vm.deal(funder, 100 ether);

        escrow = new TerraCycleEscrow(verifier, beneficiary, DOMAIN_NAME, DOMAIN_VERSION);
        probe = new BalanceProbe();
    }

    function _register(address beneficiary_) internal returns (bytes32 commitmentId) {
        vm.prank(beneficiary);
        commitmentId = escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary_, uint64(block.timestamp + 1 days)
        );
    }

    function _sign(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        view
        returns (bytes memory)
    {
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(DOMAIN_NAME)),
                keccak256(bytes(DOMAIN_VERSION)),
                block.chainid,
                address(escrow)
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256(
                    "VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)"
                ),
                commitmentId,
                planHash,
                evidenceHash,
                verdict,
                validUntil
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(VERIFIER_KEY, digest);
        return abi.encodePacked(r, s, v);
    }

    function _settle(bytes32 commitmentId, uint8 verdict) internal {
        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, verdict, uint64(block.timestamp + 1 days));
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: verdict,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            signature
        );
    }

    // =====================================================================
    // 1. THE REGRESSION TEST
    //
    //    This test FAILS against the vulnerable contract (the registration
    //    succeeds, so the expected revert never happens) and PASSES once the
    //    zero-address beneficiary is rejected.
    // =====================================================================

    function test_register_rejects_a_zero_beneficiary() public {
        vm.prank(beneficiary);
        vm.expectRevert(ZERO_BENEFICIARY_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, address(0), uint64(block.timestamp + 1 days)
        );
    }

    // =====================================================================
    // 2. THE VULNERABILITY ITSELF
    //
    //    Kept as executable documentation of what the bug did, so that the
    //    fix can never be silently reverted.
    // =====================================================================

    /// @dev The vulnerable behaviour: registering with `address(0)` succeeded
    ///      and the settlement transferred the reward to the zero address,
    ///      where the money is irrecoverable.
    ///
    ///      Against the FIXED contract this test reverts at registration, so
    ///      it asserts that the burn is now unreachable rather than that it
    ///      happens.
    function test_a_zero_beneficiary_can_never_receive_a_payout() public {
        bytes32 commitmentId;
        bytes memory revertReason;
        bool created = true;

        // A low-level call so the revert can be observed: the test then
        // behaves the same way against the vulnerable contract and against the
        // fixed one. The prank is explicit: the registrar is the `beneficiary`.
        vm.prank(beneficiary);
        (bool ok, bytes memory ret) = address(escrow).call(
            abi.encodeWithSelector(
                TerraCycleEscrow.registerCommitment.selector,
                PARCEL_ID,
                SEASON_ID,
                PLAN_HASH,
                address(0),
                uint64(block.timestamp + 1 days)
            )
        );
        if (ok) {
            commitmentId = keccak256(abi.encode(PARCEL_ID, SEASON_ID));
        } else {
            created = false;
            revertReason = ret;
        }

        if (created) {
            // The vulnerable path is still reachable: demonstrate the burn.
            uint256 zeroBalanceBefore = probe.balanceOf(address(0));
            uint256 escrowBefore = address(escrow).balance;

            _settle(commitmentId, 0);

            (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) =
                escrow.getCommitment(commitmentId);

            emit log_named_uint("VULNERABLE: escrow balance before settle", escrowBefore);
            emit log_named_uint("VULNERABLE: escrow balance after  settle", address(escrow).balance);
            emit log_named_uint("VULNERABLE: address(0) balance before", zeroBalanceBefore);
            emit log_named_uint("VULNERABLE: address(0) balance after ", probe.balanceOf(address(0)));
            emit log_named_uint("VULNERABLE: commitment reward recorded ", reward);
            emit log_named_uint("VULNERABLE: commitment state (2=Funded,3=Paid)", uint256(uint8(state)));

            assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Paid));
            assertEq(reward, 0, "the accounting says the reward was paid");
            assertEq(address(escrow).balance, escrowBefore - REWARD, "the escrow released the funds");
            assertEq(
                probe.balanceOf(address(0)),
                zeroBalanceBefore + REWARD,
                "the funds were transferred to the zero address, where they are lost"
            );
        } else {
            // The fixed contract: the registration was rejected with the
            // dedicated error, no commitment exists, and no ETH can reach the
            // zero address.
            assertEq(
                bytes4(revertReason),
                ZERO_BENEFICIARY_SELECTOR,
                "the registration must be rejected with ZeroBeneficiary"
            );
            assertFalse(
                escrow.registeredId(keccak256(abi.encode(PARCEL_ID, SEASON_ID))),
                "a commitment id was reserved"
            );
            (, address storedBeneficiary, , , , TerraCycleEscrow.CommitmentState state) =
                escrow.getCommitment(keccak256(abi.encode(PARCEL_ID, SEASON_ID)));
            assertEq(storedBeneficiary, address(0), "no beneficiary was stored");
            assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.None), "a commitment was created");
            assertEq(address(escrow).balance, 0, "no ETH reached the escrow");
            assertEq(probe.balanceOf(address(0)), 0, "no ETH reached the zero address");
        }
    }



    // =====================================================================
    // 3. THE FIX MUST NOT BREAK ANYTHING ELSE
    // =====================================================================

    function test_a_valid_nonzero_beneficiary_still_works() public {
        bytes32 commitmentId = _register(beneficiary);

        (, , , , , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Registered));
        (, address storedBeneficiary, , , , ) = escrow.getCommitment(commitmentId);
        assertEq(storedBeneficiary, beneficiary);
    }

    function test_a_failed_zero_beneficiary_registration_changes_no_balance_and_no_state() public {
        uint256 escrowBalanceBefore = address(escrow).balance;
        uint256 funderBalanceBefore = funder.balance;

        vm.prank(beneficiary);
        vm.expectRevert(ZERO_BENEFICIARY_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, address(0), uint64(block.timestamp + 1 days)
        );

        assertEq(address(escrow).balance, escrowBalanceBefore, "the escrow balance changed");
        assertEq(funder.balance, funderBalanceBefore, "the funder balance changed");
        assertEq(address(escrow).balance, 0, "no ETH reached the escrow");

        // No partial commitment state was created.
        bytes32 expectedId = keccak256(abi.encode(PARCEL_ID, SEASON_ID));
        assertFalse(escrow.registeredId(expectedId), "a commitment id was reserved");
        (, address storedBeneficiary, , , , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(expectedId);
        assertEq(storedBeneficiary, address(0), "no beneficiary was stored");
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.None), "a commitment was created");
    }

    function test_repeated_zero_beneficiary_registrations_are_all_rejected() public {
        for (uint256 i = 0; i < 5; i++) {
            vm.prank(beneficiary);
            vm.expectRevert(ZERO_BENEFICIARY_SELECTOR);
            escrow.registerCommitment(
                PARCEL_ID,
                SEASON_ID,
                PLAN_HASH,
                address(0),
                uint64(block.timestamp + 1 days)
            );
        }
        assertFalse(escrow.registeredId(keccak256(abi.encode(PARCEL_ID, SEASON_ID))));
    }

    function test_the_zero_beneficiary_protection_cannot_be_bypassed_by_using_another_parcel_or_season() public {
        bytes32[3] memory parcels = [bytes32(uint256(0x1111)), bytes32(uint256(0x2222)), bytes32(uint256(0x3333))];
        for (uint256 i = 0; i < parcels.length; i++) {
            vm.prank(beneficiary);
            vm.expectRevert(ZERO_BENEFICIARY_SELECTOR);
            escrow.registerCommitment(
                parcels[i], SEASON_ID, PLAN_HASH, address(0), uint64(block.timestamp + 1 days)
            );
        }
    }

    /// @dev Any non-zero address must still be accepted.
    function testFuzz_a_nonzero_beneficiary_is_always_accepted(address candidate) public {
        vm.assume(candidate != address(0));
        vm.assume(candidate != address(escrow));

        bytes32 parcelId = bytes32(uint256(uint160(candidate)));
        vm.prank(beneficiary);
        bytes32 commitmentId = escrow.registerCommitment(
            parcelId, SEASON_ID, PLAN_HASH, candidate, uint64(block.timestamp + 1 days)
        );

        (, address storedBeneficiary, , , , ) = escrow.getCommitment(commitmentId);
        assertEq(storedBeneficiary, candidate);
    }

    // =====================================================================
    // 4. THE EXISTING FLOWS STILL WORK
    // =====================================================================

    function test_funding_behaviour_is_unchanged() public {
        bytes32 commitmentId = _register(beneficiary);

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        (, , address storedFunder, uint256 reward, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(storedFunder, funder);
        assertEq(reward, REWARD);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));
        assertEq(address(escrow).balance, REWARD);
    }

    function test_refund_behaviour_is_unchanged() public {
        bytes32 commitmentId = _register(beneficiary);

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        vm.warp(block.timestamp + 2 days);
        uint256 funderBefore = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);

        assertEq(funder.balance, funderBefore + REWARD);
        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(reward, 0);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Refunded));
        assertEq(address(escrow).balance, 0);
    }

    function test_a_legitimate_signed_settlement_still_pays_the_beneficiary() public {
        bytes32 commitmentId = _register(beneficiary);

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        uint256 beneficiaryBefore = beneficiary.balance;
        _settle(commitmentId, 0);

        assertEq(beneficiary.balance, beneficiaryBefore + REWARD, "the beneficiary was not paid");
        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(reward, 0);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Paid));
    }

    function test_a_nonconform_settlement_still_does_not_pay_and_can_be_refunded() public {
        bytes32 commitmentId = _register(beneficiary);

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        uint256 beneficiaryBefore = beneficiary.balance;
        _settle(commitmentId, 1);

        assertEq(beneficiary.balance, beneficiaryBefore, "a nonconform verdict paid the beneficiary");

        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(address(escrow).balance, 0);
    }
}

/// @dev Reads the balance of an arbitrary address at run time. Solidity
///      constant-folds the literal ddress(0).balance to 0, so the balance of
///      the zero address can only be observed through a helper that receives
///      the address as a runtime value.
contract BalanceProbe {
    function balanceOf(address account) external view returns (uint256) {
        return account.balance;
    }
}