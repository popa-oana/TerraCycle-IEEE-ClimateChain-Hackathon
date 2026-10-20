// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract TerraCycleEscrowTest is Test {
    TerraCycleEscrow public escrow;

    uint256 public constant VERIFIER_KEY = 0xA11CE;
    address public verifier;
    address public beneficiary;
    address public funder;
    address public stranger;

    bytes32 public constant PARCEL_ID = bytes32(uint256(0x1111));
    bytes32 public constant SEASON_ID = bytes32(uint256(0x2222));
    bytes32 public constant PLAN_HASH = keccak256("plan-document");
    bytes32 public constant EVIDENCE_HASH = keccak256("evidence-document");
    uint256 public constant REWARD = 1 ether;

    function setUp() public {
        verifier = vm.addr(VERIFIER_KEY);
        beneficiary = makeAddr("beneficiary");
        funder = makeAddr("funder");
        stranger = makeAddr("stranger");

        escrow = new TerraCycleEscrow(verifier, "TerraCycleEscrow", "1");
    }

    function _register() internal returns (bytes32 commitmentId) {
        vm.prank(beneficiary);
        commitmentId = escrow.registerCommitment(PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days));
        return commitmentId;
    }

    function _registerAndFund() internal returns (bytes32 commitmentId) {
        commitmentId = _register();
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function _sign(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        view
        returns (bytes memory)
    {
        bytes32 domainSeparator = escrow.domainSeparatorV4();
        bytes32 typehash = keccak256(
            "VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)"
        );
        bytes32 structHash = keccak256(abi.encode(typehash, commitmentId, planHash, evidenceHash, verdict, validUntil));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(VERIFIER_KEY, digest);
        return abi.encodePacked(r, s, v);
    }

    function test_register_success() public {
        bytes32 commitmentId = _register();
        (bytes32 planHash, address ben, , , , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(planHash, PLAN_HASH);
        assertEq(ben, beneficiary);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Registered));
    }

    function test_register_duplicate_reverts() public {
        _register();
        vm.prank(beneficiary);
        vm.expectRevert(TerraCycleEscrow.CommitmentAlreadyRegistered.selector);
        escrow.registerCommitment(PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days));
    }

    function test_register_zero_plan_hash_reverts() public {
        vm.prank(beneficiary);
        vm.expectRevert(TerraCycleEscrow.InvalidPlanHash.selector);
        escrow.registerCommitment(PARCEL_ID, SEASON_ID, bytes32(0), beneficiary, uint64(block.timestamp + 1 days));
    }

    function test_fund_success() public {
        bytes32 commitmentId = _register();
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        (, , address fnd, uint256 rewardAmount, , TerraCycleEscrow.CommitmentState state) =
            escrow.getCommitment(commitmentId);
        assertEq(fnd, funder);
        assertEq(rewardAmount, REWARD);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));
    }

    function test_fund_zero_reverts() public {
        bytes32 commitmentId = _register();
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.InvalidReward.selector);
        escrow.fundCommitment(commitmentId);
    }

    function test_fund_double_reverts() public {
        bytes32 commitmentId = _registerAndFund();
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.AlreadyFunded.selector);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function test_settle_conform_pays_beneficiary() public {
        bytes32 commitmentId = _registerAndFund();
        uint256 before = beneficiary.balance;

        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
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

        assertEq(beneficiary.balance, before + REWARD);
        (bytes32 planHash, address beneficiary, address funder, uint256 rewardAmount, uint64 settleDeadline, CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(rewardAmount, 0);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Paid));
    }

    function test_settle_nonconform_moves_to_negative() public {
        bytes32 commitmentId = _registerAndFund();

        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 1, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: 1,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            signature
        );

        (bytes32 planHash, address beneficiary, address funder, uint256 rewardAmount, uint64 settleDeadline, CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Negative));
    }

    function test_settle_wrong_signer_reverts() public {
        bytes32 commitmentId = _registerAndFund();

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xBEEF, bytes32(uint256(0xdead)));
        bytes memory badSignature = abi.encodePacked(r, s, v);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidSignature.selector);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: 0,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            badSignature
        );
    }

    function test_settle_plan_hash_mismatch_reverts() public {
        bytes32 commitmentId = _registerAndFund();

        bytes memory signature = _sign(commitmentId, keccak256("tampered"), EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.PlanHashMismatch.selector);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: keccak256("tampered"),
                evidenceHash: EVIDENCE_HASH,
                verdict: 0,
                validUntil: uint64(block.timestamp + 1 days)
            }),
            signature
        );
    }

    function test_settle_expired_attestation_reverts() public {
        bytes32 commitmentId = _registerAndFund();

        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp - 1));

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.AttestationExpired.selector);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: commitmentId,
                planHash: PLAN_HASH,
                evidenceHash: EVIDENCE_HASH,
                verdict: 0,
                validUntil: uint64(block.timestamp - 1)
            }),
            signature
        );
    }

    function test_settle_twice_reverts() public {
        bytes32 commitmentId = _registerAndFund();
        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({commitmentId: commitmentId, planHash: PLAN_HASH, evidenceHash: EVIDENCE_HASH, verdict: 0, validUntil: uint64(block.timestamp + 1 days)}),
            signature
        );

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({commitmentId: commitmentId, planHash: PLAN_HASH, evidenceHash: EVIDENCE_HASH, verdict: 0, validUntil: uint64(block.timestamp + 1 days)}),
            signature
        );
    }

    function test_refund_after_negative() public {
        bytes32 commitmentId = _registerAndFund();

        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 2, uint64(block.timestamp + 1 days));
        vm.prank(stranger);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({commitmentId: commitmentId, planHash: PLAN_HASH, evidenceHash: EVIDENCE_HASH, verdict: 2, validUntil: uint64(block.timestamp + 1 days)}),
            signature
        );

        uint256 before = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(funder.balance, before + REWARD);

        (bytes32 , , , uint256 rewardAmount, , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(rewardAmount, 0);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Refunded));
    }

    function test_refund_after_deadline() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);

        uint256 before = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(funder.balance, before + REWARD);
    }

    function test_refund_by_stranger_reverts() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.NotFunder.selector);
        escrow.refund(commitmentId);
    }

    function test_refund_twice_reverts() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);

        vm.prank(funder);
        escrow.refund(commitmentId);

        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.refund(commitmentId);
    }
}
