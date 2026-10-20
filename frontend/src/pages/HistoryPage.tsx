
type HistoryPageProps = {
  selectedParcelId: string | null;
  onBack: () => void;
};

export default function HistoryPage({
  selectedParcelId,
  onBack,
}: HistoryPageProps) {
  return (
    <main className="min-w-0 flex-1">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#982b3c]">
        02 / FIELD HISTORY
      </p>

      <h1 className="mt-6 font-serif text-5xl leading-tight text-[#111827] md:text-6xl">
        Field history
      </h1>

      <p className="mt-6 text-base leading-relaxed text-slate-600">
        Review the selected field before entering its crop history.
      </p>

      <div className="mt-12 border-t border-slate-200 pt-10">
        <section
          className="rounded-xl border border-slate-200 bg-white p-6 md:p-8"
          aria-labelledby="selected-field-heading"
        >
          <h2
            id="selected-field-heading"
            className="text-xl font-semibold text-slate-900"
          >
            Selected field
          </h2>

          <p className="mt-4 break-all font-mono text-sm text-slate-700">
            {selectedParcelId ?? 'No parcel selected'}
          </p>

          <p className="mt-6 text-sm text-[#982b3c]">
            Demo fixture - not satellite-verified.
          </p>
        </section>
      </div>

      <button
        type="button"
        onClick={onBack}
        className="mt-8 inline-flex min-h-11 items-center justify-center rounded-md border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-900 transition-colors hover:border-slate-900 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#982b3c]"
      >
        Back to parcel selection
      </button>
    </main>
  );
}
