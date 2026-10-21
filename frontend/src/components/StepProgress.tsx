export type StepIndex = 1 | 2 | 3 | 4 | 5 | 6;

interface StepProgressProps {
  currentStep: StepIndex;
  /**
   * Steps that were genuinely completed. A step that was only visited is not
   * completed, so the rail never claims progress that did not happen.
   */
  completedSteps?: StepIndex[];
  /** Steps that can be opened directly. */
  availableSteps?: StepIndex[];
  onSelectStep?: (step: StepIndex) => void;
}

interface WorkflowStep {
  index: StepIndex;
  label: string;
}

const WORKFLOW_STEPS: WorkflowStep[] = [
  { index: 1, label: 'Choose a field' },
  { index: 2, label: 'Field history' },
  { index: 3, label: 'Rotation options' },
  { index: 4, label: 'Commitment' },
  { index: 5, label: 'Verification' },
  { index: 6, label: 'Digital passport' },
];

function padStep(step: number): string {
  return step.toString().padStart(2, '0');
}

export function StepProgress({
  currentStep,
  completedSteps = [],
  availableSteps = [],
  onSelectStep,
}: StepProgressProps) {
  const activeLabel = WORKFLOW_STEPS[currentStep - 1].label;

  return (
    <nav aria-label="Workflow progress" className="w-full min-w-0 md:w-auto">
      {/* Desktop: vertical rail */}
      <ol className="hidden w-[var(--rail)] shrink-0 md:block">
        {WORKFLOW_STEPS.map((step) => {
          const isCurrent = step.index === currentStep;
          const isCompleted = completedSteps.includes(step.index);
          const isAvailable = availableSteps.includes(step.index) && onSelectStep !== undefined;
          const borderStyle = {
            borderColor: isCurrent ? 'var(--red-700)' : 'var(--line)',
            borderLeftWidth: isCurrent ? '3px' : '1px',
          };

          const content = (
            <>
              <span
                className={`font-mono text-[13px] tracking-[0.08em] ${
                  isCurrent ? 'text-[var(--red-700)]' : 'text-[var(--muted)]'
                }`}
              >
                {padStep(step.index)}
              </span>
              <span
                className={`text-[14px] leading-[1.4] ${
                  isCurrent
                    ? 'font-semibold text-[var(--navy-950)]'
                    : isCompleted
                      ? 'text-[var(--muted)]'
                      : 'text-[var(--muted)]'
                }`}
              >
                {step.label}
              </span>
              {isCompleted && (
                <span className="ml-auto text-[12px] text-[var(--muted)]" aria-hidden="true">
                  &#10003;
                </span>
              )}
            </>
          );

          return (
            <li key={step.index} className="relative">
              {isAvailable ? (
                <button
                  type="button"
                  onClick={() => onSelectStep(step.index)}
                  aria-current={isCurrent ? 'step' : undefined}
                  className="flex w-full items-baseline gap-3 border-l py-3 pl-4 text-left transition-colors hover:bg-[var(--white)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--red-600)]"
                  style={borderStyle}
                >
                  {content}
                </button>
              ) : (
                <div className="flex items-baseline gap-3 border-l py-3 pl-4" style={borderStyle}>
                  {content}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {/* Mobile: compact horizontal progress */}
      <div className="w-full md:hidden">
        <div className="flex w-full flex-col gap-1">
          <p className="text-[12px] font-medium tracking-[0.16em] text-[var(--muted)]">
            STEP {padStep(currentStep)} OF 06
          </p>
          <p className="text-[13px] leading-[1.4] font-semibold text-[var(--navy-950)]">
            {activeLabel}
          </p>
        </div>
        <div
          className="mt-3 flex w-full gap-1.5"
          role="group"
          aria-label={`Step ${currentStep} of 6: ${activeLabel}`}
        >
          {WORKFLOW_STEPS.map((step) => {
            const isCurrent = step.index === currentStep;
            const isCompleted = completedSteps.includes(step.index);
            const isAvailable = availableSteps.includes(step.index) && onSelectStep !== undefined;

            const segmentClass = `h-1.5 min-w-0 flex-1 ${
              isCurrent
                ? 'bg-[var(--red-700)]'
                : isCompleted
                  ? 'bg-[var(--navy-800)]'
                  : 'bg-[var(--line)]'
            }`;

            return isAvailable ? (
              <button
                key={step.index}
                type="button"
                onClick={() => onSelectStep(step.index)}
                aria-current={isCurrent ? 'step' : undefined}
                aria-label={`${padStep(step.index)} ${step.label}`}
                title={`${padStep(step.index)} ${step.label}`}
                className={`${segmentClass} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--red-600)]`}
              />
            ) : (
              <div
                key={step.index}
                className={segmentClass}
                aria-current={isCurrent ? 'step' : undefined}
                title={`${padStep(step.index)} ${step.label}`}
              />
            );
          })}
        </div>
      </div>
    </nav>
  );
}

export default StepProgress;
