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

    mapping(bytes32 => Commitment) public commitments;
    mapping(bytes32 => bool) public registeredId;

    uint8 private constant VERDICT_CONFORM = 0;
    uint8 private constant VERDICT_NONCONFORM = 1;

    event CommitmentRegistered(bytes32 indexed commitmentId, bytes32 indexed planHash, address beneficiary);
    event CommitmentFunded(bytes32 indexed commitmentId, address funder, uint256 reward);
    event CommitmentSettled(bytes32 indexed commitmentId, uint8 verdict);
    event CommitmentRefunded(bytes32 indexed commitmentId, address funder, uint256 amount);

    error VerifierZeroAddress();
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

    constructor(address verifier_, string memory name, string memory version)
        EIP712(name, version)
    {
        if (verifier_ == address(0)) {
            revert VerifierZeroAddress();
        }
        verifier = verifier_;
    }

    function registerCommitment(
        bytes32 parcelId,
        bytes32 seasonId,
        bytes32 planHash,
        address beneficiary,
        uint64 settleDeadline
    ) external returns (bytes32 commitmentId) {
        if (registeredId[keccak256(abi.encode(parcelId, seasonId))]) {
            revert CommitmentAlreadyRegistered();
        }
        if (planHash == bytes32(0)) {
            revert InvalidPlanHash();
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
