// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";

/**
 * @title TerraCycleEscrowRegistrationAuthTest
 * @notice TASK-004B.2B - commitment registration authorization.
 *
 * @dev The vulnerability: `registerCommitment` had NO `msg.sender` condition,
 *      so ANY account could create a commitment for any `(parcel, season)`
 *      pair. Because the commitment id is `keccak256(abi.encode(parcelId,
 *      seasonId))` and does NOT depend on the beneficiary, an unauthorized
 *      account could RESERVE a commitment id permanently and lock the
 *      legitimate farmer out for that parcel and season
 *      (`registeredId` is never cleared).
 *
 *      The documented architecture (`TerraCycle_Ghid_Integrare.md` and
 *      `docs/api-contract.md`) names the actor for a registration as the
 *      "farmer", and the `/transactions` endpoint is specified to verify
 *      "actors". The transition table, however, gives `refund` an explicit
 *      `msg.sender == funder` rule and gives `registerCommitment` none.
 *      That missing rule is the gap this task closes.
 *
 *      The registrar is a role of its own, DISTINCT from the EIP-712 verifier.
 */
contract TerraCycleEscrowRegistrationAuthTest is Test {
    TerraCycleEscrow public escrow;

    uint256 public constant REGISTRAR_KEY = 0xB0B;

    address public verifier;
    address public registrar;
    address public stranger;
    address public beneficiary;
    address public funder;

    bytes32 public constant PARCEL_ID = bytes32(uint256(0x1111));
    bytes32 public constant SEASON_ID = bytes32(uint256(0x2222));
    bytes32 public constant PLAN_HASH = keccak256("plan-document");
    bytes32 public constant EVIDENCE_HASH = keccak256("evidence-document");
    uint256 public constant REWARD = 1 ether;

    string public constant DOMAIN_NAME = "TerraCycleEscrow";
    string public constant DOMAIN_VERSION = "1";

    /// @dev Computed locally so the expectation compiles against the contract
    ///      both before and after the fix.
    bytes4 internal constant NOT_REGISTRAR_SELECTOR = bytes4(keccak256("NotRegistrar()"));

    function setUp() public {
        verifier = vm.addr(0xA11CE);
        registrar = vm.addr(REGISTRAR_KEY);
        stranger = makeAddr("stranger");
        beneficiary = makeAddr("beneficiary");
        funder = makeAddr("funder");

        vm.deal(funder, 100 ether);
        vm.deal(registrar, 100 ether);

        escrow = _deploy(verifier, registrar);
    }

    /// @dev The single place that knows the constructor signature.
    function _deploy(address verifier_, address registrar_) internal returns (TerraCycleEscrow) {
        return new TerraCycleEscrow(verifier_, registrar_, DOMAIN_NAME, DOMAIN_VERSION);
    }

    function _registerAs(address caller) internal returns (bytes32 commitmentId) {
        vm.prank(caller);
        commitmentId = escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    function _sign(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        view
        returns (bytes memory)
    {
        return _signWith(0xA11CE, commitmentId, planHash, evidenceHash, verdict, validUntil);
    }

    function _signWith(
        uint256 key,
        bytes32 commitmentId,
        bytes32 planHash,
        bytes32 evidenceHash,
        uint8 verdict,
        uint64 validUntil
    )
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
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    // =====================================================================
    // 1. THE REGRESSION TEST
    //
    //    Against the vulnerable contract this FAILS: the registration
    //    succeeds, so the expected revert never happens.
    // =====================================================================

    function test_an_unauthorized_account_cannot_register() public {
        vm.prank(stranger);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    /// @dev The squat: an unauthorized account tries to reserve the commitment
    ///      id of the intended commitment. It must fail, so the id stays
    ///      available for the authorized registrar.
    function test_an_unauthorized_account_cannot_squat_a_commitment_id() public {
        vm.prank(stranger);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );

        // The intended commitment is still registrable by the registrar.
        bytes32 commitmentId = _registerAs(registrar);
        assertEq(commitmentId, keccak256(abi.encode(PARCEL_ID, SEASON_ID)));
        assertTrue(escrow.registeredId(commitmentId));
    }

    // =====================================================================
    // 2. THE AUTHORIZED PATH
    // =====================================================================

    function test_the_authorized_registrar_can_register() public {
        bytes32 commitmentId = _registerAs(registrar);

        assertEq(commitmentId, keccak256(abi.encode(PARCEL_ID, SEASON_ID)));
        assertTrue(escrow.registeredId(commitmentId));

        (, address storedBeneficiary, address storedFunder, uint256 reward, uint64 deadline, TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(storedBeneficiary, beneficiary);
        assertEq(storedFunder, address(0));
        assertEq(reward, 0);
        assertEq(deadline, uint64(block.timestamp + 1 days));
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Registered));
    }

    function test_an_authorized_registration_preserves_the_original_commitment_data() public {
        bytes32 commitmentId = _registerAs(registrar);

        (bytes32 planHash, address storedBeneficiary, , , uint64 deadline, ) =
            escrow.getCommitment(commitmentId);
        assertEq(planHash, PLAN_HASH, "the plan hash changed");
        assertEq(storedBeneficiary, beneficiary, "the beneficiary changed");
        assertEq(deadline, uint64(block.timestamp + 1 days), "the deadline changed");
        assertEq(commitmentId, keccak256(abi.encode(PARCEL_ID, SEASON_ID)), "the id format changed");
    }

    function test_a_duplicate_registration_is_still_rejected() public {
        _registerAs(registrar);

        vm.prank(registrar);
        vm.expectRevert(TerraCycleEscrow.CommitmentAlreadyRegistered.selector);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    // =====================================================================
    // 3. THE FAILURE MODE IS CLEAN
    // =====================================================================

    function test_repeated_unauthorized_attempts_all_fail() public {
        for (uint256 i = 0; i < 5; i++) {
            vm.prank(stranger);
            vm.expectRevert(NOT_REGISTRAR_SELECTOR);
            escrow.registerCommitment(
                PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
            );
        }
        assertFalse(escrow.registeredId(keccak256(abi.encode(PARCEL_ID, SEASON_ID))));
    }

    function test_an_unauthorized_registration_leaves_storage_unchanged() public {
        bytes32 expectedId = keccak256(abi.encode(PARCEL_ID, SEASON_ID));

        (, address beforeBeneficiary, , , , TerraCycleEscrow.CommitmentState stateBefore) =
            escrow.getCommitment(expectedId);
        uint256 escrowBalanceBefore = address(escrow).balance;

        vm.prank(stranger);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );

        (, address afterBeneficiary, , , , TerraCycleEscrow.CommitmentState stateAfter) =
            escrow.getCommitment(expectedId);
        assertEq(afterBeneficiary, beforeBeneficiary, "the stored beneficiary changed");
        assertEq(uint8(stateAfter), uint8(stateBefore), "the commitment state changed");
        assertFalse(escrow.registeredId(expectedId), "the commitment id was reserved");
        assertEq(address(escrow).balance, escrowBalanceBefore, "the escrow balance changed");
    }

    function test_an_unauthorized_registration_emits_no_event() public {
        vm.recordLogs();

        vm.prank(stranger);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );

        assertEq(vm.getRecordedLogs().length, 0, "an unauthorized registration emitted an event");
    }

    function test_an_authorized_registration_emits_exactly_one_event() public {
        vm.recordLogs();
        _registerAs(registrar);

        Vm.Log[] memory logs = vm.getRecordedLogs();
        assertEq(logs.length, 1, "the authorized registration must emit exactly one event");
        assertEq(logs[0].topics[0], keccak256("CommitmentRegistered(bytes32,bytes32,address)"));
        assertEq(logs[0].topics[1], bytes32(keccak256(abi.encode(PARCEL_ID, SEASON_ID))));
    }

    // =====================================================================
    // 4. THE TWO ROLES ARE DISTINCT
    // =====================================================================

    /// @dev The registrar is NOT the settlement authority.
    function test_the_registrar_cannot_settle() public {
        bytes32 commitmentId = _registerAs(registrar);
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        // Signed with the REGISTRAR's own key: registration authority must not
        // imply settlement authority.
        bytes memory signature = _signWith(REGISTRAR_KEY, commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        // The registrar is not the verifier, so its signature is not accepted.
        vm.prank(registrar);
        vm.expectRevert(TerraCycleEscrow.InvalidSignature.selector);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: 0,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            signature
        );
    }

    /// @dev The EIP-712 verifier is NOT the registrar.
    function test_the_verifier_cannot_register() public {
        vm.prank(verifier);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    /// @dev The beneficiary and the funder are not registrars either.
    function test_neither_the_beneficiary_nor_the_funder_can_register() public {
        vm.prank(beneficiary);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );

        vm.prank(funder);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    // =====================================================================
    // 5. THE EXISTING BEHAVIOUR IS UNCHANGED
    // =====================================================================

    function test_the_zero_beneficiary_protection_still_applies_to_the_registrar() public {
        vm.prank(registrar);
        vm.expectRevert(TerraCycleEscrow.ZeroBeneficiary.selector);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, address(0), uint64(block.timestamp + 1 days)
        );
    }

    function test_funding_and_refund_still_work_after_an_authorized_registration() public {
        bytes32 commitmentId = _registerAs(registrar);

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        (, , address storedFunder, uint256 reward, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(storedFunder, funder);
        assertEq(reward, REWARD);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));

        vm.warp(block.timestamp + 2 days);
        uint256 funderBefore = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(funder.balance, funderBefore + REWARD);
    }

    function test_eip712_settlement_still_works_after_an_authorized_registration() public {
        bytes32 commitmentId = _registerAs(registrar);
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        uint256 beneficiaryBefore = beneficiary.balance;
        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: 0,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            signature
        );

        assertEq(beneficiary.balance, beneficiaryBefore + REWARD);
        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(reward, 0);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Paid));
    }

    // =====================================================================
    // 6. FUZZING
    // =====================================================================

    /// @dev No caller other than the registrar may ever register, whatever the
    ///      address, the parcel, the season or the plan hash.
    function testFuzz_only_the_registrar_can_register(
        address caller,
        bytes32 parcelId,
        bytes32 seasonId,
        bytes32 planHash
    ) public {
        vm.assume(caller != registrar);
        vm.assume(planHash != bytes32(0));
        vm.assume(caller != address(escrow));

        vm.prank(caller);
        vm.expectRevert(NOT_REGISTRAR_SELECTOR);
        escrow.registerCommitment(
            parcelId, seasonId, planHash, beneficiary, uint64(block.timestamp + 1 days)
        );

        assertFalse(escrow.registeredId(keccak256(abi.encode(parcelId, seasonId))));
    }
}
