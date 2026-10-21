import type { ReactNode } from 'react';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--paper)] text-[var(--ink)]">
      <header className="bg-[var(--navy-950)] text-[var(--paper)]">
        <div className="mx-auto flex h-[60px] max-w-[var(--container)] items-center px-5 md:h-[var(--header-height)] md:px-10">
          <span className="text-[12px] font-medium tracking-[0.18em] md:text-[13px]">
            TERRACYCLE&nbsp;<span className="text-[var(--red-600)]">/</span>&nbsp;PROOF
          </span>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="bg-[var(--navy-950)] text-[var(--paper)]">
        <div className="mx-auto flex max-w-[var(--container)] flex-col gap-1 px-5 py-5 md:flex-row md:items-center md:justify-between md:px-10">
          <p className="text-[12px] leading-[1.4] font-medium tracking-[0.12em] text-[var(--paper)] md:text-[13px]">
            TerraCycle Proof / Demonstration prototype • 2026
          </p>
          <p className="text-[12px] leading-[1.4] text-[var(--line)] md:text-[13px]">
            Vegetation-cover assessment from satellite observations.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default AppShell;
