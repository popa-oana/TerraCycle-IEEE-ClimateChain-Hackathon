// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TerraCycleEvidenceRegistry} from "../src/TerraCycleEvidenceRegistry.sol";

/**
 * @title TerraCycleEvidenceRegistryTest
 * @notice Unit tests for the minimal TerraCycle evidence registry.
 *
 * The commitment id and the evidence hash used here are the genuine values
 * produced by the backend from the shared fixtures:
 *   - data/fixtures/demo.json                        -> reference_parcel.commitment_id
 *   - data/fixtures/canonical_evidence_snapshot.json -> SHA-256 of the
 *     canonical evidence document bytes.
 * No value in this file is invented.
 */
contract TerraCycleEvidenceRegistryTest is Test {
    TerraCycleEvidenceRegistry public registry;

    uint256 public constant VERIFIER_KEY = 0xA11CE;
    address public verifier;
    address public stranger;

    /// @dev keccak256(abi.encode(parcelIdBytes32, seasonIdBytes32)) for parcel_01 / season-2024.
    bytes32 public constant COMMITMENT_ID = 0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871;
    /// @dev SHA-256 over the canonical evidence document bytes.
    bytes32 public constant EVIDENCE_HASH = 0x89a43f3a2b84f44f4f8d12809d29a76c52769e62f05c759bc90c003ee3e9a16f;
    /// @dev The commitment id of the canonical evidence snapshot fixture.
    bytes32 public constant OTHER_COMMITMENT_ID = 0x8979bf59bbcd3c6b2ff84ee6c2306d649d2cb37a4e0c4ceeb06b72ca1387d834;

    // Local mirrors of the TerraCycle verdict codes. They are plain constants on
    // purpose: reading registry.VERDICT_*() would be an extra external call and
    // would consume the expectation set by vm.expectRevert.
    uint8 internal constant VERDICT_CONFORM = 0;
    uint8 internal constant VERDICT_NONCONFORM = 1;
    uint8 internal constant VERDICT_INCONCLUSIVE = 2;

    event EvidenceRecorded(
        bytes32 indexed commitmentId,
        bytes32 indexed evidenceHash,
        uint8 indexed verdict,
        address recorder,
        uint256 recordedAt
    );

    function setUp() public {
        verifier = vm.addr(VERIFIER_KEY);
        stranger = makeAddr("stranger");
        registry = new TerraCycleEvidenceRegistry(verifier);
    }

    function _record(bytes32 commitmentId, bytes32 evidenceHash, uint8 verdict) internal {
        vm.prank(verifier);
        registry.recordEvidence(commitmentId, evidenceHash, verdict);
    }

    // ---------------------------------------------------------------
    // 1. The authorized verifier can record valid evidence.
    // ---------------------------------------------------------------

    function test_verifier_can_record_valid_evidence() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);

        assertTrue(registry.hasEvidence(COMMITMENT_ID));
        assertEq(registry.verifier(), verifier);
    }

    // ---------------------------------------------------------------
    // 2. The stored values are retrieved correctly.
    // ---------------------------------------------------------------

    function test_stored_values_are_retrieved_correctly() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_NONCONFORM);

        TerraCycleEvidenceRegistry.Evidence memory stored = registry.getEvidence(COMMITMENT_ID);

        assertEq(stored.commitmentId, COMMITMENT_ID);
        assertEq(stored.evidenceHash, EVIDENCE_HASH);
        assertEq(stored.verdict, VERDICT_NONCONFORM);
        assertEq(stored.recorder, verifier);
        assertEq(stored.recordedAt, block.timestamp);
    }

    // ---------------------------------------------------------------
    // 3. An unauthorized caller cannot record evidence.
    // ---------------------------------------------------------------

    function test_unauthorized_caller_cannot_record_evidence() public {
        vm.prank(stranger);
        vm.expectRevert(TerraCycleEvidenceRegistry.NotVerifier.selector);
        registry.recordEvidence(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);

        assertFalse(registry.hasEvidence(COMMITMENT_ID));
    }

    function test_deployer_cannot_record_evidence_without_being_the_verifier() public {
        // The deployer is not the verifier, so it has no special rights.
        vm.prank(address(this));
        vm.expectRevert(TerraCycleEvidenceRegistry.NotVerifier.selector);
        registry.recordEvidence(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);
    }

    // ---------------------------------------------------------------
    // 4. The same commitment id cannot be recorded twice.
    // ---------------------------------------------------------------

    function test_duplicate_commitment_id_is_rejected() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);

        vm.prank(verifier);
        vm.expectRevert(TerraCycleEvidenceRegistry.EvidenceAlreadyRecorded.selector);
        registry.recordEvidence(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_NONCONFORM);

        // The first record must be untouched.
        TerraCycleEvidenceRegistry.Evidence memory stored = registry.getEvidence(COMMITMENT_ID);
        assertEq(stored.evidenceHash, EVIDENCE_HASH);
        assertEq(stored.verdict, VERDICT_CONFORM);
    }

    // ---------------------------------------------------------------
    // 5. A zero commitment id is rejected.
    // ---------------------------------------------------------------

    function test_zero_commitment_id_is_rejected() public {
        vm.prank(verifier);
        vm.expectRevert(TerraCycleEvidenceRegistry.ZeroCommitmentId.selector);
        registry.recordEvidence(bytes32(0), EVIDENCE_HASH, VERDICT_CONFORM);
    }

    // ---------------------------------------------------------------
    // 6. A zero evidence hash is rejected.
    // ---------------------------------------------------------------

    function test_zero_evidence_hash_is_rejected() public {
        vm.prank(verifier);
        vm.expectRevert(TerraCycleEvidenceRegistry.ZeroEvidenceHash.selector);
        registry.recordEvidence(COMMITMENT_ID, bytes32(0), VERDICT_CONFORM);
    }

    // ---------------------------------------------------------------
    // 7. An invalid verdict is rejected.
    // ---------------------------------------------------------------

    function test_invalid_verdict_is_rejected() public {
        vm.prank(verifier);
        vm.expectRevert(TerraCycleEvidenceRegistry.InvalidVerdict.selector);
        registry.recordEvidence(COMMITMENT_ID, EVIDENCE_HASH, 3);

        vm.prank(verifier);
        vm.expectRevert(TerraCycleEvidenceRegistry.InvalidVerdict.selector);
        registry.recordEvidence(COMMITMENT_ID, EVIDENCE_HASH, 255);

        assertFalse(registry.hasEvidence(COMMITMENT_ID));
    }

    // ---------------------------------------------------------------
    // 8. The correct event is emitted.
    // ---------------------------------------------------------------

    function test_event_is_emitted_on_recording() public {
        vm.expectEmit(true, true, true, true);
        emit EvidenceRecorded(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM, verifier, block.timestamp);

        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);
    }

    // ---------------------------------------------------------------
    // 9. Conform and inconclusive verdicts can be recorded.
    // ---------------------------------------------------------------

    function test_conform_and_inconclusive_verdicts_can_be_recorded() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);
        _record(OTHER_COMMITMENT_ID, EVIDENCE_HASH, VERDICT_INCONCLUSIVE);

        assertEq(registry.getEvidence(COMMITMENT_ID).verdict, VERDICT_CONFORM);
        assertEq(registry.getEvidence(OTHER_COMMITMENT_ID).verdict, VERDICT_INCONCLUSIVE);
        assertTrue(registry.hasEvidence(COMMITMENT_ID));
        assertTrue(registry.hasEvidence(OTHER_COMMITMENT_ID));
    }

    function test_contract_exposes_the_terra_cycle_verdict_codes() public view {
        assertEq(registry.VERDICT_CONFORM(), 0);
        assertEq(registry.VERDICT_NONCONFORM(), 1);
        assertEq(registry.VERDICT_INCONCLUSIVE(), 2);
    }

    function test_all_three_terra_cycle_verdict_codes_are_accepted() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);
        _record(OTHER_COMMITMENT_ID, EVIDENCE_HASH, VERDICT_NONCONFORM);

        assertEq(registry.getEvidence(COMMITMENT_ID).verdict, VERDICT_CONFORM);
        assertEq(registry.getEvidence(OTHER_COMMITMENT_ID).verdict, VERDICT_NONCONFORM);
    }

    // ---------------------------------------------------------------
    // 10. Read-only retrieval does not modify state.
    // ---------------------------------------------------------------

    function test_read_only_retrieval_does_not_modify_state() public {
        _record(COMMITMENT_ID, EVIDENCE_HASH, VERDICT_CONFORM);

        TerraCycleEvidenceRegistry.Evidence memory first = registry.getEvidence(COMMITMENT_ID);
        TerraCycleEvidenceRegistry.Evidence memory second = registry.getEvidence(COMMITMENT_ID);

        assertEq(first.commitmentId, second.commitmentId);
        assertEq(first.evidenceHash, second.evidenceHash);
        assertEq(first.verdict, second.verdict);
        assertEq(first.recordedAt, second.recordedAt);
        assertEq(first.recorder, second.recorder);

        // Reading an unknown commitment id must not create anything.
        bytes32 unknownId = bytes32(uint256(0xdead));
        TerraCycleEvidenceRegistry.Evidence memory missing = registry.getEvidence(unknownId);
        assertEq(missing.commitmentId, bytes32(0));
        assertEq(missing.evidenceHash, bytes32(0));
        assertFalse(registry.hasEvidence(unknownId));
    }

    // ---------------------------------------------------------------
    // Constructor and deployment guards.
    // ---------------------------------------------------------------

    function test_constructor_rejects_zero_verifier_address() public {
        vm.expectRevert(TerraCycleEvidenceRegistry.ZeroVerifierAddress.selector);
        new TerraCycleEvidenceRegistry(address(0));
    }

    function test_contract_cannot_receive_eth() public {
        // No payable function exists, so the registry cannot receive ETH.
        (bool success,) = address(registry).call{value: 1 wei}("");
        assertFalse(success);
        assertEq(address(registry).balance, 0);
    }
}
