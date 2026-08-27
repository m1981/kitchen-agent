import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { forwardRef, useId } from 'react'
import { cn } from '@/lib/utils'

const CONTROL_BASE =
  'w-full min-h-12 rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 ' +
  'placeholder:text-slate-400 transition-colors ' +
  'focus:border-brand-500 focus:outline-2 focus:outline-offset-0 focus:outline-brand-500/40 ' +
  'aria-[invalid=true]:border-red-500 aria-[invalid=true]:bg-red-50/40'

export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p className="mt-1 text-sm font-medium text-red-600" role="alert">
      {message}
    </p>
  )
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string
  hint?: string
  error?: string
  required?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <label className="mb-1 block text-sm font-semibold text-slate-700">
        {label}
        {required ? <span className="ml-0.5 text-red-600">*</span> : null}
      </label>
      {children}
      {hint && !error ? (
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
      ) : null}
      <FieldError message={error} />
    </div>
  )
}

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }
>(function Input({ className, invalid, ...props }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid ? 'true' : undefined}
      className={cn(CONTROL_BASE, className)}
      {...props}
    />
  )
})

/** Input wymiarowy — numeryczna klawiatura na tablecie, sufiks "mm". */
export const MmInput = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean; unit?: string }
>(function MmInput({ className, invalid, unit = 'mm', ...props }, ref) {
  return (
    <div className="relative">
      <input
        ref={ref}
        inputMode="decimal"
        autoComplete="off"
        aria-invalid={invalid ? 'true' : undefined}
        className={cn(CONTROL_BASE, 'pr-11 tabular-nums', className)}
        {...props}
      />
      <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-slate-400">
        {unit}
      </span>
    </div>
  )
})

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }
>(function Select({ className, invalid, children, ...props }, ref) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid ? 'true' : undefined}
      className={cn(CONTROL_BASE, 'appearance-none pr-8', className)}
      {...props}
    >
      {children}
    </select>
  )
})

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      rows={4}
      className={cn(CONTROL_BASE, 'min-h-24 resize-y leading-relaxed', className)}
      {...props}
    />
  )
})

export const Checkbox = forwardRef<
  HTMLInputElement,
  Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
    label: ReactNode
    description?: string
  }
>(function Checkbox({ label, description, className, ...props }, ref) {
  const id = useId()
  return (
    <div className={cn('flex items-start gap-3', className)}>
      <input
        ref={ref}
        id={id}
        type="checkbox"
        className="mt-0.5 size-6 shrink-0 cursor-pointer rounded border-slate-400 text-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
        {...props}
      />
      <label htmlFor={id} className="cursor-pointer text-sm text-slate-700">
        <span className="font-medium">{label}</span>
        {description ? (
          <span className="mt-0.5 block text-xs text-slate-500">
            {description}
          </span>
        ) : null}
      </label>
    </div>
  )
})

/** Segmentowany wybór — duże cele dotykowe zamiast małych radiów. */
export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  name,
}: {
  value: T | null
  options: ReadonlyArray<{ value: T; label: string; hint?: string }>
  onChange: (value: T) => void
  name: string
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label={name}>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'min-h-12 rounded-lg border px-3 py-2 text-left text-sm font-semibold transition-colors',
              active
                ? 'border-brand-500 bg-brand-50 text-brand-900 ring-2 ring-brand-500/30'
                : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50',
            )}
          >
            {option.label}
            {option.hint ? (
              <span className="mt-0.5 block text-xs font-normal text-slate-500">
                {option.hint}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
