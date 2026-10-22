// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract TerraCycleEscrow is EIP712, ReentrancyGuard {
    using ECDSA for bytes32;

    enum CommitmentState {
        None,
        Registered,
        Funded,
        Paid,
        Negative,
        Refunded
    }

    struct Commitment {
        bytes32 commitmentId;
        bytes32 planHash;
        address beneficiary;
        address funder;
        uint256 reward;
        uint64 settleDeadline;
        CommitmentState state;
    }

    struct VerificationResult {
        bytes32 commitmentId;
        bytes32 planHash;
        bytes32 evidenceHash;
        uint8 verdict;
        uint64 validUntil;
    }

    bytes32 public immutable VERIFIER_TYPEHASH =
        keccak256("VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)");

    address public immutable verifier;

    /// @notice The only address allowed to register commitments.
    /// @dev This role is DELIBERATELY distinct from `verifier`. The verifier
    ///      attests to a verdict; the registrar allocates commitment ids.
    ///      Granting a commitment to a farmer is a farmer-side act, while
    ///      signing a verdict is an operator-side act. Keeping them separate
    ///      means a compromised verifier cannot create commitments, and a
    ///      compromised registrar cannot forge verdicts.
    address public immutable registrar;

    mapping(bytes32 => Commitment) public commitments;
    mapping(bytes32 => bool) public registeredId;

    uint8 private constant VERDICT_CONFORM = 0;
    uint8 private constant VERDICT_NONCONFORM = 1;

    event CommitmentRegistered(bytes32 indexed commitmentId, bytes32 indexed planHash, address beneficiary);
    event CommitmentFunded(bytes32 indexed commitmentId, address funder, uint256 reward);
    event CommitmentSettled(bytes32 indexed commitmentId, uint8 verdict);
    event CommitmentRefunded(bytes32 indexed commitmentId, address funder, uint256 amount);

    error VerifierZeroAddress();
    error RegistrarZeroAddress();
    error NotRegistrar();
    error CommitmentAlreadyRegistered();
    error InvalidPlanHash();
    error InvalidReward();
    error CommitmentNotFound();
    error AlreadyFunded();
    error NotFunded();
    error NotFunder();
    error NotBeneficiary();
    error InvalidVerdict();
    error AttestationExpired();
    error InvalidSignature();
    error PlanHashMismatch();
    error InvalidState();
    error TransferFailed();
    error DeadlineNotExpired();
    error ZeroBeneficiary();

    /**
     * @param verifier_   The address authorized to sign settlement attestations.
     * @param registrar_  The address authorized to register commitments.
     * @dev Both roles are immutable and both are set once, at deployment.
     */
    constructor(
        address verifier_,
        address registrar_,
        string memory name,
        string memory version
    ) EIP712(name, version) {
        if (verifier_ == address(0)) {
            revert VerifierZeroAddress();
        }
        if (registrar_ == address(0)) {
            revert RegistrarZeroAddress();
        }
        verifier = verifier_;
        registrar = registrar_;
    }

    function registerCommitment(
        bytes32 parcelId,
        bytes32 seasonId,
        bytes32 planHash,
        address beneficiary,
        uint64 settleDeadline
    ) external returns (bytes32 commitmentId) {
        // Authorization comes first. Without it ANY account could reserve a
        // commitment id: the id is keccak256(parcelId, seasonId) and does not
        // depend on the beneficiary, and `registeredId` is never cleared, so a
        // single unauthorized call could lock the legitimate farmer out of a
        // parcel and season permanently.
        if (msg.sender != registrar) {
            revert NotRegistrar();
        }
        if (registeredId[keccak256(abi.encode(parcelId, seasonId))]) {
            revert CommitmentAlreadyRegistered();
        }
        if (planHash == bytes32(0)) {
            revert InvalidPlanHash();
        }
        // The beneficiary is the payout destination. A zero address would make
        // `payable(address(0)).call{value: ...}` SUCCEED, so the escrowed
        // reward would leave the contract, be marked as paid and become
        // irrecoverable. The beneficiary can only be supplied here and there
        // is no setter, so this is the only boundary at which it can be
        // rejected.
        if (beneficiary == address(0)) {
            revert ZeroBeneficiary();
        }

        commitmentId = keccak256(abi.encode(parcelId, seasonId));

        commitments[commitmentId] = Commitment({
            commitmentId: commitmentId,
            planHash: planHash,
            beneficiary: beneficiary,
            funder: address(0),
            reward: 0,
            settleDeadline: settleDeadline,
            state: CommitmentState.Registered
        });

        registeredId[commitmentId] = true;

        emit CommitmentRegistered(commitmentId, planHash, beneficiary);
    }

    function fundCommitment(bytes32 commitmentId) external payable {
        Commitment storage c = commitments[commitmentId];

        if (c.state == CommitmentState.None) {
            revert CommitmentNotFound();
        }
        if (c.state != CommitmentState.Registered) {
            revert AlreadyFunded();
        }
        if (msg.value == 0) {
            revert InvalidReward();
        }

        c.funder = msg.sender;
        c.reward = msg.value;
        c.state = CommitmentState.Funded;

        emit CommitmentFunded(commitmentId, msg.sender, msg.value);
    }

    function settle(VerificationResult calldata attestation, bytes calldata signature)
        external
        nonReentrant
    {
        Commitment storage c = commitments[attestation.commitmentId];

        if (c.state == CommitmentState.None) {
            revert CommitmentNotFound();
        }
        if (c.state != CommitmentState.Funded) {
            revert InvalidState();
        }
        if (attestation.planHash != c.planHash) {
            revert PlanHashMismatch();
        }
        if (attestation.verdict > 2) {
            revert InvalidVerdict();
        }
        if (block.timestamp > attestation.validUntil) {
            revert AttestationExpired();
        }

        bytes32 digest = _hashTypedDataV4(
            keccak256(
                abi.encode(
                    VERIFIER_TYPEHASH,
                    attestation.commitmentId,
                    attestation.planHash,
                    attestation.evidenceHash,
                    attestation.verdict,
                    attestation.validUntil
                )
            )
        );

        address signer = ECDSA.recover(digest, signature);
        if (signer != verifier) {
            revert InvalidSignature();
        }

        c.state = (attestation.verdict == VERDICT_CONFORM)
            ? CommitmentState.Paid
            : CommitmentState.Negative;

        if (attestation.verdict == VERDICT_CONFORM) {
            _payBeneficiary(c);
        }

        emit CommitmentSettled(attestation.commitmentId, attestation.verdict);
    }

    function refund(bytes32 commitmentId) external nonReentrant {
        Commitment storage c = commitments[commitmentId];

        if (c.state == CommitmentState.None) {
            revert CommitmentNotFound();
        }
        if (msg.sender != c.funder) {
            revert NotFunder();
        }

        bool negative = c.state == CommitmentState.Negative;
        bool expired = c.state == CommitmentState.Funded && block.timestamp > c.settleDeadline;

        if (!negative && !expired) {
            revert InvalidState();
        }

        uint256 amount = c.reward;
        c.reward = 0;
        c.state = CommitmentState.Refunded;

        (bool ok, ) = payable(c.funder).call{value: amount}("");
        if (!ok) {
            revert TransferFailed();
        }

        emit CommitmentRefunded(commitmentId, c.funder, amount);
    }

    function getCommitment(bytes32 commitmentId)
        external
        view
        returns (bytes32 planHash, address beneficiary, address funder, uint256 reward, uint64 settleDeadline, CommitmentState state)
    {
        Commitment storage c = commitments[commitmentId];
        return (c.planHash, c.beneficiary, c.funder, c.reward, c.settleDeadline, c.state);
    }

    function _payBeneficiary(Commitment storage c) private {
        // Defence in depth. `registerCommitment` already rejects a zero
        // beneficiary, so this is unreachable today, but a transfer to the zero
        // address SUCCEEDS and would silently destroy the escrowed funds.
        // The payout boundary itself must never be able to burn ETH.
        if (c.beneficiary == address(0)) {
            revert ZeroBeneficiary();
        }

        uint256 amount = c.reward;
        c.reward = 0;

        (bool ok, ) = payable(c.beneficiary).call{value: amount}("");
        if (!ok) {
            revert TransferFailed();
        }
    }

    receive() external payable {
        revert();
    }
}
