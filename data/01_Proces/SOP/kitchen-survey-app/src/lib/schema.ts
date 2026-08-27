import { z } from 'zod'
import { computeMaxColumnHeight, computeMinDimension } from './calc.ts'
import { runRules, toPathSegments, type Rule } from './diagnostics.ts'
import { GEOMETRY_RULES } from './rules/geometry.ts'
import { installationRules } from './rules/installations.ts'

/**
 * Schemat rozdziela się na dwie warstwy (patrz docs/adr/0009-rule-registry.md):
 *
 * - `…Shape`  — kształt + wartości pochodne. Parsuje się zawsze, także dla
 *               niekompletnego formularza. To po nim UI liczy diagnostyki.
 * - `…Schema` — `Shape` + polityka domenowa. Wciąga z rejestru reguł wyłącznie
 *               diagnostyki `blocker` i zgłasza je jako błędy pola.
 */
const addBlockers =
  <M, P extends string>(
    resolve: (model: M) => ReadonlyArray<Rule<M, P>>,
  ) =>
  (model: M, ctx: z.RefinementCtx) => {
    for (const diagnostic of runRules(model, resolve(model))) {
      if (diagnostic.severity !== 'blocker') continue
      ctx.addIssue({
        code: 'custom',
        path: toPathSegments(diagnostic.path),
        message: diagnostic.message,
      })
    }
  }

/* -------------------------------------------------------------------------- */
/*  Prymitywy pomiarowe                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Pole liczbowe w mm. Puste pole ("") mapujemy na `null`, żeby odróżnić
 * "nie zmierzono" od wartości 0 i nie wywalać walidacji na świeżym formularzu.
 */
export const mmOptional = z
  .union([z.string(), z.number(), z.null(), z.undefined()])
  .transform((value) => {
    if (value === null || value === undefined) return null
    if (typeof value === 'number') return Number.isFinite(value) ? value : null
    const normalized = value.trim().replace(',', '.')
    if (normalized === '') return null
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  })
  .pipe(
    z
      .number()
      .min(0, 'Wymiar nie może być ujemny')
      .max(20000, 'Wymiar poza zakresem (max 20 000 mm)')
      .nullable(),
  )

/** Wariant wymagany (Hard warning) — bez wymiaru nie przechodzimy dalej. */
export const mmRequired = (message = 'Wymiar wymagany') =>
  mmOptional.refine((value): value is number => value !== null, { message })

/** Odchyłka pionu / spadek posadzki — może być ujemna. */
export const deviationOptional = z
  .union([z.string(), z.number(), z.null(), z.undefined()])
  .transform((value) => {
    if (value === null || value === undefined) return null
    if (typeof value === 'number') return Number.isFinite(value) ? value : null
    const normalized = value.trim().replace(',', '.')
    if (normalized === '') return null
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  })
  .pipe(z.number().min(-500).max(500).nullable())

const optionalText = z
  .string()
  .trim()
  .max(500, 'Maksymalnie 500 znaków')
  .optional()
  .default('')

/* -------------------------------------------------------------------------- */
/*  KROK 1 — Dane klienta i inwestycji                                         */
/* -------------------------------------------------------------------------- */

export const customerInfoSchema = z
  .object({
    /** Inwestor — używany też do nazwy pliku eksportu (pomiar_kowalski.json). */
    clientName: z
      .string()
      .trim()
      .min(3, 'Podaj imię i nazwisko inwestora (min. 3 znaki)')
      .max(120, 'Maksymalnie 120 znaków'),
    phone: z
      .string()
      .trim()
      .min(9, 'Telefon wymagany (min. 9 znaków)')
      .max(30, 'Maksymalnie 30 znaków')
      .regex(/^[0-9+()\-\s]+$/, 'Dozwolone tylko cyfry i znaki + ( ) -'),
    email: z
      .union([z.literal(''), z.email('Nieprawidłowy e-mail')])
      .optional()
      .default(''),
    /** Adres inwestycji / osiedle — bez adresu ekipa nie dojedzie na montaż. */
    address: z
      .string()
      .trim()
      .min(5, 'Podaj adres inwestycji (min. 5 znaków)')
      .max(200, 'Maksymalnie 200 znaków'),
    measurementDate: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, 'Data w formacie RRRR-MM-DD'),
    /** Planowany termin montażu — tekst, bo w praktyce to "4–5 tygodni". */
    plannedInstallation: optionalText,
    budget: optionalText,
    surveyorName: optionalText,
  })
  .superRefine((data, ctx) => {
    // Soft-hard granica: pomiar z przyszłą datą to prawie zawsze literówka.
    const measured = new Date(`${data.measurementDate}T00:00:00`)
    if (Number.isNaN(measured.getTime())) {
      ctx.addIssue({
        code: 'custom',
        path: ['measurementDate'],
        message: 'Nieprawidłowa data',
      })
    }
  })

export type CustomerInfo = z.infer<typeof customerInfoSchema>
export type CustomerInfoInput = z.input<typeof customerInfoSchema>

/* -------------------------------------------------------------------------- */
/*  KROK 2 — Geometria pomieszczenia (Bounding Box, pomiar 3-punktowy)         */
/* -------------------------------------------------------------------------- */

export const LAYOUTS = ['I', 'L', 'U'] as const
export const CEILING_TYPES = ['twardy', 'podwieszany'] as const
export const WINDOW_OPENING = ['brak', 'lewe', 'prawe', 'uchylne'] as const

/**
 * Pomiar 3-punktowy jednej płaszczyzny. `min` jest wyliczany automatycznie
 * (cross-field logic) — do CAD wchodzi ZAWSZE najmniejszy zarejestrowany wymiar.
 */
export const threePointMeasurementSchema = z
  .object({
    bottom: mmOptional,
    middle: mmOptional,
    top: mmOptional,
    deviation: deviationOptional,
  })
  .transform((data) => {
    const { min, spread } = computeMinDimension([data.bottom, data.middle, data.top])
    return {
      ...data,
      /** NAJMNIEJSZY wymiar — wartość wprowadzana do Corpus LTR. */
      min,
      /** Rozrzut pomiaru — sygnał "krzywa ściana", steruje szerokością blendy. */
      spread,
    }
  })

export type ThreePointMeasurement = z.infer<typeof threePointMeasurementSchema>

export const obstaclesSchema = z.object({
  tapWindowCollision: z.boolean().default(false),
  radiator: z.boolean().default(false),
  radiatorProtrusion: mmOptional,
  skirtingBoards: z.boolean().default(false),
  inspectionHatch: z.boolean().default(false),
  lightSwitch: z.boolean().default(false),
  intercomThermostat: z.boolean().default(false),
  chimneyShaft: z.boolean().default(false),
  wallNiche: z.boolean().default(false),
  wallNicheDepth: mmOptional,
  notes: z.string().trim().max(2000, 'Maksymalnie 2000 znaków').optional().default(''),
})

export const roomGeometryShape = z
  .object({
    layout: z.enum(LAYOUTS, { error: 'Wybierz układ zabudowy' }),

    /* Bounding Box — pomiar 3-punktowy */
    wallA: threePointMeasurementSchema,
    wallB: threePointMeasurementSchema,
    wallC: threePointMeasurementSchema,
    /** Wysokość pomieszczenia: lewa / środek / prawa. */
    height: threePointMeasurementSchema,

    /* Parametry geometrii */
    cornerAngle: z
      .union([z.string(), z.number(), z.null(), z.undefined()])
      .transform((value) => {
        if (value === null || value === undefined) return null
        if (typeof value === 'number') return Number.isFinite(value) ? value : null
        const normalized = value.trim().replace(',', '.')
        if (normalized === '') return null
        const parsed = Number(normalized)
        return Number.isFinite(parsed) ? parsed : null
      })
      .pipe(z.number().min(45, 'Kąt poza zakresem').max(135, 'Kąt poza zakresem').nullable()),
    ceilingType: z.enum(CEILING_TYPES).default('twardy'),
    floorLevelDrop: deviationOptional,

    /* Podciąg / uskok sufitu */
    hasBulkhead: z.boolean().default(false),
    bulkheadWidth: mmOptional,
    bulkheadHeight: mmOptional,
    bulkheadDepth: mmOptional,
    bulkheadOffsetFromLeft: mmOptional,

    /* Okno (Progressive Disclosure) */
    hasWindow: z.boolean().default(false),
    windowSillHeight: mmOptional,
    windowSillDepth: mmOptional,
    windowAxisFromLeft: mmOptional,
    windowOpening: z.enum(WINDOW_OPENING).default('brak'),

    obstacles: obstaclesSchema,
  })
  .transform((data) => ({
    ...data,
    /**
     * Maksymalna wysokość słupka pod sufit = H min − 30 mm
     * (luz montażowy na przekątną + blenda górna).
     */
    maxColumnHeight: computeMaxColumnHeight(data.height.min),
  }))

/** Polityka domenowa: blokery z rejestru reguł (`lib/rules/geometry.ts`). */
export const roomGeometrySchema = roomGeometryShape.superRefine(
  addBlockers(() => GEOMETRY_RULES),
)

/** Model po parsowaniu i wyliczeniach — wejście dla reguł domenowych. */
export type RoomGeometryModel = z.output<typeof roomGeometryShape>
export type RoomGeometry = z.output<typeof roomGeometrySchema>
export type RoomGeometryInput = z.input<typeof roomGeometryShape>

/* -------------------------------------------------------------------------- */
/*  KROK 3 — AGD, wentylacja i przyłącza (osie X/Y dla CNC)                    */
/* -------------------------------------------------------------------------- */

export const FRIDGE_FRONT_SYSTEM = ['door-on-door', 'suwakowy'] as const
export const OVEN_PLACEMENT = ['slupek', 'pod-blatem'] as const
export const HOB_POWER = ['400V', '230V'] as const
export const DISHWASHER_WIDTH = ['45', '60'] as const
export const HOOD_TYPE = ['wyciag', 'pochlaniacz'] as const

export const appliancesSchema = z.object({
  fridge: z.object({
    frontSystem: z.enum(FRIDGE_FRONT_SYSTEM).default('suwakowy'),
    noHdfBack: z.boolean().default(true),
    ventGapMin50: z.boolean().default(true),
    inletGrille: z.boolean().default(true),
    outletGrille: z.boolean().default(true),
    visibleSideFrontMaterial: z.boolean().default(true),
    model: optionalText,
    nicheHeight: mmOptional,
  }),
  oven: z.object({
    placement: z.enum(OVEN_PLACEMENT).default('slupek'),
    noHdfBack: z.boolean().default(true),
    thermalShields: z.boolean().default(true),
    socketInNeighbourCabinet: z.boolean().default(true),
    model: optionalText,
  }),
  hob: z.object({
    power: z.enum(HOB_POWER).default('400V'),
    ventGap: mmOptional,
    metalTraverses: z.boolean().default(true),
    distanceToSink: mmOptional,
    distanceToSideWall: mmOptional,
    model: optionalText,
  }),
  dishwasher: z.object({
    width: z.enum(DISHWASHER_WIDTH).default('60'),
    varioHinge: z.boolean().default(false),
    steamProtectionStrip: z.boolean().default(true),
  }),
  hood: z.object({
    type: z.enum(HOOD_TYPE).default('wyciag'),
    ductAxisX: mmOptional,
    ductHeightY: mmOptional,
    ductDiameter: mmOptional,
  }),
})

/** Pojedyncze przyłącze: X od lewej ściany bazowej, Y od gotowej posadzki. */
export const utilityPointSchema = z.object({
  id: z.string(),
  label: z.string(),
  x: mmOptional,
  y: mmOptional,
  cabinet: optionalText,
  notes: optionalText,
  /** Czerwona strefa: gniazdo bezpośrednio za AGD do zabudowy. */
  behindAppliance: z.boolean().default(false),
})

export type UtilityPoint = z.infer<typeof utilityPointSchema>

export const installationsShape = z.object({
  appliances: appliancesSchema,
  utilities: z.array(utilityPointSchema),
})

/** Model po parsowaniu — wejście dla reguł domenowych. */
export type InstallationsModel = z.output<typeof installationsShape>

/** Polityka domenowa: blokery z rejestru (`lib/rules/installations.ts`). */
export const installationsSchema = installationsShape.superRefine(
  addBlockers(installationRules),
)

export type Installations = z.output<typeof installationsSchema>
export type InstallationsInput = z.input<typeof installationsShape>

/* -------------------------------------------------------------------------- */
/*  KROK 4 — Pakiet materiałowy, logistyka i checklista                        */
/* -------------------------------------------------------------------------- */

export const STYLE_PACKAGES = ['scandi', 'wloski', 'loft'] as const
export const FLOOR_PROTECTION = ['brak', 'tektura', 'hdf'] as const

export const finishAndLogisticsSchema = z.object({
  stylePackage: z.enum(STYLE_PACKAGES).nullable().default(null),
  logistics: z.object({
    elevator: optionalText,
    staircase: optionalText,
    parking: optionalText,
    floorProtection: z.enum(FLOOR_PROTECTION).default('brak'),
  }),
  checklist: z.object({
    photoDocumentation: z.boolean().default(false),
    serviceSpace: z.boolean().default(false),
    clientInformedNoChanges: z.boolean().default(false),
    drawerSystemConfirmed: z.boolean().default(false),
    sinkTemplateConfirmed: z.boolean().default(false),
    purGlueOnly: z.boolean().default(false),
  }),
  sketchNotes: z.string().trim().max(4000, 'Maksymalnie 4000 znaków').optional().default(''),
})

export type FinishAndLogistics = z.infer<typeof finishAndLogisticsSchema>
export type FinishAndLogisticsInput = z.input<typeof finishAndLogisticsSchema>

/* -------------------------------------------------------------------------- */
/*  Cały pomiar                                                                */
/* -------------------------------------------------------------------------- */

export const surveySchema = z.object({
  version: z.literal(1),
  customer: customerInfoSchema,
  geometry: roomGeometrySchema,
  installations: installationsSchema,
  finish: finishAndLogisticsSchema,
})

export type Survey = z.infer<typeof surveySchema>
export type SurveyInput = z.input<typeof surveySchema>
