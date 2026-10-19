function ParcelsPage() {
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
            NO DATASET CONNECTED
          </p>
        </div>

        <div className="mt-6 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--white)] px-5 py-8 md:px-8 md:py-10">
          <p className="text-[12px] font-medium tracking-[0.16em] text-[var(--red-700)]">
            PARCEL DATA PENDING
          </p>
          <p className="mt-3 max-w-[52ch] text-[17px] leading-[1.4] font-semibold text-[var(--ink)] md:text-[18px]">
            The field list is not available in this prototype yet.
          </p>
          <p className="mt-3 max-w-[60ch] text-[15px] leading-[1.6] text-[var(--muted)]">
            Parcel records have not been connected to this page. No fields are shown,
            and none have been invented for demonstration. Selection will be enabled
            once the shared parcel dataset is available.
          </p>
        </div>
      </section>
    </section>
  );
}

export default ParcelsPage;
