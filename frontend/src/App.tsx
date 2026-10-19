import AppShell from './components/AppShell';
import StepProgress from './components/StepProgress';
import ParcelsPage from './pages/ParcelsPage';

function App() {
  return (
    <AppShell>
      <div className="mx-auto flex max-w-[var(--container)] flex-col gap-8 px-5 py-12 md:flex-row md:gap-12 md:px-10 md:py-16">
        <StepProgress currentStep={1} />
        <ParcelsPage />
      </div>
    </AppShell>
  );
}

export default App;
