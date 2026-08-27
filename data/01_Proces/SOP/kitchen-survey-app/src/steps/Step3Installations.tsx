import { zodResolver } from '@hookform/resolvers/zod'
import { Flame, PlugZap, Refrigerator, Wind } from 'lucide-react'
import { useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { StepNav } from '@/components/StepNav'
import { Alert } from '@/components/ui/alert'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import {
  Checkbox,
  Field,
  Input,
  MmInput,
  SegmentedControl,
} from '@/components/ui/field'
import { installationWarnings, toNumber } from '@/lib/calc'
import { useAutosave } from '@/lib/useAutosave'
import { installationsSchema, type InstallationsInput } from '@/lib/schema'
import { useSurveyStore } from '@/store/surveyStore'

/** Punkty, przy których gniazdo za AGD to błąd krytyczny. */
const SOCKET_POINTS = new Set([
  'piekarnik-230v',
  'zmywarka-230v',
  'lodowka-230v',
  'sila-400v',
])

export function Step3Installations() {
  const installations = useSurveyStore((state) => state.installations)
  const setInstallations = useSurveyStore((state) => state.setInstallations)
  const markStepComplete = useSurveyStore((state) => state.markStepComplete)
  const next = useSurveyStore((state) => state.next)
  const prev = useSurveyStore((state) => state.prev)

  const form = useForm<InstallationsInput>({
    resolver: zodResolver(installationsSchema),
    defaultValues: installations,
    mode: 'onTouched',
  })

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = form

  const save = useCallback(
    (values: InstallationsInput) => setInstallations(values),
    [setInstallations],
  )
  useAutosave(watch, save)

  const values = watch()
  const utilities = values.utilities ?? installations.utilities

  const warnings = installationWarnings({
    hobVentGap: toNumber(values.appliances?.hob?.ventGap as string),
    hobDistanceToSink: toNumber(
      values.appliances?.hob?.distanceToSink as string,
    ),
    hobDistanceToSideWall: toNumber(
      values.appliances?.hob?.distanceToSideWall as string,
    ),
    fridgeNoHdfBack: !!values.appliances?.fridge?.noHdfBack,
    fridgeVentGapMin50: !!values.appliances?.fridge?.ventGapMin50,
    ovenNoHdfBack: !!values.appliances?.oven?.noHdfBack,
    hobMetalTraverses: !!values.appliances?.hob?.metalTraverses,
    socketBehindApplianceIds: utilities
      .filter((point) => point.behindAppliance)
      .map((point) => point.label),
  })

  const onSubmit = handleSubmit(() => {
    markStepComplete(2)
    next()
  })

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <Card>
        <CardHeader
          title="3. AGD, wentylacja i odstępy"
          accent="red"
          description="Czerwona strefa elektryczna i wymogi wentylacyjne zabudowy."
          icon={<Refrigerator className="size-5" aria-hidden />}
        />
        <CardBody>
          <Alert severity="critical">
            <strong>ZAKAZ GNIAZDEK ZA AGD.</strong> Lodówka, piekarnik i zmywarka
            wchodzą na 540–550 mm — wystająca wtyczka wypchnie sprzęt przed lico
            frontów. Gniazda wyłącznie w szafkach sąsiadujących, z wycięciem w
            HDF.
          </Alert>

          {/* Lodówka */}
          <div className="rounded-lg border border-slate-200 p-3">
            <h3 className="mb-2 text-sm font-bold text-brand-900">
              Słupek lodówkowy
            </h3>
            <Field label="System frontu">
              <SegmentedControl
                name="System frontu lodówki"
                value={
                  (values.appliances?.fridge?.frontSystem ?? 'suwakowy') as
                    | 'door-on-door'
                    | 'suwakowy'
                }
                onChange={(value) =>
                  setValue('appliances.fridge.frontSystem', value)
                }
                options={[
                  {
                    value: 'door-on-door',
                    label: 'Door-on-Door',
                    hint: 'Front na drzwiach lodówki',
                  },
                  {
                    value: 'suwakowy',
                    label: 'Suwakowy / Sliding',
                    hint: 'Blum 155° 71T6550',
                  },
                ]}
              />
            </Field>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Checkbox
                {...register('appliances.fridge.noHdfBack')}
                label="Brak pleców HDF w module"
              />
              <Checkbox
                {...register('appliances.fridge.ventGapMin50')}
                label="Komin wentylacyjny min. 50 mm od ściany"
              />
              <Checkbox
                {...register('appliances.fridge.inletGrille')}
                label="Wlot w cokole min. 200 cm²"
              />
              <Checkbox
                {...register('appliances.fridge.outletGrille')}
                label="Wylot w wieńcu min. 200 cm²"
              />
              <Checkbox
                {...register('appliances.fridge.visibleSideFrontMaterial')}
                label="Bok widoczny z materiału frontowego (EM)"
                description="Swiss Krono BE.VELVET — nie korpusowy VL."
              />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Model lodówki">
                <Input
                  {...register('appliances.fridge.model')}
                  placeholder="np. Bosch KIN86NSE0"
                />
              </Field>
              <Field label="Wysokość niszy">
                <MmInput
                  {...register('appliances.fridge.nicheHeight')}
                  placeholder="0"
                />
              </Field>
            </div>
          </div>

          {/* Piekarnik i płyta */}
          <div className="rounded-lg border border-slate-200 p-3">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-brand-900">
              <Flame className="size-4" aria-hidden />
              Piekarnik i płyta indukcyjna
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Umiejscowienie piekarnika">
                <SegmentedControl
                  name="Umiejscowienie piekarnika"
                  value={
                    (values.appliances?.oven?.placement ?? 'slupek') as
                      | 'slupek'
                      | 'pod-blatem'
                  }
                  onChange={(value) =>
                    setValue('appliances.oven.placement', value)
                  }
                  options={[
                    { value: 'slupek', label: 'W słupku wysokim' },
                    { value: 'pod-blatem', label: 'W szafce pod blatem' },
                  ]}
                />
              </Field>
              <Field label="Zasilanie płyty">
                <SegmentedControl
                  name="Zasilanie płyty"
                  value={
                    (values.appliances?.hob?.power ?? '400V') as '400V' | '230V'
                  }
                  onChange={(value) => setValue('appliances.hob.power', value)}
                  options={[
                    { value: '400V', label: 'Siła 400V (3 fazy)' },
                    { value: '230V', label: '230V' },
                  ]}
                />
              </Field>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Checkbox
                {...register('appliances.oven.noHdfBack')}
                label="Brak pleców HDF w niszy piekarnika"
              />
              <Checkbox
                {...register('appliances.oven.thermalShields')}
                label="Aluminiowe blaszki termiczne na boki"
              />
              <Checkbox
                {...register('appliances.oven.socketInNeighbourCabinet')}
                label="Gniazdo 230V w szafce obok"
              />
              <Checkbox
                {...register('appliances.hob.metalTraverses')}
                label="Trawersy metalowe pod blatem HPL 12 mm"
              />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <Field
                label="Szczelina wentylacyjna pod płytą"
                hint="Zalecane 5–20 mm"
              >
                <MmInput
                  {...register('appliances.hob.ventGap')}
                  placeholder="10"
                />
              </Field>
              <Field label="Odstęp płyta – zlew" hint="Min. 300 mm">
                <MmInput
                  {...register('appliances.hob.distanceToSink')}
                  placeholder="300"
                />
              </Field>
              <Field label="Odstęp płyta – ściana boczna" hint="Min. 300 mm">
                <MmInput
                  {...register('appliances.hob.distanceToSideWall')}
                  placeholder="300"
                />
              </Field>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Model piekarnika">
                <Input {...register('appliances.oven.model')} placeholder="Model" />
              </Field>
              <Field label="Model płyty / wymiar wycięcia">
                <Input
                  {...register('appliances.hob.model')}
                  placeholder="np. 560 × 490 mm"
                />
              </Field>
            </div>
          </div>

          {/* Zmywarka i okap */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-3">
              <h3 className="mb-2 text-sm font-bold text-brand-900">Zmywarka</h3>
              <Field label="Szerokość">
                <SegmentedControl
                  name="Szerokość zmywarki"
                  value={
                    (values.appliances?.dishwasher?.width ?? '60') as '45' | '60'
                  }
                  onChange={(value) =>
                    setValue('appliances.dishwasher.width', value)
                  }
                  options={[
                    { value: '45', label: '45 cm' },
                    { value: '60', label: '60 cm' },
                  ]}
                />
              </Field>
              <div className="mt-3 space-y-3">
                <Checkbox
                  {...register('appliances.dishwasher.varioHinge')}
                  label="Zawiasy ślizgowe VarioHinge"
                  description="Przy niskich cokołach i wysokich frontach."
                />
                <Checkbox
                  {...register('appliances.dishwasher.steamProtectionStrip')}
                  label="Listwa aluminiowa pod blatem (ochrona przed parą)"
                />
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 p-3">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-brand-900">
                <Wind className="size-4" aria-hidden />
                Okap i wentylacja
              </h3>
              <Field label="Typ okapu">
                <SegmentedControl
                  name="Typ okapu"
                  value={
                    (values.appliances?.hood?.type ?? 'wyciag') as
                      | 'wyciag'
                      | 'pochlaniacz'
                  }
                  onChange={(value) => setValue('appliances.hood.type', value)}
                  options={[
                    { value: 'wyciag', label: 'Wyciąg do komina' },
                    { value: 'pochlaniacz', label: 'Pochłaniacz' },
                  ]}
                />
              </Field>
              {values.appliances?.hood?.type === 'wyciag' ? (
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  <Field label="Oś wlotu X">
                    <MmInput
                      {...register('appliances.hood.ductAxisX')}
                      placeholder="0"
                    />
                  </Field>
                  <Field label="Wysokość Y">
                    <MmInput
                      {...register('appliances.hood.ductHeightY')}
                      placeholder="0"
                    />
                  </Field>
                  <Field label="Średnica rury">
                    <MmInput
                      {...register('appliances.hood.ductDiameter')}
                      placeholder="150"
                    />
                  </Field>
                </div>
              ) : null}
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="4. Mapowanie przyłączy (osie X, Y dla CNC)"
          description="X = od lewej ściany bazowej, Y = od gotowej posadzki."
          icon={<PlugZap className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="space-y-3">
            {utilities.map((point, index) => (
              <div
                key={point.id}
                className="rounded-lg border border-slate-200 p-3"
              >
                <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-sm font-bold text-slate-800">
                    {point.label}
                  </h3>
                  <span className="text-xs text-slate-500">{point.cabinet}</span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Pozycja X (od lewej)">
                    <MmInput
                      {...register(`utilities.${index}.x` as const)}
                      placeholder="0"
                      invalid={!!errors.utilities?.[index]?.x}
                    />
                  </Field>
                  <Field label="Wysokość Y (od podłogi)">
                    <MmInput
                      {...register(`utilities.${index}.y` as const)}
                      placeholder="0"
                      invalid={!!errors.utilities?.[index]?.y}
                    />
                  </Field>
                </div>
                <Field label="Uwagi wykonawcze" className="mt-3">
                  <Input {...register(`utilities.${index}.notes` as const)} />
                </Field>
                {SOCKET_POINTS.has(point.id) ? (
                  <div className="mt-3">
                    <Checkbox
                      {...register(
                        `utilities.${index}.behindAppliance` as const,
                      )}
                      label="Gniazdo wypada BEZPOŚREDNIO ZA AGD"
                      description="Zaznacz, jeśli tak jest w rzeczywistości — trzeba je przenieść."
                    />
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {warnings.length > 0 ? (
            <div className="space-y-2">
              {warnings.map((warning) => (
                <Alert key={warning.id} severity={warning.severity}>
                  {warning.message}
                </Alert>
              ))}
            </div>
          ) : null}
        </CardBody>
        <StepNav onBack={prev} nextLabel="Dalej: pakiet i logistyka" />
      </Card>
    </form>
  )
}
