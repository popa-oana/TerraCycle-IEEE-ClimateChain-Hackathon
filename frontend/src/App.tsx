import { useState } from 'react';
import AppShell from './components/AppShell';
import StepProgress from './components/StepProgress';
import ParcelsPage from './pages/ParcelsPage';
import HistoryPage from './pages/HistoryPage';

function App() {
  const [selectedParcelId, setSelectedParcelId] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<1 | 2>(1);

  const handleContinue = () => {
    if (selectedParcelId !== null) {
      setCurrentStep(2);
    }
  };

  const handleBack = () => {
    setCurrentStep(1);
  };

  return (
    <AppShell>
      <div className="mx-auto flex max-w-[var(--container)] flex-col gap-8 px-5 py-12 md:flex-row md:gap-12 md:px-10 md:py-16">
        <StepProgress currentStep={currentStep} />
        {currentStep === 1 ? (
          <ParcelsPage
            selectedParcelId={selectedParcelId}
            onSelectParcel={setSelectedParcelId}
            onContinue={handleContinue}
          />
        ) : (
          <HistoryPage selectedParcelId={selectedParcelId} onBack={handleBack} />
        )}
      </div>
    </AppShell>
  );
}

export default App;
