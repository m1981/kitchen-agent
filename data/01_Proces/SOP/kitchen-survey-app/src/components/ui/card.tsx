import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <section
      className={cn(
        'rounded-xl border border-slate-200 bg-white shadow-sm print-avoid-break',
        className,
      )}
    >
      {children}
    </section>
  )
}

export function CardHeader({
  title,
  description,
  icon,
  accent = 'brand',
}: {
  title: string
  description?: string
  icon?: ReactNode
  accent?: 'brand' | 'red' | 'slate'
}) {
  const border =
    accent === 'red'
      ? 'border-l-red-600'
      : accent === 'slate'
        ? 'border-l-slate-400'
        : 'border-l-brand-500'
  return (
    <header
      className={cn(
        'flex items-start gap-3 border-b border-slate-200 border-l-4 px-4 py-3',
        border,
      )}
    >
      {icon ? <span className="mt-0.5 text-brand-900">{icon}</span> : null}
      <div>
        <h2 className="text-sm font-bold tracking-wide text-slate-900 uppercase">
          {title}
        </h2>
        {description ? (
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        ) : null}
      </div>
    </header>
  )
}

export function CardBody({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return <div className={cn('space-y-4 p-4', className)}>{children}</div>
}
