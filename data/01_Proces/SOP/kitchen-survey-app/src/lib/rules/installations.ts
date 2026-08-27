import type { Path } from 'react-hook-form'
import type { Rule } from '../diagnostics.ts'
import { NORM } from '../norms.ts'
import type { InstallationsInput, InstallationsModel } from '../schema.ts'

type InstPath = Path<InstallationsInput>
type InstRule = Rule<InstallationsModel, InstPath>

const STATIC_RULES: readonly InstRule[] = [
  {
    code: 'INS-001',
    severity: 'critical',
    path: 'appliances.hob.distanceToSink',
    requires: (m) => m.appliances.hob.distanceToSink !== null,
    check: (m) => m.appliances.hob.distanceToSink! >= NORM.hobToSink,
    message: (m) =>
      `Płyta ${m.appliances.hob.distanceToSink} mm od zlewu — norma to min. ${NORM.hobToSink} mm. Przesuń moduł lub zmień układ.`,
  },
  {
    code: 'INS-002',
    severity: 'critical',
    path: 'appliances.hob.distanceToSideWall',
    requires: (m) => m.appliances.hob.distanceToSideWall !== null,
    check: (m) => m.appliances.hob.distanceToSideWall! >= NORM.hobToSideWall,
    message: (m) =>
      `Płyta ${m.appliances.hob.distanceToSideWall} mm od ściany bocznej — norma to min. ${NORM.hobToSideWall} mm.`,
  },
  {
    code: 'INS-003',
    severity: 'warning',
    path: 'appliances.hob.ventGap',
    requires: (m) => m.appliances.hob.ventGap !== null,
    check: (m) =>
      m.appliances.hob.ventGap! >= NORM.hobVentGapMin &&
      m.appliances.hob.ventGap! <= NORM.hobVentGapMax,
    message: (m) =>
      `Szczelina wentylacyjna pod indukcją ${m.appliances.hob.ventGap} mm — zalecane ${NORM.hobVentGapMin}–${NORM.hobVentGapMax} mm.`,
  },
  {
    code: 'INS-004',
    severity: 'critical',
    path: 'appliances.fridge.noHdfBack',
    check: (m) => m.appliances.fridge.noHdfBack,
    message: () =>
      'Zaznaczono plecy HDF w słupku lodówkowym — blokują komin wentylacyjny. Standard: brak pleców.',
  },
  {
    code: 'INS-005',
    severity: 'critical',
    path: 'appliances.fridge.ventGapMin50',
    check: (m) => m.appliances.fridge.ventGapMin50,
    message: () =>
      `Brak odstępu min. ${NORM.fridgeVentGap} mm od ściany za lodówką — komin wentylacyjny nie zadziała.`,
  },
  {
    code: 'INS-006',
    severity: 'critical',
    path: 'appliances.oven.noHdfBack',
    check: (m) => m.appliances.oven.noHdfBack,
    message: () =>
      'Plecy HDF w niszy piekarnika — brak odprowadzania ciepła. Standard: brak pleców.',
  },
  {
    code: 'INS-007',
    severity: 'warning',
    path: 'appliances.hob.metalTraverses',
    check: (m) => m.appliances.hob.metalTraverses,
    message: () =>
      'Brak trawersów metalowych pod blatem HPL 12 mm — wieńce płytowe nie przeniosą obciążenia płyty.',
  },
]

/**
 * Rejestr jest funkcją, bo przyłącza to tablica o zmiennej długości: reguła
 * czerwonej strefy musi zakotwiczyć się w konkretnym wierszu (`utilities.3.…`),
 * a nie w całej kolekcji.
 */
export function installationRules(
  model: InstallationsModel,
): readonly InstRule[] {
  const redZone: InstRule[] = model.utilities.map((point, index) => ({
    code: `INS-100/${point.id}`,
    severity: 'critical',
    path: `utilities.${index}.behindAppliance` as InstPath,
    check: () => !point.behindAppliance,
    message: () =>
      `Gniazdo „${point.label}" wypada za AGD — CZERWONA STREFA. Sprzęt wchodzi na ${NORM.applianceDepth} mm, wtyczka wypchnie go przed lico frontów. Przenieś do szafki sąsiedniej.`,
  }))

  return [...STATIC_RULES, ...redZone]
}
