import { useEffect, useState } from 'react';
import { getParcels, ApiError } from '../lib/api';
import type { Parcel } from '../lib/types';

type LoadState = 'loading' | 'success' | 'empty' | 'error';

interface ParcelsState {
  status: LoadState;
  parcels: Parcel[];
  errorMessage: string | null;
  errorCode: string | null;
  configError: boolean;
  networkError: boolean;
}

function ParcelsPage() {
  const [state, setState] = useState<ParcelsState>({
    status: 'loading',
    parcels: [],
    errorMessage: null,
    errorCode: null,
    configError: false,
    networkError: false,
  });
  const [selectedParcelId, setSelectedParcelId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    let ignore = false;

    const load = async () => {
      if (ignore) {
        return;
      }
      setState({
        status: 'loading',
        parcels: [],
        errorMessage: null,
        errorCode: null,
        configError: false,
        networkError: false,
      });

      try {
        const response = await getParcels();
        if (!isMounted) {
          return;
        }

        const parcels = response.parcels;
        if (parcels.length === 0) {
          setState({
            status: 'empty',
            parcels: [],
            errorMessage: null,
            errorCode: null,
            configError: false,
            networkError: false,
          });
          return;
        }

        setState({
          status: 'success',
          parcels,
          errorMessage: null,
          errorCode: null,
          configError: false,
          networkError: false,
        });
      } catch (error: unknown) {
        if (!isMounted) {
          return;
        }

        if (error instanceof ApiError) {
          const isConfig = error.code === 'CONFIG_ERROR';
          const isNetwork = error.code === 'NETWORK_ERROR';
          setState({
            status: 'error',
            parcels: [],
            errorMessage: error.message,
            errorCode: error.code,
            configError: isConfig,
            networkError: isNetwork,
          });
          return;
        }

        setState({
          status: 'error',
          parcels: [],
          errorMessage: 'An unexpected error occurred while loading parcels.',
          errorCode: 'UNKNOWN_ERROR',
          configError: false,
          networkError: false,
        });
      }
    };

    load();

    return () => {
      isMounted = false;
      ignore = true;
    };
  }, []);

  return (
    <section
      aria-labelledby="parcels-page-heading"
      className="flex min-w-0 max-w-[880px] flex-1 flex-col"
    >
      <p className="text-[12px] font-medium tracking-[0.2em] text-[var(--muted)] md:text-[13px]">
        <span className="text-[var(--red-700)]">01</span> / SELECT A FIELD
      </p>

      <h1
        id="parcels-page-heading"
        className="mt-4 max-w-[20ch] font-[family-name:var(--font-display)] text-[37px] leading-[1.12] font-medium text-[var(--ink)] md:text-[56px]"
      >
        A claim is not a proof.
      </h1>

      <p className="mt-5 max-w-[46ch] text-[15px] leading-[1.6] text-[var(--muted)] md:text-[16px]">
        A verifiable agricultural record, from field to evidence.
      </p>

      <div className="mt-10 h-px w-16 bg-[var(--red-700)]" aria-hidden="true" />

      <section
        aria-labelledby="field-selection-heading"
        className="mt-10 border-t border-[var(--line)] pt-8 md:mt-12 md:pt-10"
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
          <h2
            id="field-selection-heading"
            className="text-[22px] leading-[1.2] font-semibold text-[var(--navy-950)] md:text-[24px]"
          >
            Field selection
          </h2>
          <p className="text-[12px] font-medium tracking-[0.14em] text-[var(--muted)]">
            {state.status === 'loading' && 'LOADING PARCELS'}
            {state.status === 'success' && 'PARCELS LOADED'}
            {state.status === 'empty' && 'NO PARCELS RETURNED'}
            {state.status === 'error' && 'PARCEL DATA UNAVAILABLE'}
          </p>
        </div>

        <div className="mt-6">
          <p className="mb-6 text-[12px] font-medium tracking-[0.12em] text-[var(--red-700)]">
            Demo fixture — not satellite-verified.
          </p>

          {state.status === 'loading' && (
            <div
              role="status"
              aria-live="polite"
              className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10"
            >
              <p className="text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
                Loading parcels from the API.
              </p>
              <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
                Retrieving available fields. This may take a moment.
              </p>
            </div>
          )}

          {state.status === 'error' && (
            <div
              role="alert"
              className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10"
            >
              <p className="text-[12px] font-medium tracking-[0.16em] text-[var(--red-700)]">
                {state.configError
                  ? 'API CONFIGURATION ERROR'
                  : state.networkError
                    ? 'BACKEND UNAVAILABLE'
                    : 'PARCEL DATA ERROR'}
              </p>
              <p className="mt-3 max-w-[52ch] text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
                {state.configError
                  ? 'API base URL is not configured.'
                  : state.networkError
                    ? 'The backend could not be reached.'
                    : 'The parcel list could not be loaded.'}
              </p>
              <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
                {state.errorMessage ??
                  'An unexpected error occurred while retrieving parcel records. No fields were shown and none were invented.'}
              </p>
              {!state.configError && (
                <p className="mt-3 max-w-[60ch] text-[14px] leading-[1.6] text-[var(--muted)]">
                  Ensure the backend is running and that CORS allows this origin.
                </p>
              )}
            </div>
          )}

          {state.status === 'empty' && (
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10">
              <p className="text-[12px] font-medium tracking-[0.16em] text-[var(--red-700)]">
                NO PARCELS RETURNED
              </p>
              <p className="mt-3 max-w-[52ch] text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
                The API returned an empty parcel list.
              </p>
              <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
                No parcel records are currently available. No fields are shown, and none
                have been invented for demonstration.
              </p>
            </div>
          )}

          {state.status === 'success' && (
            <>
              <p
                className="mb-4 text-[12px] font-medium tracking-[0.12em] text-[var(--muted)]"
                aria-live="polite"
              >
                {selectedParcelId
                  ? `SELECTED PARCEL: ${selectedParcelId}`
                  : 'SELECT A PARCEL BY CLICKING OR USING KEYBOARD'}
              </p>
              <ul
                className="flex flex-col gap-6 md:gap-8"
                aria-label="Available parcels"
              >
                {state.parcels.map((parcel) => {
                  const isSelected = selectedParcelId === parcel.parcel_id;
                  return (
                    <li
                      key={parcel.parcel_id}
                      className={`flex flex-col gap-4 rounded-[var(--radius-md)] border bg-[var(--white)] px-5 py-6 transition-shadow md:px-8 md:py-8 ${
                        isSelected
                          ? 'border-[var(--red-700)] shadow-[var(--shadow-soft)] ring-1 ring-[var(--red-700)]'
                          : 'border-[var(--line)]'
                      }`}
                    >
                      <button
                        type="button"
                        className="w-full text-left focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[var(--red-600)]"
                        aria-pressed={isSelected}
                        aria-label={`Select ${parcel.display_name}, ${parcel.parcel_id}, ${parcel.region}, ${parcel.area_ha} hectares`}
                        onClick={() => {
                          setSelectedParcelId((current) =>
                            current === parcel.parcel_id ? null : parcel.parcel_id,
                          );
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            setSelectedParcelId((current) =>
                              current === parcel.parcel_id ? null : parcel.parcel_id,
                            );
                          }
                        }}
                      >
                        <div className="flex flex-col gap-2 md:flex-row md:items-baseline md:justify-between">
                          <h3 className="text-[18px] leading-[1.25] font-semibold text-[var(--navy-950)] md:text-[20px]">
                            {parcel.display_name}
                          </h3>
                          <p className="text-[12px] font-medium tracking-[0.14em] text-[var(--muted)]">
                            {parcel.parcel_id}
                          </p>
                        </div>

                        <div className="mt-3 flex flex-col gap-x-8 gap-y-2 sm:flex-row sm:items-baseline">
                          <p className="text-[15px] leading-[1.6] text-[var(--ink)] md:text-[16px]">
                            <span className="text-[var(--muted)]">Region:</span>{' '}
                            {parcel.region}
                          </p>
                          <p className="text-[15px] leading-[1.6] text-[var(--ink)] md:text-[16px]">
                            <span className="text-[var(--muted)]">Area:</span>{' '}
                            {parcel.area_ha.toLocaleString('en-US')} ha
                          </p>
                        </div>
                        {isSelected && (
                          <p className="mt-3 text-[12px] font-medium tracking-[0.12em] text-[var(--red-700)]">
                            SELECTED
                          </p>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      </section>
    </section>
  );
}

export default ParcelsPage;
