import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function StepNav({
  onBack,
  backLabel = 'Wstecz',
  nextLabel = 'Dalej',
  showBack = true,
  isLast = false,
}: {
  onBack?: () => void
  backLabel?: string
  nextLabel?: string
  showBack?: boolean
  isLast?: boolean
}) {
  return (
    <div className="no-print sticky bottom-0 -mx-4 mt-6 flex gap-3 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-b-xl">
      {showBack ? (
        <Button variant="secondary" onClick={onBack} className="flex-1 sm:flex-none">
          <ArrowLeft className="size-4" aria-hidden />
          {backLabel}
        </Button>
      ) : null}
      <Button type="submit" className="flex-1">
        {isLast ? <Check className="size-4" aria-hidden /> : null}
        {nextLabel}
        {isLast ? null : <ArrowRight className="size-4" aria-hidden />}
      </Button>
    </div>
  )
}
