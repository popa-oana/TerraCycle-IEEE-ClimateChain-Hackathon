import { useEffect, useState } from 'react';
import { ApiError } from '../lib/api';
import { getProof } from '../lib/proof';
import type { ProofDocument } from '../lib/types';

type LoadState = 'loading' | 'success' | 'error';

interface ProofState {
  status: LoadState;
  document: ProofDocument | null;
  errorMessage: string | null;
  errorCode: string | null;
}

/**
 * Verdict presentation. DESIGN_OANA.md reserves green for "conform" and amber
 * for "inconclusive"; a nonconform result uses the oxblood accent. The verdict
 * comes from the proof document, never from a constant in this file.
 */
const VERDICT_STYLES: Record<string, string> = {
  conform: 'border-[#BBD6CD] bg-[#E8F0ED] text-[var(--green-700)]',
  nonconform: 'border-[#E2C3C3] bg-[var(--red-100)] text-[var(--red-700)]',
  inconclusive: 'border-[#E0D2B2] bg-[#F7F0E2] text-[var(--amber-700)]',
};

const UNKNOWN_VERDICT_STYLE = 'border-[var(--line)] bg-[#F1F4F5] text-[var(--muted)]';

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex flex-col gap-1 border-b border-[var(--line)] py-3 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
      <dt className="text-[13px] leading-[1.4] text-[var(--muted)]">{label}</dt>
      <dd className="text-[15px] leading-[1.6] text-[var(--ink)] sm:text-right">{value ?? '—'}</dd>
    </div>
  );
}

function HashField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    const done = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      void navigator.clipboard.writeText(value).then(done, () => undefined);
      return;
    }

    const helper = document.createElement('textarea');
    helper.value = value;
    helper.setAttribute('readonly', '');
    helper.style.position = 'absolute';
    helper.style.left = '-9999px';
    document.body.appendChild(helper);
    helper.select();
    try {
      document.execCommand('copy');
      done();
    } catch {
      /* clipboard unavailable: the value stays selectable */
    }
    document.body.removeChild(helper);
  };

  return (
    <div className="flex flex-col gap-1 border-b border-[var(--line)] py-3 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
      <dt className="text-[13px] leading-[1.4] text-[var(--muted)]">{label}</dt>
      <dd className="flex min-w-0 flex-col items-start gap-2 sm:items-end">
        <code className="break-all font-mono text-[13px] leading-[1.5] text-[var(--navy-950)]">{value}</code>
        <button
          type="button"
          onClick={copy}
          className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2 py-1 text-[12px] font-medium text-[var(--muted)] transition-colors hover:border-[var(--navy-950)] hover:text-[var(--navy-950)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--red-600)]"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </dd>
    </div>
  );
}

function Card({
  title,
  step,
  children,
}: {
  title: string;
  step: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-labelledby={`proof-${step}`}
      className="mt-10 border-t border-[var(--line)] pt-8 md:mt-12 md:pt-10"
    >
      <h2
        id={`proof-${step}`}
        className="text-[22px] leading-[1.2] font-semibold text-[var(--navy-950)] md:text-[24px]"
      >
        {title}
      </h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export default function ProofPage() {
  const [state, setState] = useState<ProofState>({
    status: 'loading',
    document: null,
    errorMessage: null,
    errorCode: null,
  });

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const document = await getProof();
        if (!isMounted) {
          return;
        }
        setState({ status: 'success', document, errorMessage: null, errorCode: null });
      } catch (error: unknown) {
        if (!isMounted) {
          return;
        }
        if (error instanceof ApiError) {
          setState({
            status: 'error',
            document: null,
            errorMessage: error.message,
            errorCode: error.code,
          });
          return;
        }
        setState({
          status: 'error',
          document: null,
          errorMessage: 'The demonstration proof could not be loaded.',
          errorCode: 'UNKNOWN_ERROR',
        });
      }
    };

    void load();

    return () => {
      isMounted = false;
    };
  }, []);

  const document = state.document;
  const verdict = document?.verification.verdict ?? '';
  const verdictStyle = VERDICT_STYLES[verdict] ?? UNKNOWN_VERDICT_STYLE;

  const errorTitle = (code: string | null): string => {
    switch (code) {
      case 'PROOF_UNAVAILABLE':
        return 'NO DEMONSTRATION PROOF AVAILABLE';
      case 'PROOF_MALFORMED':
        return 'THE DEMONSTRATION PROOF IS MALFORMED';
      case 'NETWORK_ERROR':
        return 'THE PROOF SERVER IS UNREACHABLE';
      case 'INVALID_RESPONSE':
        return 'THE PROOF DOCUMENT DOES NOT MATCH THE EXPECTED STRUCTURE';
      default:
        return 'THE DEMONSTRATION PROOF COULD NOT BE LOADED';
    }
  };

  return (
    <section
      aria-labelledby="proof-page-heading"
      className="flex min-w-0 max-w-[880px] flex-1 flex-col"
    >
      <p className="text-[12px] font-medium tracking-[0.2em] text-[var(--muted)] md:text-[13px]">
        <span className="text-[var(--red-700)]">05</span> / VERIFICATION
      </p>

      <h1
        id="proof-page-heading"
        className="mt-4 max-w-[24ch] font-[family-name:var(--font-display)] text-[37px] leading-[1.12] font-medium text-[var(--ink)] md:text-[56px]"
      >
        The evidence, as recorded.
      </h1>

      <p className="mt-5 max-w-[52ch] text-[15px] leading-[1.6] text-[var(--muted)] md:text-[16px]">
        A scientific verdict from satellite observations, the canonical evidence hash, and the
        record of that hash on a local blockchain.
      </p>

      <div className="mt-10 h-px w-16 bg-[var(--red-700)]" aria-hidden="true" />

      {state.status === 'loading' && (
        <div
          role="status"
          aria-live="polite"
          className="mt-10 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10"
        >
          <p className="text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
            Loading the verified demonstration proof.
          </p>
          <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
            Retrieving the canonical evidence document. This may take a moment.
          </p>
        </div>
      )}

      {state.status === 'error' && (
        <div
          role="alert"
          className="mt-10 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10"
        >
          <p className="text-[12px] font-medium tracking-[0.16em] text-[var(--red-700)]">
            {errorTitle(state.errorCode)}
          </p>
          <p className="mt-3 max-w-[56ch] text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
            The verification result is not available.
          </p>
          <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
            {state.errorMessage ??
              'The demonstration proof could not be read. No verdict, hash or transaction is shown, and none has been invented.'}
          </p>
          <p className="mt-3 max-w-[60ch] text-[14px] leading-[1.6] text-[var(--muted)]">
            Start the read-only proof server with <code className="font-mono">python scripts/serve_demo.py</code>{' '}
            and reload this page.
          </p>
        </div>
      )}

      {state.status === 'success' && document && (
        <div>
          <p className="mt-8 text-[12px] font-medium tracking-[0.14em] text-[var(--muted)]">
            SNAPSHOT GENERATED {document.generated_at} · {document.run.network} · CHAIN{' '}
            {document.run.chain_id}
          </p>

          {/* Section A */}
          <Card title="Satellite evidence" step="satellite">
            <dl>
              <Field label="Parcel" value={document.parcel.parcel_id} />
              <Field label="Season" value={document.parcel.season_id} />
              <Field label="Satellite source" value={document.parcel.satellite_provider} />
              <Field label="Dataset" value={document.parcel.satellite_dataset} />
              <Field label="Method" value={document.parcel.satellite_method} />
              <Field label="Source file" value={document.parcel.source_csv} />
              <Field
                label="Observations"
                value={`${document.parcel.observations_total} (${document.parcel.observations_valid} valid of ${document.parcel.source_rows} rows)`}
              />
              <Field label="Evidence quality" value={document.verification.evidence_quality} />
              <Field
                label="Temporal coverage"
                value={document.verification.temporal_coverage === null ? null : `${Math.round(document.verification.temporal_coverage * 100)}%`}
              />
            </dl>
            {document.verification.evidence_quality_warnings.length > 0 && (
              <ul className="mt-4 list-disc pl-5 text-[14px] leading-[1.6] text-[var(--muted)]">
                {document.verification.evidence_quality_warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </Card>

          {/* Section B */}
          <Card title="Scientific verification" step="verification">
            <div className="flex flex-wrap items-baseline gap-4">
              <span
                className={`rounded-[var(--radius-sm)] border px-4 py-2 text-[18px] font-semibold uppercase tracking-[0.04em] ${verdictStyle}`}
              >
                {document.verification.verdict}
              </span>
              <span className="font-mono text-[13px] text-[var(--muted)]">
                verdict code {document.verification.verdict_code}
              </span>
            </div>

            <p className="mt-4 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--ink)]">
              {document.verification.reason}
            </p>

            <p className="mt-4 max-w-[60ch] border-l-2 border-[var(--line)] pl-4 text-[14px] leading-[1.6] text-[var(--muted)]">
              This is the scientific outcome for the stated window and policy. A nonconform or
              inconclusive result is a valid verification result — it is not a successful
              compliance assessment, and it is presented here unchanged.
            </p>

            <dl className="mt-6">
              <Field label="Reason code" value={document.verification.reason_code} />
              <Field
                label="Policy"
                value={`${document.verification.policy_version} (${document.verification.policy_type})`}
              />
              <Field
                label="Verification interval"
                value={`${document.verification.window_start} → ${document.verification.window_end}`}
              />
              <Field label="NDVI threshold" value={document.verification.ndvi_threshold} />
              <Field label="Required fraction" value={document.verification.required_fraction} />
              <Field label="Minimum observations" value={document.verification.min_observations} />
            </dl>
          </Card>

          {/* Section C */}
          <Card title="Canonical evidence" step="evidence">
            <dl>
              <HashField label="Commitment id" value={document.evidence.commitment_id} />
              <Field label="Evidence id" value={document.evidence.evidence_id} />
              <HashField label="Evidence hash (SHA-256)" value={document.evidence.evidence_hash} />
              <HashField
                label="Hash recomputed from the canonical bytes"
                value={document.evidence.evidence_hash_recomputed}
              />
              <Field label="Canonical size" value={`${document.evidence.canonical_bytes_length} bytes`} />
              <Field label="Evidence schema" value={document.evidence.schema_version} />
              <HashField label="Plan hash" value={document.evidence.plan_hash} />
            </dl>
          </Card>

          {/* Section D */}
          <Card title="Blockchain proof" step="blockchain">
            <p className="mb-5 inline-block rounded-[var(--radius-sm)] border border-[var(--line)] bg-[#F1F4F5] px-3 py-2 text-[12px] font-medium tracking-[0.08em] text-[var(--muted)]">
              LOCAL ANVIL SNAPSHOT — NOT A PUBLIC TESTNET, NOT LIVE CHAIN STATE
            </p>

            <dl>
              <Field label="Network" value={document.blockchain.network} />
              <Field label="Chain id" value={document.blockchain.chain_id} />
              <HashField label="Registry contract" value={document.blockchain.registry_address} />
              <HashField label="Evidence transaction" value={document.blockchain.tx_hash} />
              <HashField label="Deployment transaction" value={document.blockchain.deploy_tx_hash} />
              <Field
                label="Receipt status"
                value={document.blockchain.receipt_status === 1 ? '1 — successful' : document.blockchain.receipt_status}
              />
              <Field label="Event" value={document.blockchain.event.name} />
              <Field label="Recorded by" value={document.blockchain.event.recorder} />
              <Field
                label="On-chain read-back"
                value={
                  document.blockchain.on_chain.read_back_match
                    ? 'MATCH — the contract stores the same commitment id, evidence hash and verdict'
                    : 'MISMATCH'
                }
              />
            </dl>

            <p className="mt-5 max-w-[60ch] text-[14px] leading-[1.6] text-[var(--muted)]">
              A successful receipt means the transaction was executed and mined on the local
              chain. It says nothing about the scientific outcome of the verification, and the
              local chain is not publicly verifiable.
            </p>
          </Card>

          {/* Section E */}
          <Card title="Limitations" step="limitations">
            <ul className="list-disc pl-5 text-[15px] leading-[1.6] text-[var(--ink)]">
              {document.limitations.map((limitation) => (
                <li key={limitation} className="mb-2">
                  {limitation}
                </li>
              ))}
            </ul>
          </Card>

          <section
            aria-labelledby="proof-integrity"
            className="mt-10 border-t border-[var(--line)] pt-8 md:mt-12 md:pt-10"
          >
            <h2
              id="proof-integrity"
              className="text-[22px] leading-[1.2] font-semibold text-[var(--navy-950)] md:text-[24px]"
            >
              Integrity checks at generation time
            </h2>
            <ul className="mt-6 space-y-2">
              {Object.entries(document.integrity).map(([check, passed]) => (
                <li key={check} className="flex flex-col gap-1 text-[14px] leading-[1.6] sm:flex-row sm:gap-4">
                  <span
                    className={`font-mono text-[12px] tracking-[0.08em] ${passed ? 'text-[var(--green-700)]' : 'text-[var(--red-700)]'}`}
                  >
                    {passed ? 'VERIFIED' : 'FAILED'}
                  </span>
                  <span className="text-[var(--muted)]">{check.replace(/_/g, ' ')}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </section>
  );
}
