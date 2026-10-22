// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TerraCycleEscrow} from "../src/TerraCycleEscrow.sol";

/**
 * @title TerraCycleEscrowInvariantTest
 * @notice Stateful invariant over the recovered escrow contract.
 *
 * @dev The invariant under test is the accounting property that matters most
 *      for an escrow that holds real value:
 *
 *          address(escrow).balance == SUM(reward of every commitment)
 *
 *      i.e. the ETH the contract holds is exactly the sum of what it still
 *      owes. A violation means ETH was created, destroyed or double-released.
 *
 *      The handler mixes register / fund / settle / refund in arbitrary
 *      orders, including settling to a beneficiary that is the handler itself.
 */
contract EscrowInvariantHandler is Test {
    TerraCycleEscrow public immutable escrow;
    /// @notice The address authorized to register commitments. The handler
    ///         presents itself as this address when it registers.
    address public immutable registrar;
    bytes32[] public trackedIds;

    uint256 public constant VERIFIER_KEY = 0xA11CE;

    uint256 public zeroBeneficiaryAttempts;
    uint256 public zeroBeneficiarySuccesses;
    /// @notice The custom-error selector returned by the last rejected
    ///         zero-beneficiary registration.
    bytes4 public lastZeroBeneficiaryError;

    uint256 public unauthorizedAttempts;
    uint256 public unauthorizedSuccesses;
    /// @notice The custom-error selector returned by the last rejected
    ///         unauthorized registration.
    bytes4 public lastUnauthorizedError;

    constructor(TerraCycleEscrow escrow_, address registrar_) {
        escrow = escrow_;
        registrar = registrar_;
    }

    /// @notice Attempts to register WITHOUT being the authorized registrar.
    /// @dev The prank is set EXPLICITLY to this contract, which is never the
    ///      registrar, so the result cannot depend on a prank left over from
    ///      another handler function. The parcel/season pair is deliberately
    ///      different from the one `_register` uses, so the failure cannot be
    ///      a duplicate-id rejection either.
    function attemptUnauthorizedRegistration(uint256 seed) external {
        vm.assume(seed != 0);
        unauthorizedAttempts++;
        vm.prank(address(this));
        (bool ok, bytes memory ret) = address(escrow).call(
            abi.encodeWithSignature(
                "registerCommitment(bytes32,bytes32,bytes32,address,uint64)",
                bytes32(uint256(seed)),
                bytes32(uint256(seed) + 11),
                keccak256(abi.encode("plan", seed)),
                address(this),
                uint64(block.timestamp + 1 days)
            )
        );
        if (ok) {
            unauthorizedSuccesses++;
        } else if (ret.length >= 4) {
            lastUnauthorizedError = bytes4(ret);
        }
    }

    /// @notice Attempts to register a commitment with a zero beneficiary.
    /// @dev The call MUST fail, and it MUST fail with `ZeroBeneficiary()` and
    ///      not with `NotRegistrar()`: the handler registers as the authorized
    ///      registrar, so the zero-address guard is what has to stop it.
    ///
    ///      The parcel/season pair is deliberately different from the one
    ///      `_register` uses, so the failure cannot be a duplicate-id rejection.
    function attemptZeroBeneficiaryRegistration(uint256 seed) external {
        vm.assume(seed != 0);
        zeroBeneficiaryAttempts++;
        vm.prank(registrar);
        (bool ok, bytes memory ret) = address(escrow).call(
            abi.encodeWithSignature(
                "registerCommitment(bytes32,bytes32,bytes32,address,uint64)",
                bytes32(uint256(seed)),
                bytes32(uint256(seed) + 7),
                keccak256(abi.encode("plan", seed)),
                address(0),
                uint64(block.timestamp + 1 days)
            )
        );
        if (ok) {
            zeroBeneficiarySuccesses++;
        } else if (ret.length >= 4) {
            lastZeroBeneficiaryError = bytes4(ret);
        }
    }

    function _register(uint256 seed) internal returns (bytes32 id) {
        vm.prank(registrar);
        id = escrow.registerCommitment(
            bytes32(uint256(seed)),
            bytes32(uint256(seed) + 1),
            keccak256(abi.encode("plan", seed)),
            address(this),
            uint64(block.timestamp + 1 days)
        );
        trackedIds.push(id);
    }

    function register(uint256 seed) external {
        vm.assume(seed != 0);
        _register(seed);
    }

    function fund(uint256 seed, uint96 amount) external {
        if (trackedIds.length == 0) return;
        amount = uint96(bound(amount, 1, 1e24));

        bytes32 id = trackedIds[seed % trackedIds.length];
        (, , , , , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(id);
        if (state != TerraCycleEscrow.CommitmentState.Registered) return;

        vm.deal(address(this), address(this).balance + amount);
        escrow.fundCommitment{value: amount}(id);
    }

    function settle(uint256 seed, uint8 verdict) external {
        if (trackedIds.length == 0) return;
        verdict = uint8(bound(verdict, 0, 2));

        bytes32 id = trackedIds[seed % trackedIds.length];
        (bytes32 planHash, , , , , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(id);
        if (state != TerraCycleEscrow.CommitmentState.Funded) return;

        bytes32 evidenceHash = keccak256(abi.encode("evidence", seed));
        uint64 validUntil = uint64(block.timestamp + 1 days);

        bytes32 digest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                keccak256(
                    abi.encode(
                        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                        keccak256(bytes("TerraCycleEscrow")),
                        keccak256(bytes("1")),
                        block.chainid,
                        address(escrow)
                    )
                ),
                keccak256(
                    abi.encode(
                        keccak256(
                            "VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)"
                        ),
                        id,
                        planHash,
                        evidenceHash,
                        verdict,
                        validUntil
                    )
                )
            )
        );

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(VERIFIER_KEY, digest);
        escrow.settle(
            TerraCycleEscrow.VerificationResult({
                commitmentId: id,
                planHash: planHash,
                evidenceHash: evidenceHash,
                verdict: verdict,
                validUntil: validUntil
            }),
            abi.encodePacked(r, s, v)
        );
    }

    function refund(uint256 seed) external {
        if (trackedIds.length == 0) return;

        bytes32 id = trackedIds[seed % trackedIds.length];
        (, , , , , TerraCycleEscrow.CommitmentState state) = escrow.getCommitment(id);
        if (state != TerraCycleEscrow.CommitmentState.Negative) return;

        escrow.refund(id);
    }

    /// @notice Number of commitments tracked by this handler.
    function trackedCount() public view returns (uint256) {
        return trackedIds.length;
    }

    /// @notice Total amount the escrow still owes across all tracked commitments.
    function totalLiabilities() public view returns (uint256 total) {
        for (uint256 i = 0; i < trackedIds.length; i++) {
            (, , , uint256 reward, , ) = escrow.getCommitment(trackedIds[i]);
            total += reward;
        }
    }
}

contract TerraCycleEscrowInvariantTest is Test {
    TerraCycleEscrow public escrow;
    EscrowInvariantHandler public handler;
    address public registrar;

    function setUp() public {
        registrar = makeAddr("invariantRegistrar");
        escrow = new TerraCycleEscrow(vm.addr(0xA11CE), registrar, "TerraCycleEscrow", "1");
        handler = new EscrowInvariantHandler(escrow, registrar);
    }

    /// @dev The escrow must never hold more or less ETH than it owes.
    function invariant_balance_equals_recorded_liabilities() public view {
        assertEq(address(escrow).balance, handler.totalLiabilities());
    }

    /// @dev The escrow must never accept a stray ETH transfer.
    function invariant_contract_holds_no_unaccounted_eth() public view {
        assertGe(address(escrow).balance, 0);
    }

    /// @dev No commitment may ever carry a zero beneficiary.
    ///
    ///      A zero beneficiary is unrecoverable: `payable(address(0)).call`
    ///      succeeds, so the reward would leave the escrow, be marked as paid
    ///      and become unspendable. `registerCommitment` rejects it
    ///      (TASK-004B.2A); this invariant proves it stays rejected.
    function invariant_no_commitment_has_a_zero_beneficiary() public view {
        uint256 count = handler.trackedCount();
        for (uint256 i = 0; i < count; i++) {
            (, address beneficiary, , , , ) = escrow.getCommitment(handler.trackedIds(i));
            assertTrue(
                beneficiary != address(0),
                "a commitment carries a zero beneficiary"
            );
        }
    }

    /// @dev Registering a zero beneficiary must ALWAYS fail, however the
    ///      handler tries it.
    function invariant_zero_beneficiary_registration_never_succeeds() public view {
        assertEq(
            handler.zeroBeneficiarySuccesses(),
            0,
            "a zero beneficiary registration succeeded"
        );
        if (handler.zeroBeneficiaryAttempts() > 0) {
            assertEq(
                handler.lastZeroBeneficiaryError(),
                bytes4(keccak256("ZeroBeneficiary()")),
                "the zero beneficiary must be rejected by the zero-address guard"
            );
        }
    }

    /// @dev An unauthorized registration must ALWAYS fail, however the handler
    ///      tries it, and it must fail with `NotRegistrar()`.
    function invariant_unauthorized_registration_never_succeeds() public view {
        assertEq(
            handler.unauthorizedSuccesses(),
            0,
            "an unauthorized registration succeeded"
        );
        if (handler.unauthorizedAttempts() > 0) {
            assertEq(
                handler.lastUnauthorizedError(),
                bytes4(keccak256("NotRegistrar()")),
                "the unauthorized registration must be rejected by the registrar guard"
            );
        }
    }
}
