// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/**
 * @title TerraCycleEscrowSecurityTest
 * @notice Focused security tests for the recovered TerraCycle escrow contract.
 *
 * @dev Scope of this file:
 *      - It does NOT redefine any business rule. Where the contract does not
 *        implement a property (for example "the reward amount agreed at
 *        registration time"), the gap is CHARACTERISED by a test whose name
 *        starts with `test_FINDING_` and carries a comment explaining the
 *        risk. Such a test asserts the CURRENT behaviour on purpose: it makes
 *        the finding executable so it cannot be silently forgotten or
 *        accidentally "fixed" without a decision.
 *      - Everything else asserts a security property the contract DOES
 *        implement today.
 *
 *      Nothing in this file moves funds outside the local test EVM.
 */
contract TerraCycleEscrowSecurityTest is Test {
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

    string public constant DOMAIN_NAME = "TerraCycleEscrow";
    string public constant DOMAIN_VERSION = "1";

    function setUp() public {
        verifier = vm.addr(VERIFIER_KEY);
        beneficiary = makeAddr("beneficiary");
        funder = makeAddr("funder");
        stranger = makeAddr("stranger");

        vm.deal(funder, 100 ether);

        escrow = new TerraCycleEscrow(verifier, beneficiary, DOMAIN_NAME, DOMAIN_VERSION);
    }

    // ---------------------------------------------------------------------
    // helpers
    // ---------------------------------------------------------------------

    /// @dev EIP-712 domain separator, derived independently of the contract.
    ///      This is exactly what ethers v6 `signTypedData` computes for the
    ///      domain `{name, version, chainId, verifyingContract}`.
    function _domainSeparator() internal view returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(DOMAIN_NAME)),
                keccak256(bytes(DOMAIN_VERSION)),
                block.chainid,
                address(escrow)
            )
        );
    }

    function _structHash(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        pure
        returns (bytes32)
    {
        return keccak256(
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
    }

    function _digest(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        view
        returns (bytes32)
    {
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), _structHash(commitmentId, planHash, evidenceHash, verdict, validUntil)));
    }

    function _sign(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        view
        returns (bytes memory)
    {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(VERIFIER_KEY, _digest(commitmentId, planHash, evidenceHash, verdict, validUntil));
        return abi.encodePacked(r, s, v);
    }

    function _register() internal returns (bytes32 commitmentId) {
        vm.prank(beneficiary);
        commitmentId = escrow.registerCommitment(PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days));
    }

    function _registerAndFund() internal returns (bytes32 commitmentId) {
        commitmentId = _register();
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function _attestation(bytes32 commitmentId, bytes32 planHash, bytes32 evidenceHash, uint8 verdict, uint64 validUntil)
        internal
        pure
        returns (TerraCycleEscrow.VerificationResult memory)
    {
        return TerraCycleEscrow.VerificationResult({
            commitmentId: commitmentId,
            planHash: planHash,
            evidenceHash: evidenceHash,
            verdict: verdict,
            validUntil: validUntil
        });
    }

    // =====================================================================
    // 1. Authorization
    // =====================================================================

    function test_settle_requires_a_signature_from_the_verifier() public {
        bytes32 commitmentId = _registerAndFund();

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xBEEF, _digest(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)));
        bytes memory wrongSignature = abi.encodePacked(r, s, v);

        vm.expectRevert(TerraCycleEscrow.InvalidSignature.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            wrongSignature
        );
    }

    function test_refund_can_only_be_called_by_the_funder() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.NotFunder.selector);
        escrow.refund(commitmentId);
    }

    function test_register_rejects_a_zero_plan_hash() public {
        vm.prank(beneficiary);
        vm.expectRevert(TerraCycleEscrow.InvalidPlanHash.selector);
        escrow.registerCommitment(PARCEL_ID, SEASON_ID, bytes32(0), beneficiary, uint64(block.timestamp + 1 days));
    }

    function test_register_rejects_a_duplicate_parcel_and_season() public {
        _register();
        // The duplicate check is reached by the AUTHORIZED registrar. An
        // unauthorized caller is rejected earlier, with NotRegistrar().
        vm.prank(beneficiary);
        vm.expectRevert(TerraCycleEscrow.CommitmentAlreadyRegistered.selector);
        escrow.registerCommitment(PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days));
    }

    /// @dev The caller of `settle` is not restricted: any account may submit a
    ///      validly signed attestation (relayer-friendly). Only the SIGNATURE
    ///      is authorized, not the submitter. This is intended behaviour and is
    ///      asserted here so a future change is deliberate.
    function test_any_relayer_may_submit_a_validly_signed_settlement() public {
        bytes32 commitmentId = _registerAndFund();
        uint256 before = beneficiary.balance;

        vm.prank(stranger);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );

        assertEq(beneficiary.balance, before + REWARD);
    }

    // =====================================================================
    // 2. Funding
    // =====================================================================

    function test_fund_rejects_zero_value() public {
        bytes32 commitmentId = _register();
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.InvalidReward.selector);
        escrow.fundCommitment(commitmentId);
    }

    function test_fund_rejects_an_unknown_commitment() public {
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.CommitmentNotFound.selector);
        escrow.fundCommitment{value: REWARD}(keccak256("nope"));
    }

    function test_fund_rejects_a_second_funding() public {
        bytes32 commitmentId = _registerAndFund();
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.AlreadyFunded.selector);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function test_fund_rejects_funding_after_settlement() public {
        bytes32 commitmentId = _registerAndFund();
        vm.prank(stranger);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );

        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.AlreadyFunded.selector);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function test_fund_rejects_funding_after_refund() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);
        vm.prank(funder);
        escrow.refund(commitmentId);

        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.AlreadyFunded.selector);
        escrow.fundCommitment{value: REWARD}(commitmentId);
    }

    function testFuzz_funded_amount_is_recorded_exactly(uint96 amount) public {
        amount = uint96(bound(amount, 1, 1e24));
        bytes32 commitmentId = _register();

        uint256 balanceBefore = address(escrow).balance;
        vm.deal(funder, amount);
        vm.prank(funder);
        escrow.fundCommitment{value: amount}(commitmentId);

        (, , , uint256 reward, , ) = escrow.getCommitment(commitmentId);
        assertEq(reward, amount);
        assertEq(address(escrow).balance, balanceBefore + amount);
    }

    /// @dev FINDING: the agreed reward amount is NOT bound on-chain.
    ///      `registerCommitment` takes no amount, so a funder may fund with
    ///      1 wei instead of the agreed `reward_wei` and the contract accepts
    ///      it silently. The backend's `chain_service._check_fund` performs an
    ///      OFF-CHAIN amount check, which is not a substitute: the commitment
    ///      itself carries no committed amount.
    ///      Impact: a malicious or buggy funder can settle a "conform"
    ///      commitment for a negligible amount, and the on-chain record cannot
    ///      distinguish it from the agreed reward.
    ///      Fix direction: add the expected reward to `registerCommitment` and
    ///      require `msg.value == reward` in `fundCommitment`. That is an ABI
    ///      and business-rule change and is deliberately NOT made here.
    function test_FINDING_reward_amount_is_not_bound_on_chain() public {
        bytes32 commitmentId = _register();

        vm.deal(funder, 1 ether);
        vm.prank(funder);
        escrow.fundCommitment{value: 1 wei}(commitmentId);

        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(reward, 1);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));
    }

    // =====================================================================
    // 3. Commitment id integrity
    // =====================================================================

    function test_commitment_id_is_keccak256_of_the_encoded_parcel_and_season() public {
        bytes32 commitmentId = _register();
        assertEq(commitmentId, keccak256(abi.encode(PARCEL_ID, SEASON_ID)));
    }

    function test_commitment_id_is_unique_per_parcel_and_season() public {
        bytes32 first = _register();

        vm.prank(beneficiary);
        bytes32 second = escrow.registerCommitment(
            bytes32(uint256(0x3333)), SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );

        assertTrue(first != second);
    }

    function test_a_commitment_id_cannot_be_reused_for_a_different_plan_hash() public {
        _register();
        vm.prank(beneficiary);
        vm.expectRevert(TerraCycleEscrow.CommitmentAlreadyRegistered.selector);
        escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, keccak256("another-plan"), beneficiary, uint64(block.timestamp + 1 days)
        );
    }

    // =====================================================================
    // 4. A signed verification is consumed at most once
    // =====================================================================

    function test_settle_can_only_be_consumed_once() public {
        bytes32 commitmentId = _registerAndFund();
        bytes memory signature = _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
        escrow.settle(_attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)), signature);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.settle(_attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)), signature);
    }

    function test_settle_is_rejected_after_a_refund() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);
        vm.prank(funder);
        escrow.refund(commitmentId);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );
    }

    // =====================================================================
    // 5. Replay protection
    // =====================================================================

    function test_a_signature_for_one_commitment_cannot_settle_another() public {
        bytes32 first = _registerAndFund();

        vm.prank(beneficiary);
        bytes32 second = escrow.registerCommitment(
            bytes32(uint256(0x3333)), SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(second);

        // The signature is over `first`, but the attestation claims `second`.
        bytes memory signature = _sign(first, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidSignature.selector);
        escrow.settle(_attestation(second, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)), signature);
    }

    function test_an_expired_attestation_is_rejected() public {
        bytes32 commitmentId = _registerAndFund();
        uint64 expired = uint64(block.timestamp - 1);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.AttestationExpired.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, expired),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, expired)
        );
    }

    function test_a_plan_hash_mismatch_is_rejected() public {
        bytes32 commitmentId = _registerAndFund();
        bytes32 tampered = keccak256("tampered");

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.PlanHashMismatch.selector);
        escrow.settle(
            _attestation(commitmentId, tampered, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, tampered, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );
    }

    /// @dev A malformed signature is rejected by OpenZeppelin v5 with its own
    ///      error, NOT with the contract's `InvalidSignature()`. The behaviour is
    ///      safe (the call reverts), but the error taxonomy is inconsistent with
    ///      the wrong-signer case. Recorded for TASK-004B.
    function test_a_malformed_signature_is_rejected() public {
        bytes32 commitmentId = _registerAndFund();

        vm.prank(stranger);
        vm.expectRevert();
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            hex"00"
        );
    }

    // =====================================================================
    // 6. No double withdrawal
    // =====================================================================

    function test_refund_can_only_be_executed_once() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);

        vm.prank(funder);
        escrow.refund(commitmentId);

        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.refund(commitmentId);
    }

    function test_settle_then_refund_is_rejected() public {
        bytes32 commitmentId = _registerAndFund();
        vm.prank(stranger);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );

        vm.warp(block.timestamp + 2 days);
        vm.prank(funder);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.refund(commitmentId);
    }

    function test_refund_then_settle_is_rejected() public {
        bytes32 commitmentId = _registerAndFund();
        vm.warp(block.timestamp + 2 days);
        vm.prank(funder);
        escrow.refund(commitmentId);

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidState.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );
    }

    function test_a_reentrant_funder_cannot_withdraw_twice() public {
        ReentrantFunder attacker = new ReentrantFunder(escrow);
        vm.deal(address(attacker), REWARD);

        // The AUTHORIZED registrar registers the commitment for the attacker.
        // The attacker is the beneficiary and the funder; it is not allowed to
        // register for itself.
        bytes32 commitmentId = _registerFor(address(attacker));
        attacker.fund(commitmentId);
        vm.warp(block.timestamp + 2 days);

        uint256 contractBalanceBefore = address(escrow).balance;
        uint256 attackerBalanceBefore = address(attacker).balance;

        attacker.claimRefund(commitmentId);

        // The attacker attempted to re-enter refund() during the payout.
        assertEq(attacker.attempts(), 1, "re-entrant refund attempt was not made");
        assertEq(address(escrow).balance, contractBalanceBefore - REWARD, "escrow released more than the reward");
        assertEq(address(attacker).balance, attackerBalanceBefore + REWARD, "attacker received the reward more than once");
    }

    // =====================================================================
    // 7. A failed ETH transfer cannot corrupt the accounting
    // =====================================================================

    function test_a_failing_beneficiary_transfer_preserves_the_accounting() public {
        RevertingReceiver receiver = new RevertingReceiver();
        bytes32 commitmentId = _registerFor(address(receiver));

        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(commitmentId);

        uint256 balanceBefore = address(escrow).balance;

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.TransferFailed.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );

        // Nothing moved and the commitment is still Funded and still owed.
        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));
        assertEq(reward, REWARD);
        assertEq(address(escrow).balance, balanceBefore);

        // And the funder can still recover the funds after the deadline.
        vm.warp(block.timestamp + 2 days);
        uint256 funderBefore = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(funder.balance, funderBefore + REWARD);
    }

    function test_a_failing_refund_transfer_preserves_the_accounting() public {
        RevertingReceiver receiver = new RevertingReceiver();
        bytes32 commitmentId = _registerFor(address(receiver));

        // The receiver is the funder, so the refund transfer will fail.
        vm.deal(address(receiver), 10 ether);
        vm.prank(address(receiver));
        escrow.fundCommitment{value: REWARD}(commitmentId);

        vm.warp(block.timestamp + 2 days);
        uint256 balanceBefore = address(escrow).balance;

        vm.prank(address(receiver));
        vm.expectRevert(TerraCycleEscrow.TransferFailed.selector);
        escrow.refund(commitmentId);

        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Funded));
        assertEq(reward, REWARD);
        assertEq(address(escrow).balance, balanceBefore);
    }

    // =====================================================================
    // 8. Inconclusive evidence must never authorize a payout
    // =====================================================================

    function test_inconclusive_verdict_does_not_pay_the_beneficiary() public {
        bytes32 commitmentId = _registerAndFund();
        uint256 beneficiaryBefore = beneficiary.balance;
        uint256 escrowBefore = address(escrow).balance;

        vm.prank(stranger);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 2, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 2, uint64(block.timestamp + 1 days))
        );

        assertEq(beneficiary.balance, beneficiaryBefore, "an inconclusive verdict paid the beneficiary");
        assertEq(address(escrow).balance, escrowBefore, "an inconclusive verdict released the funds");

        (, , , uint256 reward, , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(commitmentId);
        assertEq(uint8(state), uint8(TerraCycleEscrow.CommitmentState.Negative));
        assertEq(reward, REWARD, "the refundable amount was destroyed");

        // The funder recovers the money.
        uint256 funderBefore = funder.balance;
        vm.prank(funder);
        escrow.refund(commitmentId);
        assertEq(funder.balance, funderBefore + REWARD);
    }

    function test_nonconform_verdict_does_not_pay_the_beneficiary() public {
        bytes32 commitmentId = _registerAndFund();
        uint256 beneficiaryBefore = beneficiary.balance;

        vm.prank(stranger);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, 1, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, 1, uint64(block.timestamp + 1 days))
        );

        assertEq(beneficiary.balance, beneficiaryBefore);
    }

    function testFuzz_a_verdict_above_two_is_always_rejected(uint8 verdict) public {
        verdict = uint8(bound(verdict, 3, 255));
        bytes32 commitmentId = _registerAndFund();

        vm.prank(stranger);
        vm.expectRevert(TerraCycleEscrow.InvalidVerdict.selector);
        escrow.settle(
            _attestation(commitmentId, PLAN_HASH, EVIDENCE_HASH, verdict, uint64(block.timestamp + 1 days)),
            _sign(commitmentId, PLAN_HASH, EVIDENCE_HASH, verdict, uint64(block.timestamp + 1 days))
        );
    }

    // =====================================================================
    // 9. Contract balance and recorded liabilities stay consistent
    // =====================================================================

    function test_the_contract_rejects_plain_eth_transfers() public {
        vm.deal(stranger, 1 ether);
        vm.prank(stranger);
        (bool ok,) = address(escrow).call{value: 1 ether}("");
        assertFalse(ok, "the escrow accepted a stray ETH transfer");
        assertEq(address(escrow).balance, 0);
    }

    function test_the_balance_matches_the_sum_of_the_recorded_liabilities() public {
        bytes32 first = _registerAndFund();

        // A second, distinct commitment (different parcel and season).
        vm.prank(beneficiary);
        bytes32 second = escrow.registerCommitment(
            bytes32(uint256(0x3333)), SEASON_ID, PLAN_HASH, beneficiary, uint64(block.timestamp + 1 days)
        );
        vm.prank(funder);
        escrow.fundCommitment{value: REWARD}(second);

        (, , , uint256 rewardFirst, , ) = escrow.getCommitment(first);
        (, , , uint256 rewardSecond, , ) = escrow.getCommitment(second);
        assertEq(address(escrow).balance, rewardFirst + rewardSecond);

        vm.prank(stranger);
        escrow.settle(
            _attestation(first, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days)),
            _sign(first, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days))
        );

        (, , , uint256 rewardFirstAfter, , ) = escrow.getCommitment(first);
        (, , , uint256 rewardSecondAfter, , ) = escrow.getCommitment(second);
        assertEq(address(escrow).balance, rewardFirstAfter + rewardSecondAfter);
        assertEq(rewardFirstAfter, 0);
    }

    // =====================================================================
    // EIP-712 cross-checks (needed by TASK-004B: Solidity <-> Node signer)
    // =====================================================================

    function test_the_domain_separator_matches_the_contract_domain() public {
        (
            bytes1 fields,
            string memory name,
            string memory version,
            uint256 chainId,
            address verifyingContract,
            bytes32 salt,
            uint256[] memory extensions
        ) = escrow.eip712Domain();

        assertEq(uint8(fields), 0x0f, "unexpected EIP-712 domain fields");
        assertEq(name, DOMAIN_NAME);
        assertEq(version, DOMAIN_VERSION);
        assertEq(chainId, block.chainid);
        assertEq(verifyingContract, address(escrow));
        assertEq(salt, bytes32(0));
        assertEq(extensions.length, 0);

        bytes32 fromContract = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                chainId,
                verifyingContract
            )
        );
        assertEq(fromContract, _domainSeparator(), "the independently derived domain separator differs");
    }

    function test_the_digest_matches_openzeppelin_message_hash_utils() public {
        bytes32 commitmentId = _registerAndFund();
        bytes32 structHash = _structHash(commitmentId, PLAN_HASH, EVIDENCE_HASH, 0, uint64(block.timestamp + 1 days));

        bytes32 manual = keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
        bytes32 viaOpenZeppelin = MessageHashUtils.toTypedDataHash(_domainSeparator(), structHash);

        assertEq(manual, viaOpenZeppelin, "the manual digest differs from the OpenZeppelin digest");
    }

    // =====================================================================
    // helpers used above
    // =====================================================================

    function _registerFor(address beneficiary_) internal returns (bytes32 commitmentId) {
        // The registrar (the `beneficiary` account) registers the commitment
        // ON BEHALF of `beneficiary_`, which may be a contract.
        vm.prank(beneficiary);
        commitmentId = escrow.registerCommitment(
            PARCEL_ID, SEASON_ID, PLAN_HASH, beneficiary_, uint64(block.timestamp + 1 days)
        );
    }
}

/// @dev A contract that rejects every incoming ETH transfer.
contract RevertingReceiver {
    // No receive() and no fallback(): any plain transfer to this address reverts.
}

/// @dev A funder that re-enters `refund()` from its own `receive()` hook.
contract ReentrantFunder {
    TerraCycleEscrow public immutable escrow;
    uint256 public attempts;
    bytes32 public lastCommitmentId;

    constructor(TerraCycleEscrow escrow_) {
        escrow = escrow_;
    }

    /// @dev Funds a commitment that the authorized registrar created for this
    ///      contract. The attacker is the funder, not the registrar.
    function fund(bytes32 commitmentId) external {
        lastCommitmentId = commitmentId;
        escrow.fundCommitment{value: address(this).balance}(commitmentId);
    }

    function claimRefund(bytes32 commitmentId) external {
        lastCommitmentId = commitmentId;
        escrow.refund(commitmentId);
    }

    receive() external payable {
        if (attempts < 2) {
            attempts++;
            // Re-enter the contract while the refund payout is in flight.
            // The nonReentrant guard must block this.
            try escrow.refund(lastCommitmentId) {} catch {}
        }
    }
}
