function App() {
  return (
    <main className="min-h-screen bg-[var(--paper)] text-[var(--ink)]">
      <header className="bg-[var(--navy-950)] text-[var(--paper)]">
        <div className="mx-auto flex h-[60px] max-w-[var(--container)] items-center px-5 md:h-[var(--header-height)] md:px-10">
          <span className="text-[12px] font-medium tracking-[0.18em] md:text-[13px]">
            TERRACYCLE&nbsp;<span className="text-[var(--red-600)]">/</span>&nbsp;PROOF
          </span>
        </div>
      </header>

      <section className="mx-auto flex min-h-[60vh] max-w-[var(--container)] flex-col justify-center px-5 py-16 md:min-h-[420px] md:px-10 md:py-24">
        <p className="text-[12px] font-medium uppercase tracking-[0.2em] text-[var(--muted)] md:text-[13px]">
          TERRACYCLE / PROOF
        </p>

        <h1 className="mt-4 max-w-[16ch] font-[family-name:var(--font-display)] text-[37px] leading-[1.12] font-medium text-[var(--ink)] md:text-[56px]">
          TerraCycle Proof
        </h1>

        <p className="mt-5 max-w-[46ch] text-[15px] leading-[1.6] text-[var(--muted)] md:text-[16px]">
          A verifiable agricultural record, from field to evidence.
        </p>

        <div className="mt-10 h-px w-16 bg-[var(--red-700)]" aria-hidden="true" />

        <p className="mt-6 text-[12px] font-medium tracking-[0.14em] text-[var(--muted)] md:text-[13px]">
          Demonstration prototype · 2026
        </p>
      </section>
    </main>
  );
}

export default App;
