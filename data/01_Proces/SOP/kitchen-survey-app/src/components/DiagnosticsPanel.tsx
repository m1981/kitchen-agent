import { Alert } from '@/components/ui/alert'
import { useDiagnostics } from '@/components/DiagnosticsProvider'

/**
 * Skrót przed kliknięciem „Dalej" — wyłącznie diagnostyki `critical`.
 * Ostrzeżenia `warning` żyją inline przy swoich polach, żeby nie robić
 * z dołu karty ściany tekstu, której nikt nie czyta.
 */
export function DiagnosticsPanel() {
  const critical = useDiagnostics().filter((d) => d.severity === 'critical')
  if (critical.length === 0) return null

  return (
    <div className="space-y-2">
      {critical.map((diagnostic) => (
        <Alert key={diagnostic.code} severity="critical">
          {diagnostic.message}
        </Alert>
      ))}
    </div>
  )
}
