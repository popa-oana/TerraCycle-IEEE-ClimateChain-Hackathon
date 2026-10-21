// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title TerraCycleEvidenceRegistry
 * @notice Append-only registry that records the canonical evidence hash and the
 *         verifier verdict of a TerraCycle commitment.
 *
 * @dev Scope, deliberately minimal:
 *      - The contract records only what an authorized verifier submits.
 *      - It does NOT verify satellite data, does NOT sign attestations,
 *        does NOT hold or transfer ETH, does NOT register farming plans and
 *        does NOT settle anything.
 *      - The canonical evidence hash is computed off-chain by the backend
 *        (SHA-256 over the canonical evidence document bytes). This contract
 *        stores that hash; it never recomputes or validates it.
 *
 *      A commitment id can be recorded exactly once. Evidence is immutable.
 */
contract TerraCycleEvidenceRegistry {
    // TerraCycle verdict codes (see Agent.md, "Verdict").
    uint8 public constant VERDICT_CONFORM = 0;
    uint8 public constant VERDICT_NONCONFORM = 1;
    uint8 public constant VERDICT_INCONCLUSIVE = 2;

    /// @notice The only address allowed to record evidence.
    address public immutable verifier;

    /// @notice A recorded evidence record.
    struct Evidence {
        bytes32 commitmentId;
        bytes32 evidenceHash;
        uint8 verdict;
        uint256 recordedAt;
        address recorder;
    }

    mapping(bytes32 => Evidence) private _evidence;

    /// @notice True when a commitment id already has evidence recorded.
    mapping(bytes32 => bool) public hasEvidence;

    /**
     * @notice Emitted whenever evidence is recorded for a commitment.
     * @param commitmentId The commitment the evidence belongs to.
     * @param evidenceHash SHA-256 hash of the canonical evidence document.
     * @param verdict TerraCycle verdict code: 0 conform, 1 nonconform, 2 inconclusive.
     * @param recorder The authorized verifier that submitted the evidence.
     * @param recordedAt Block timestamp of the recording, in Unix seconds.
     */
    event EvidenceRecorded(
        bytes32 indexed commitmentId,
        bytes32 indexed evidenceHash,
        uint8 indexed verdict,
        address recorder,
        uint256 recordedAt
    );

    error NotVerifier();
    error ZeroVerifierAddress();
    error ZeroCommitmentId();
    error ZeroEvidenceHash();
    error InvalidVerdict();
    error EvidenceAlreadyRecorded();

    /**
     * @param verifier_ The address authorized to record evidence. Cannot be zero.
     */
    constructor(address verifier_) {
        if (verifier_ == address(0)) {
            revert ZeroVerifierAddress();
        }
        verifier = verifier_;
    }

    /**
     * @notice Records the canonical evidence hash and verdict of a commitment.
     * @dev Callable only by the authorized verifier. Rejects the zero commitment
     *      id, the zero evidence hash, unknown verdict codes, and a commitment
     *      id that already carries evidence.
     * @param commitmentId The commitment the evidence belongs to. Cannot be zero.
     * @param evidenceHash SHA-256 hash of the canonical evidence document. Cannot be zero.
     * @param verdict TerraCycle verdict code: 0 conform, 1 nonconform, 2 inconclusive.
     */
    function recordEvidence(bytes32 commitmentId, bytes32 evidenceHash, uint8 verdict) external {
        if (msg.sender != verifier) {
            revert NotVerifier();
        }
        if (commitmentId == bytes32(0)) {
            revert ZeroCommitmentId();
        }
        if (evidenceHash == bytes32(0)) {
            revert ZeroEvidenceHash();
        }
        if (verdict > VERDICT_INCONCLUSIVE) {
            revert InvalidVerdict();
        }
        if (hasEvidence[commitmentId]) {
            revert EvidenceAlreadyRecorded();
        }

        uint256 recordedAt = block.timestamp;

        _evidence[commitmentId] = Evidence({
            commitmentId: commitmentId,
            evidenceHash: evidenceHash,
            verdict: verdict,
            recordedAt: recordedAt,
            recorder: msg.sender
        });
        hasEvidence[commitmentId] = true;

        emit EvidenceRecorded(commitmentId, evidenceHash, verdict, msg.sender, recordedAt);
    }

    /**
     * @notice Read-only retrieval of a recorded evidence record.
     * @dev Returns a zeroed record for an unknown commitment id; use
     *      `hasEvidence` to distinguish "not recorded" from a real record.
     * @param commitmentId The commitment to look up.
     */
    function getEvidence(bytes32 commitmentId) external view returns (Evidence memory) {
        return _evidence[commitmentId];
    }
}
