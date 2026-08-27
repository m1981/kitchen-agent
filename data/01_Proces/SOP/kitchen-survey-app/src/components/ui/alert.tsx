import { AlertTriangle, Info, OctagonAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Severity } from '@/lib/diagnostics'
import { cn } from '@/lib/utils'

const CRITICAL = {
  box: 'bg-red-50 border-red-200 border-l-red-600 text-red-900',
  icon: <OctagonAlert className="size-4 shrink-0" aria-hidden />,
}

const STYLES: Record<Severity, { box: string; icon: ReactNode }> = {
  // Bloker wygląda jak critical — różnica jest w tym, czy przepuszcza dalej.
  blocker: CRITICAL,
  info: {
    box: 'bg-brand-50 border-brand-200 border-l-brand-500 text-brand-900',
    icon: <Info className="size-4 shrink-0" aria-hidden />,
  },
  warning: {
    box: 'bg-amber-50 border-amber-200 border-l-amber-500 text-amber-900',
    icon: <AlertTriangle className="size-4 shrink-0" aria-hidden />,
  },
  critical: CRITICAL,
}

export function Alert({
  severity = 'info',
  children,
  className,
}: {
  severity?: Severity
  children: ReactNode
  className?: string
}) {
  const style = STYLES[severity]
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-md border border-l-4 px-3 py-2 text-sm',
        style.box,
        className,
      )}
      role={severity === 'critical' || severity === 'blocker' ? 'alert' : 'status'}
    >
      <span className="mt-0.5">{style.icon}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}
