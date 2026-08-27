import { HardHat, RotateCcw, Save } from 'lucide-react'
import { useState } from 'react'
import { Stepper } from '@/components/Stepper'
import { Button } from '@/components/ui/button'
import { Step1Customer } from '@/steps/Step1Customer'
import { Step2Geometry } from '@/steps/Step2Geometry'
import { Step3Installations } from '@/steps/Step3Installations'
import { Step4Finish } from '@/steps/Step4Finish'
import { Step5Summary } from '@/steps/Step5Summary'
import { STEPS, useSurveyStore } from '@/store/surveyStore'

function SaveIndicator({ lastSavedAt }: { lastSavedAt: string | null }) {
  if (!lastSavedAt) {
    return <span className="text-xs text-slate-400">Nowy pomiar</span>
  }
  const time = new Date(lastSavedAt).toLocaleTimeString('pl-PL', {
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <span className="flex items-center gap-1 text-xs text-emerald-600">
      <Save className="size-3.5" aria-hidden />
      Zapisano lokalnie {time}
    </span>
  )
}

export default function App() {
  const currentStep = useSurveyStore((state) => state.currentStep)
  const completedSteps = useSurveyStore((state) => state.completedSteps)
  const lastSavedAt = useSurveyStore((state) => state.lastSavedAt)
  const goToStep = useSurveyStore((state) => state.goToStep)
  const resetSession = useSurveyStore((state) => state.resetSession)
  const clientName = useSurveyStore((state) => state.customer.clientName)

  const [confirmReset, setConfirmReset] = useState(false)

  const stepTitle = STEPS[currentStep]?.title ?? ''

  return (
    <div className="mx-auto min-h-screen w-full max-w-4xl px-3 py-4 sm:px-4 sm:py-6">
      <header className="no-print mb-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <HardHat className="size-6 text-brand-900" aria-hidden />
            <div>
              <h1 className="text-base leading-tight font-bold text-brand-900">
                Karta Pomiarowa Kuchni
              </h1>
              <p className="text-xs text-slate-500">
                Etap 1.1 · {clientName || 'nowy pomiar'} · {stepTitle}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <SaveIndicator lastSavedAt={lastSavedAt} />
            <Button
              variant="danger"
              className="min-h-10 px-3 text-sm"
              onClick={() => setConfirmReset(true)}
            >
              <RotateCcw className="size-4" aria-hidden />
              Nowy pomiar
            </Button>
          </div>
        </div>

        <Stepper
          current={currentStep}
          completed={completedSteps}
          onSelect={goToStep}
        />
      </header>

      {confirmReset ? (
        <div className="no-print mb-4 rounded-lg border border-red-300 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-900">
            Wyczyścić pamięć lokalną i zacząć nowy pomiar? Bieżących danych nie
            da się odzyskać — najpierw pobierz JSON.
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              variant="danger"
              onClick={() => {
                resetSession()
                setConfirmReset(false)
              }}
            >
              Tak, wyczyść
            </Button>
            <Button variant="secondary" onClick={() => setConfirmReset(false)}>
              Anuluj
            </Button>
          </div>
        </div>
      ) : null}

      <main>
        {currentStep === 0 ? <Step1Customer /> : null}
        {currentStep === 1 ? <Step2Geometry /> : null}
        {currentStep === 2 ? <Step3Installations /> : null}
        {currentStep === 3 ? <Step4Finish /> : null}
        {currentStep === 4 ? <Step5Summary /> : null}
      </main>

      <footer className="no-print mt-6 text-center text-xs text-slate-400">
        Dane trzymane wyłącznie w tej przeglądarce (LocalStorage). Brak backendu,
        brak wysyłki do chmury.
      </footer>
    </div>
  )
}
