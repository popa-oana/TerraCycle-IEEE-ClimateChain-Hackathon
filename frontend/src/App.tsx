import { useEffect, useState } from 'react';
import AppShell from './components/AppShell';
import StepProgress, { type StepIndex } from './components/StepProgress';
import ParcelsPage from './pages/ParcelsPage';
import HistoryPage from './pages/HistoryPage';
import ProofPage from './pages/ProofPage';

const VERIFICATION_HASH = '#verification';
const FIELD_SELECTION_STEP: StepIndex = 1;
const HISTORY_STEP: StepIndex = 2;
const VERIFICATION_STEP: StepIndex = 5;

function stepFromHash(): StepIndex {
  if (typeof window !== 'undefined' && window.location.hash === VERIFICATION_HASH) {
    return VERIFICATION_STEP;
  }
  return FIELD_SELECTION_STEP;
}

function App() {
  const [selectedParcelId, setSelectedParcelId] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<StepIndex>(stepFromHash);

  // The verification page can be opened directly, without finishing the earlier steps.
  useEffect(() => {
    const onHashChange = () => {
      setCurrentStep(stepFromHash());
    };

    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const handleContinue = () => {
    if (selectedParcelId !== null) {
      setCurrentStep(HISTORY_STEP);
    }
  };

  const handleBack = () => {
    setCurrentStep(FIELD_SELECTION_STEP);
  };

  const handleSelectStep = (step: StepIndex) => {
    if (step === VERIFICATION_STEP) {
      window.location.hash = VERIFICATION_HASH;
      setCurrentStep(VERIFICATION_STEP);
      return;
    }
    if (step === FIELD_SELECTION_STEP) {
      window.location.hash = '';
      setCurrentStep(FIELD_SELECTION_STEP);
    }
  };

  // Only steps that were genuinely finished are marked as completed.
  const completedSteps: StepIndex[] =
    selectedParcelId !== null && currentStep !== FIELD_SELECTION_STEP ? [FIELD_SELECTION_STEP] : [];

  return (
    <AppShell>
      <div className="mx-auto flex max-w-[var(--container)] flex-col gap-8 px-5 py-12 md:flex-row md:gap-12 md:px-10 md:py-16">
        <StepProgress
          currentStep={currentStep}
          completedSteps={completedSteps}
          availableSteps={[FIELD_SELECTION_STEP, VERIFICATION_STEP]}
          onSelectStep={handleSelectStep}
        />
        {currentStep === VERIFICATION_STEP ? (
          <ProofPage />
        ) : currentStep === FIELD_SELECTION_STEP ? (
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
