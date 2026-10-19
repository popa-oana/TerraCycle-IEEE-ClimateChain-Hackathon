import AppShell from './components/AppShell';
import StepProgress from './components/StepProgress';

function App() {
  return (
    <AppShell>
      <div className="mx-auto flex max-w-[var(--container)] flex-col gap-8 px-5 py-12 md:flex-row md:gap-12 md:px-10 md:py-16">
        <StepProgress currentStep={1} />

        <section className="flex min-h-[40vh] min-w-0 max-w-[880px] flex-1 flex-col justify-center md:min-h-[360px]">
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
      </div>
    </AppShell>
  );
}

export default App;
