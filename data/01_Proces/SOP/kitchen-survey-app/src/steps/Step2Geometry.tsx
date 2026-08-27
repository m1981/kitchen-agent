import { zodResolver } from '@hookform/resolvers/zod'
import { Ruler, TriangleAlert } from 'lucide-react'
import { useCallback } from 'react'
import type { UseFormRegister } from 'react-hook-form'
import { useForm } from 'react-hook-form'
import { StepNav } from '@/components/StepNav'
import { Alert } from '@/components/ui/alert'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import {
  Checkbox,
  Field,
  MmInput,
  SegmentedControl,
  Select,
  Textarea,
} from '@/components/ui/field'
import {
  computeMaxColumnHeight,
  computeMinDimension,
  formatMm,
  geometryWarnings,
  recommendedFiller,
  toNumber,
} from '@/lib/calc'
import { useAutosave } from '@/lib/useAutosave'
import { roomGeometrySchema, type RoomGeometryInput } from '@/lib/schema'
import { useSurveyStore } from '@/store/surveyStore'

type WallKey = 'wallA' | 'wallB' | 'wallC' | 'height'

const POINT_LABELS: Record<WallKey, [string, string, string]> = {
  wallA: ['Dół (posadzka)', 'Środek (~850–900)', 'Góra (pod sufitem)'],
  wallB: ['Dół (posadzka)', 'Środek (~850–900)', 'Góra (pod sufitem)'],
  wallC: ['Dół (posadzka)', 'Środek (~850–900)', 'Góra (pod sufitem)'],
  height: ['Lewa', 'Środek', 'Prawa'],
}

function ThreePointRow({
  name,
  title,
  subtitle,
  register,
  values,
  required,
  error,
  deviationLabel,
}: {
  name: WallKey
  title: string
  subtitle?: string
  register: UseFormRegister<RoomGeometryInput>
  values: { bottom: unknown; middle: unknown; top: unknown }
  required?: boolean
  error?: string
  deviationLabel: string
}) {
  const { min, spread } = computeMinDimension([
    values.bottom as string,
    values.middle as string,
    values.top as string,
  ])
  const labels = POINT_LABELS[name]

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-bold text-slate-800">
          {title}
          {required ? <span className="ml-0.5 text-red-600">*</span> : null}
        </h3>
        {subtitle ? (
          <span className="text-xs text-slate-500">{subtitle}</span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {(['bottom', 'middle', 'top'] as const).map((point, index) => (
          <Field key={point} label={labels[index]}>
            <MmInput
              {...register(`${name}.${point}` as const)}
              placeholder="0"
              invalid={!!error && point === 'bottom'}
            />
          </Field>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-md bg-brand-50 px-3 py-2">
          <span className="block text-xs font-semibold tracking-wide text-brand-900 uppercase">
            Najmniejszy (do CAD)
          </span>
          <span className="text-lg font-bold tabular-nums text-brand-900">
            {formatMm(min)}
          </span>
          {spread !== null && spread > 0 ? (
            <span className="ml-2 text-xs text-slate-600">
              rozrzut {spread} mm → blenda ~{recommendedFiller(spread)} mm
            </span>
          ) : null}
        </div>
        <Field label={deviationLabel}>
          <MmInput
            {...register(`${name}.deviation` as const)}
            placeholder="+/-"
          />
        </Field>
      </div>

      {error ? (
        <p className="mt-2 text-sm font-medium text-red-600" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function Step2Geometry() {
  const geometry = useSurveyStore((state) => state.geometry)
  const setGeometry = useSurveyStore((state) => state.setGeometry)
  const markStepComplete = useSurveyStore((state) => state.markStepComplete)
  const next = useSurveyStore((state) => state.next)
  const prev = useSurveyStore((state) => state.prev)

  const form = useForm<RoomGeometryInput>({
    resolver: zodResolver(roomGeometrySchema),
    defaultValues: geometry,
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
    (values: RoomGeometryInput) => setGeometry(values),
    [setGeometry],
  )
  useAutosave(watch, save)

  const values = watch()

  const heightStats = computeMinDimension([
    values.height?.bottom as string,
    values.height?.middle as string,
    values.height?.top as string,
  ])
  const maxColumn = computeMaxColumnHeight(heightStats.min)

  const warnings = geometryWarnings({
    wallASpread: computeMinDimension([
      values.wallA?.bottom as string,
      values.wallA?.middle as string,
      values.wallA?.top as string,
    ]).spread,
    wallBSpread: computeMinDimension([
      values.wallB?.bottom as string,
      values.wallB?.middle as string,
      values.wallB?.top as string,
    ]).spread,
    wallCSpread: computeMinDimension([
      values.wallC?.bottom as string,
      values.wallC?.middle as string,
      values.wallC?.top as string,
    ]).spread,
    heightMin: heightStats.min,
    heightSpread: heightStats.spread,
    cornerAngle: toNumber(values.cornerAngle as string),
    floorLevelDrop: toNumber(values.floorLevelDrop as string),
    ceilingType: String(values.ceilingType ?? 'twardy'),
    hasWindow: !!values.hasWindow,
    windowSillHeight: toNumber(values.windowSillHeight as string),
    tapWindowCollision: !!values.obstacles?.tapWindowCollision,
  })

  const layout = values.layout ?? 'I'
  const showWallB = layout === 'L' || layout === 'U'
  const showWallC = layout === 'U'

  const onSubmit = handleSubmit(() => {
    markStepComplete(1)
    next()
  })

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <Card>
        <CardHeader
          title="2. Geometria pomieszczenia — Bounding Box"
          description="Laser 360°, pomiar 3-punktowy. Do CAD wchodzi zawsze najmniejszy wymiar."
          icon={<Ruler className="size-5" aria-hidden />}
        />
        <CardBody>
          <Alert severity="info">
            <strong>Złota zasada:</strong> mierz szerokość i wysokość w 3
            punktach. Do Corpus LTR wprowadzasz <strong>NAJMNIEJSZY</strong>{' '}
            wymiar wnęki i planujesz blendy maskujące 30–50 mm.
          </Alert>

          <Field label="Układ zabudowy" required error={errors.layout?.message}>
            <SegmentedControl
              name="Układ zabudowy"
              value={layout as 'I' | 'L' | 'U'}
              onChange={(value) =>
                setValue('layout', value, { shouldValidate: true })
              }
              options={[
                { value: 'I', label: 'I — jednorzędowa', hint: 'Tylko ściana A' },
                { value: 'L', label: 'L — narożna', hint: 'Ściany A + B' },
                { value: 'U', label: 'U — podkowa', hint: 'Ściany A + B + C' },
              ]}
            />
          </Field>

          <ThreePointRow
            name="wallA"
            title="Ściana główna A (szerokość)"
            register={register}
            values={{
              bottom: values.wallA?.bottom,
              middle: values.wallA?.middle,
              top: values.wallA?.top,
            }}
            required
            error={errors.wallA?.bottom?.message}
            deviationLabel="Odchyłka pionu (+/-)"
          />

          {showWallB ? (
            <ThreePointRow
              name="wallB"
              title="Ściana boczna B"
              subtitle="Wymagana dla układu L / U"
              register={register}
              values={{
                bottom: values.wallB?.bottom,
                middle: values.wallB?.middle,
                top: values.wallB?.top,
              }}
              required
              error={errors.wallB?.bottom?.message}
              deviationLabel="Odchyłka pionu (+/-)"
            />
          ) : null}

          {showWallC ? (
            <ThreePointRow
              name="wallC"
              title="Ściana boczna C"
              subtitle="Wymagana dla układu U"
              register={register}
              values={{
                bottom: values.wallC?.bottom,
                middle: values.wallC?.middle,
                top: values.wallC?.top,
              }}
              required
              error={errors.wallC?.bottom?.message}
              deviationLabel="Odchyłka pionu (+/-)"
            />
          ) : null}

          <ThreePointRow
            name="height"
            title="Wysokość pomieszczenia H"
            register={register}
            values={{
              bottom: values.height?.bottom,
              middle: values.height?.middle,
              top: values.height?.top,
            }}
            required
            error={errors.height?.bottom?.message}
            deviationLabel="Spadek posadzki (+/-)"
          />

          <div className="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2">
            <span className="block text-xs font-semibold tracking-wide text-brand-900 uppercase">
              Max wysokość słupka pod sufit
            </span>
            <span className="text-lg font-bold tabular-nums text-brand-900">
              {formatMm(maxColumn)}
            </span>
            <span className="ml-2 text-xs text-slate-600">
              = H min − 30 mm (przekątna + blenda górna)
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Kąt w narożniku"
              hint="Pomiar laserem, np. 89,5"
              error={errors.cornerAngle?.message}
            >
              <MmInput
                {...register('cornerAngle')}
                unit="°"
                placeholder="90"
                invalid={!!errors.cornerAngle}
              />
            </Field>

            <Field label="Rodzaj sufitu" error={errors.ceilingType?.message}>
              <Select {...register('ceilingType')}>
                <option value="twardy">Twardy (beton / tynk)</option>
                <option value="podwieszany">Podwieszany (karton-gips)</option>
              </Select>
            </Field>

            <Field
              label="Poziom podłogi — spadek"
              hint="Różnica lewo–prawo na długości zabudowy"
              error={errors.floorLevelDrop?.message}
            >
              <MmInput {...register('floorLevelDrop')} placeholder="0" />
            </Field>
          </div>

          {/* Progressive disclosure: podciąg */}
          <div className="rounded-lg border border-slate-200 p-3">
            <Checkbox
              {...register('hasBulkhead')}
              label="Podciąg / uskok sufitu"
              description="Zmienia wysokość szafek górnych na części ciągu."
            />
            {values.hasBulkhead ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                <Field label="Szerokość" error={errors.bulkheadWidth?.message}>
                  <MmInput {...register('bulkheadWidth')} placeholder="0" />
                </Field>
                <Field
                  label="Wysokość"
                  error={errors.bulkheadHeight?.message}
                >
                  <MmInput
                    {...register('bulkheadHeight')}
                    placeholder="0"
                    invalid={!!errors.bulkheadHeight}
                  />
                </Field>
                <Field label="Głębokość" error={errors.bulkheadDepth?.message}>
                  <MmInput {...register('bulkheadDepth')} placeholder="0" />
                </Field>
                <Field
                  label="Odległość od lewej"
                  error={errors.bulkheadOffsetFromLeft?.message}
                >
                  <MmInput
                    {...register('bulkheadOffsetFromLeft')}
                    placeholder="0"
                  />
                </Field>
              </div>
            ) : null}
          </div>

          {/* Progressive disclosure: okno */}
          <div className="rounded-lg border border-slate-200 p-3">
            <Checkbox
              {...register('hasWindow')}
              label="Okno w ciągu zabudowy"
              description="Parapet i oś okna decydują o wysokości blatu i panelu HPL."
            />
            {values.hasWindow ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                <Field
                  label="Wys. do parapetu"
                  hint="Od gotowej posadzki"
                  error={errors.windowSillHeight?.message}
                >
                  <MmInput
                    {...register('windowSillHeight')}
                    placeholder="0"
                    invalid={!!errors.windowSillHeight}
                  />
                </Field>
                <Field
                  label="Głębokość parapetu"
                  error={errors.windowSillDepth?.message}
                >
                  <MmInput {...register('windowSillDepth')} placeholder="0" />
                </Field>
                <Field
                  label="Oś okna od lewej"
                  error={errors.windowAxisFromLeft?.message}
                >
                  <MmInput
                    {...register('windowAxisFromLeft')}
                    placeholder="0"
                    invalid={!!errors.windowAxisFromLeft}
                  />
                </Field>
                <Field label="Kierunek otwierania">
                  <Select {...register('windowOpening')}>
                    <option value="brak">Brak / nie dotyczy</option>
                    <option value="lewe">Lewe</option>
                    <option value="prawe">Prawe</option>
                    <option value="uchylne">Tylko uchylne</option>
                  </Select>
                </Field>
              </div>
            ) : null}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="2b. Przeszkody i analiza kolizji"
          description="Wszystko, co wchodzi w bryłę zabudowy."
          accent="red"
          icon={<TriangleAlert className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-2">
            <Checkbox
              {...register('obstacles.tapWindowCollision')}
              label="Kolizja baterii z oknem"
              description="Wymaga baterii składanej lub przesunięcia zlewu."
            />
            <Checkbox
              {...register('obstacles.inspectionHatch')}
              label="Drzwiczki rewizyjne (wodomierze)"
              description="Zostawić dostęp serwisowy w blendzie."
            />
            <Checkbox
              {...register('obstacles.skirtingBoards')}
              label="Listwy przypodłogowe (do demontażu)"
            />
            <Checkbox
              {...register('obstacles.lightSwitch')}
              label="Włącznik światła (kolizja ze słupkiem)"
            />
            <Checkbox
              {...register('obstacles.intercomThermostat')}
              label="Domofon / termostat na ścianie"
            />
            <Checkbox
              {...register('obstacles.chimneyShaft')}
              label="Wystający szacht kominowy"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-3">
              <Checkbox {...register('obstacles.radiator')} label="Grzejnik" />
              {values.obstacles?.radiator ? (
                <Field
                  label="Odstaje od ściany"
                  className="mt-3"
                  error={errors.obstacles?.radiatorProtrusion?.message}
                >
                  <MmInput
                    {...register('obstacles.radiatorProtrusion')}
                    placeholder="0"
                    invalid={!!errors.obstacles?.radiatorProtrusion}
                  />
                </Field>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-200 p-3">
              <Checkbox
                {...register('obstacles.wallNiche')}
                label="Wnęka w ścianie"
              />
              {values.obstacles?.wallNiche ? (
                <Field
                  label="Głębokość wnęki"
                  className="mt-3"
                  error={errors.obstacles?.wallNicheDepth?.message}
                >
                  <MmInput
                    {...register('obstacles.wallNicheDepth')}
                    placeholder="0"
                    invalid={!!errors.obstacles?.wallNicheDepth}
                  />
                </Field>
              ) : null}
            </div>
          </div>

          <Field
            label="Notatki z natury"
            hint="Szkic robimy na kartce / telefonem — tu opis słowny."
            error={errors.obstacles?.notes?.message}
          >
            <Textarea
              {...register('obstacles.notes')}
              placeholder="np. Rura gazowa w narożniku na wys. 2100 mm, sufit opada w stronę okna…"
            />
          </Field>

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
        <StepNav onBack={prev} nextLabel="Dalej: AGD i przyłącza" />
      </Card>
    </form>
  )
}
