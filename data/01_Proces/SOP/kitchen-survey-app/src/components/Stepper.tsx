import { Check } from 'lucide-react'
import { STEPS, type StepIndex } from '@/store/surveyStore'
import { cn } from '@/lib/utils'

export function Stepper({
  current,
  completed,
  onSelect,
}: {
  current: StepIndex
  completed: number[]
  onSelect: (step: StepIndex) => void
}) {
  return (
    <nav aria-label="Kroki kreatora" className="no-print">
      <ol className="flex gap-1 overflow-x-auto pb-1">
        {STEPS.map((step) => {
          const isDone = completed.includes(step.id)
          const isCurrent = step.id === current
          // Wolno cofnąć się do kroku ukończonego lub wejść w bieżący/następny.
          const reachable = isDone || step.id <= current
          return (
            <li key={step.key} className="min-w-0 flex-1">
              <button
                type="button"
                disabled={!reachable}
                onClick={() => onSelect(step.id as StepIndex)}
                aria-current={isCurrent ? 'step' : undefined}
                className={cn(
                  'flex w-full min-h-11 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold whitespace-nowrap transition-colors',
                  isCurrent
                    ? 'bg-brand-900 text-white'
                    : isDone
                      ? 'bg-brand-100 text-brand-900 hover:bg-brand-200'
                      : 'bg-white text-slate-400',
                  !reachable && 'cursor-not-allowed opacity-60',
                )}
              >
                {isDone && !isCurrent ? (
                  <Check className="size-3.5" aria-hidden />
                ) : (
                  <span className="tabular-nums">{step.id + 1}.</span>
                )}
                <span className="truncate">{step.short}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
