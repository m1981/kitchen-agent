/**
 * Szybki test schematów i rejestru reguł — bez przeglądarki i bez frameworka.
 *   node --experimental-strip-types scripts/check-schema.ts
 *
 * Reguły operują na modelu, nie na formularzu, więc dają się sprawdzić tabelą
 * przypadków: model → oczekiwane kody diagnostyk.
 */
import { runRules } from '../src/lib/diagnostics.ts'
import { GEOMETRY_RULES } from '../src/lib/rules/geometry.ts'
import { installationRules } from '../src/lib/rules/installations.ts'
import {
  customerInfoSchema,
  installationsShape,
  roomGeometryShape,
  roomGeometrySchema,
} from '../src/lib/schema.ts'
import {
  defaultCustomer,
  defaultGeometry,
  defaultInstallations,
} from '../src/lib/defaults.ts'

let failures = 0
function check(name: string, actual: unknown, expected: unknown) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) failures++
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}`)
  if (!ok) console.log(`        oczekiwano ${JSON.stringify(expected)}, jest ${JSON.stringify(actual)}`)
}

const geometry = (overrides: Record<string, unknown>) =>
  roomGeometryShape.parse({ ...defaultGeometry, ...overrides })

const codes = (model: ReturnType<typeof geometry>) =>
  runRules(model, GEOMETRY_RULES).map((d) => d.code)

/* --- krok 1: walidacja pól --- */
console.log('\nKROK 1 — dane klienta')
check(
  'pusty formularz zgłasza braki',
  customerInfoSchema.safeParse(defaultCustomer).success,
  false,
)
check(
  'komplet danych przechodzi',
  customerInfoSchema.safeParse({
    ...defaultCustomer,
    clientName: 'Jan Kowalski',
    phone: '+48 600 100 200',
    address: 'Wrocław, Jagodno 12',
  }).success,
  true,
)

/* --- krok 2: auto-kalkulacje --- */
console.log('\nKROK 2 — auto-kalkulacje')
const measured = geometry({
  wallA: { bottom: '2500', middle: '2510', top: '2490', deviation: '3' },
  height: { bottom: '2620', middle: '2618', top: '2630', deviation: '' },
})
check('min do CAD = najmniejszy z trzech punktów', measured.wallA.min, 2490)
check('rozrzut pomiaru', measured.wallA.spread, 20)
check('max wysokość słupka = H min − 30', measured.maxColumnHeight, 2588)

/* --- krok 2: rejestr reguł --- */
console.log('\nKROK 2 — reguły geometrii')
check('pusty formularz: same blokery braków', codes(geometry({})), ['GEO-001', 'GEO-004'])
check(
  'gating — brak kąta nie zapala GEO-010',
  codes(geometry({ cornerAngle: '' })).includes('GEO-010'),
  false,
)
check(
  'kąt 85° zapala ostrzeżenie miękkie',
  codes(measuredWith({ cornerAngle: '85' })).includes('GEO-010'),
  true,
)
check(
  'układ U bez ścian bocznych blokuje',
  codes(geometry({ layout: 'U' })).filter((c) => c === 'GEO-002' || c === 'GEO-003'),
  ['GEO-002', 'GEO-003'],
)
check(
  'kaskada — bloker gasi ostrzeżenie o rozrzucie tej samej ściany',
  codes(geometry({ wallA: { bottom: '', middle: '', top: '', deviation: '' } })).includes('GEO-011'),
  false,
)
const lowSill = codes(
  measuredWith({ hasWindow: true, windowSillHeight: '860', windowAxisFromLeft: '1200' }),
)
check('parapet poniżej blatu zapala GEO-018', lowSill.includes('GEO-018'), true)
check(
  'kaskada — GEO-018 gasi następcze GEO-019',
  lowSill.includes('GEO-019'),
  false,
)
check(
  'blokery trafiają do resolvera jako błędy pól',
  roomGeometrySchema
    .safeParse({ ...defaultGeometry, layout: 'L' })
    .error?.issues.map((i) => i.path.join('.'))
    .sort(),
  ['height.bottom', 'wallA.bottom', 'wallB.bottom'],
)

/* --- krok 3: reguły instalacji --- */
console.log('\nKROK 3 — reguły AGD i przyłączy')
const installations = (mutate: (draft: typeof defaultInstallations) => void) => {
  const draft = structuredClone(defaultInstallations)
  mutate(draft)
  const model = installationsShape.parse(draft)
  return runRules(model, installationRules(model)).map((d) => d.code)
}
check('domyślne ustawienia są zgodne z normą', installations(() => {}), [])
check(
  'płyta 250 mm od zlewu łamie normę 300 mm',
  installations((d) => {
    d.appliances.hob.distanceToSink = '250'
  }),
  ['INS-001'],
)
check(
  'gniazdo za AGD to czerwona strefa',
  installations((d) => {
    d.utilities[3].behindAppliance = true
  }),
  ['INS-100/piekarnik-230v'],
)

/** Pomiar bazowy + nadpisania — wygodny skrót dla przypadków testowych. */
function measuredWith(overrides: Record<string, unknown>) {
  return geometry({
    wallA: { bottom: '2500', middle: '2510', top: '2490', deviation: '' },
    wallB: { bottom: '1800', middle: '1800', top: '1800', deviation: '' },
    height: { bottom: '2620', middle: '2620', top: '2620', deviation: '' },
    ...overrides,
  })
}

console.log(failures === 0 ? '\nWszystko przeszło.\n' : `\n${failures} niepowodzeń.\n`)
process.exitCode = failures === 0 ? 0 : 1
