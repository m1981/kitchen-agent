import { zodResolver } from '@hookform/resolvers/zod'
import { ClipboardCheck, Palette, Truck } from 'lucide-react'
import { useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { StepNav } from '@/components/StepNav'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import { Checkbox, Field, Input, Select, Textarea } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { useAutosave } from '@/lib/useAutosave'
import {
  finishAndLogisticsSchema,
  type FinishAndLogisticsInput,
} from '@/lib/schema'
import {
  STYLE_PACKAGE_DETAILS,
  type StylePackageKey,
} from '@/lib/stylePackages'
import { useSurveyStore } from '@/store/surveyStore'

const PACKAGE_KEYS = Object.keys(STYLE_PACKAGE_DETAILS) as StylePackageKey[]

export function Step4Finish() {
  const finish = useSurveyStore((state) => state.finish)
  const setFinish = useSurveyStore((state) => state.setFinish)
  const markStepComplete = useSurveyStore((state) => state.markStepComplete)
  const next = useSurveyStore((state) => state.next)
  const prev = useSurveyStore((state) => state.prev)

  const form = useForm<FinishAndLogisticsInput>({
    resolver: zodResolver(finishAndLogisticsSchema),
    defaultValues: finish,
    mode: 'onTouched',
  })

  const { register, handleSubmit, watch, setValue } = form

  const save = useCallback(
    (values: FinishAndLogisticsInput) => setFinish(values),
    [setFinish],
  )
  useAutosave(watch, save)

  const selected = watch('stylePackage')

  const onSubmit = handleSubmit(() => {
    markStepComplete(3)
    next()
  })

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <Card>
        <CardHeader
          title="5. Pakiet materiałowy (metoda lejka)"
          description="Wybór jednego z trzech gotowych zestawów Swiss Krono / Egger."
          icon={<Palette className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-3">
            {PACKAGE_KEYS.map((key) => {
              const pack = STYLE_PACKAGE_DETAILS[key]
              const active = selected === key
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    setValue('stylePackage', active ? null : key, {
                      shouldDirty: true,
                    })
                  }
                  className={cn(
                    'rounded-lg border p-3 text-left transition-colors',
                    active
                      ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-500/30'
                      : 'border-slate-300 bg-white hover:bg-slate-50',
                  )}
                >
                  <span className="block text-sm font-bold text-brand-900">
                    {pack.name}
                  </span>
                  <ul className="mt-2 space-y-1 text-xs text-slate-600">
                    {pack.lines.map((line) => (
                      <li key={line}>• {line}</li>
                    ))}
                  </ul>
                </button>
              )
            })}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="5b. Logistyka i transport"
          description="Krytyczne dla blatów HPL — przekątna windy decyduje o cięciu."
          icon={<Truck className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Winda (szer. × gł. × wys.)">
              <Input
                {...register('logistics.elevator')}
                placeholder="np. 900 × 1200 × 2100 — przekątna max 1500"
              />
            </Field>
            <Field label="Klatka schodowa / drzwi">
              <Input
                {...register('logistics.staircase')}
                placeholder="Szerokość drzwi, zakręty"
              />
            </Field>
            <Field label="Parking / rozładunek">
              <Input
                {...register('logistics.parking')}
                placeholder="Gdzie stajemy busem?"
              />
            </Field>
            <Field label="Ochrona posadzki">
              <Select {...register('logistics.floorProtection')}>
                <option value="brak">Nie wymagana</option>
                <option value="tektura">Wymagana — tektura falista</option>
                <option value="hdf">Wymagana — płyty HDF</option>
              </Select>
            </Field>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="6. Checklista przed zatwierdzeniem"
          description="Bez tych pozycji nie wysyłamy plików do centrum CNC."
          icon={<ClipboardCheck className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-2">
            <Checkbox
              {...register('checklist.photoDocumentation')}
              label="Pełna dokumentacja foto (ściany, narożniki, przyłącza)"
            />
            <Checkbox
              {...register('checklist.serviceSpace')}
              label="Przestrzeń serwisowa 50–70 mm za szafkami dolnymi"
            />
            <Checkbox
              {...register('checklist.clientInformedNoChanges')}
              label="Klient poinformowany o braku zmian po wysyłce do CNC"
            />
            <Checkbox
              {...register('checklist.drawerSystemConfirmed')}
              label="Wybrano system szuflad (Blum Merivobox / Antaro)"
            />
            <Checkbox
              {...register('checklist.sinkTemplateConfirmed')}
              label="Zlew podwieszany + szablon frezowania MDF"
            />
            <Checkbox
              {...register('checklist.purGlueOnly')}
              label="Okleinowanie formatek wyłącznie klejem PUR"
            />
          </div>

          <Field
            label="Opis szkicu z natury / rozmieszczenie modułów"
            hint="Lodówka, zlew, płyta, ciąg szuflad, blendy skrajne, kierunek usłojenia."
          >
            <Textarea
              {...register('sketchNotes')}
              rows={6}
              placeholder="np. Od lewej: słupek lodówki 600, zlew pod oknem 800, płyta 600, ciąg szuflad 900, blenda prawa 40 mm…"
            />
          </Field>
        </CardBody>
        <StepNav onBack={prev} nextLabel="Dalej: podsumowanie" isLast />
      </Card>
    </form>
  )
}
