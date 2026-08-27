import { customerInfoSchema, roomGeometrySchema } from '../src/lib/schema.ts'
import { computeMinDimension, geometryWarnings } from '../src/lib/calc.ts'
import { defaultCustomer, defaultGeometry } from '../src/lib/defaults.ts'

const bad = customerInfoSchema.safeParse(defaultCustomer)
console.log('pusty klient -> ok?', bad.success, bad.success ? '' : bad.error.issues.map((i) => i.path.join('.') + ': ' + i.message))

const good = customerInfoSchema.safeParse({
  ...defaultCustomer,
  clientName: 'Jan Kowalski',
  phone: '+48 600 100 200',
  address: 'Wrocław, Jagodno 12',
})
console.log('poprawny klient ->', good.success, good.success ? good.data : good.error.issues)

const geo = roomGeometrySchema.safeParse({
  ...defaultGeometry,
  layout: 'L',
  wallA: { bottom: '2500', middle: '2510', top: '2490', deviation: '3' },
  wallB: { bottom: '1800', middle: '1802', top: '1799', deviation: '' },
  height: { bottom: '2620', middle: '2618', top: '2630', deviation: '-4' },
  cornerAngle: '85',
  hasWindow: true,
  windowSillHeight: '860',
  windowAxisFromLeft: '1200',
})
console.log('geometria ->', geo.success)
if (geo.success) {
  console.log('  wallA.min =', geo.data.wallA.min, '(oczekiwane 2490)')
  console.log('  wallA.spread =', geo.data.wallA.spread, '(oczekiwane 20)')
  console.log('  height.min =', geo.data.height.min, 'maxColumnHeight =', geo.data.maxColumnHeight, '(oczekiwane 2618 / 2588)')
} else {
  console.log(geo.error.issues.map((i) => i.path.join('.') + ': ' + i.message))
}

const missingB = roomGeometrySchema.safeParse({
  ...defaultGeometry,
  layout: 'U',
  wallA: { bottom: '2500', middle: '', top: '', deviation: '' },
  height: { bottom: '2600', middle: '', top: '', deviation: '' },
})
console.log('układ U bez ścian B/C -> blokada?', !missingB.success, missingB.success ? '' : missingB.error.issues.map((i) => i.path.join('.')))

console.log('min z pustych ->', computeMinDimension(['', '', '']))
console.log(
  'soft warnings ->',
  geometryWarnings({
    wallASpread: 20, wallBSpread: null, wallCSpread: null,
    heightMin: 2618, heightSpread: 12, cornerAngle: 85, floorLevelDrop: 14,
    ceilingType: 'podwieszany', hasWindow: true, windowSillHeight: 860,
    tapWindowCollision: false,
  }).map((w) => w.severity + ': ' + w.message),
)
