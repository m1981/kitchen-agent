import type {
  CustomerInfoInput,
  FinishAndLogisticsInput,
  InstallationsInput,
  RoomGeometryInput,
} from './schema.ts'

const emptyThreePoint = () => ({
  bottom: '',
  middle: '',
  top: '',
  deviation: '',
})

export function todayIso(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export const defaultCustomer: CustomerInfoInput = {
  clientName: '',
  phone: '',
  email: '',
  address: '',
  measurementDate: todayIso(),
  plannedInstallation: '',
  budget: '',
  surveyorName: '',
}

export const defaultGeometry: RoomGeometryInput = {
  layout: 'I',
  wallA: emptyThreePoint(),
  wallB: emptyThreePoint(),
  wallC: emptyThreePoint(),
  height: emptyThreePoint(),
  cornerAngle: '',
  ceilingType: 'twardy',
  floorLevelDrop: '',
  hasBulkhead: false,
  bulkheadWidth: '',
  bulkheadHeight: '',
  bulkheadDepth: '',
  bulkheadOffsetFromLeft: '',
  hasWindow: false,
  windowSillHeight: '',
  windowSillDepth: '',
  windowAxisFromLeft: '',
  windowOpening: 'brak',
  obstacles: {
    tapWindowCollision: false,
    radiator: false,
    radiatorProtrusion: '',
    skirtingBoards: false,
    inspectionHatch: false,
    lightSwitch: false,
    intercomThermostat: false,
    chimneyShaft: false,
    wallNiche: false,
    wallNicheDepth: '',
    notes: '',
  },
}

/** Punkty przyłączy z karty pomiarowej — kolejność jak w tabeli sekcji 4. */
export const UTILITY_TEMPLATE: ReadonlyArray<{
  id: string
  label: string
  cabinet: string
  notes: string
}> = [
  {
    id: 'kanalizacja',
    label: 'Odpływ kanalizacji fi 50',
    cabinet: 'Szafka zlewozmywakowa',
    notes: 'Zmierzyć odsadzenie syfonu / rur',
  },
  {
    id: 'woda',
    label: 'Zawory wody ZW / CW',
    cabinet: 'Szafka zlewozmywakowa',
    notes: 'Sprawdzić podejście pod zmywarkę',
  },
  {
    id: 'sila-400v',
    label: 'Gniazdo Siła / Płyta (400V)',
    cabinet: 'Szafka sąsiednia',
    notes: 'Długość kabla przyłączeniowego',
  },
  {
    id: 'piekarnik-230v',
    label: 'Gniazdo Piekarnika (230V)',
    cabinet: 'Szafka obok',
    notes: 'NIE ZA PIEKARNIKIEM — wycięcie w HDF',
  },
  {
    id: 'zmywarka-230v',
    label: 'Gniazdo Zmywarki (230V)',
    cabinet: 'Szafka zlewowa',
    notes: 'NIE ZA ZMYWARKĄ — dostęp bez demontażu',
  },
  {
    id: 'lodowka-230v',
    label: 'Gniazdo Lodówki (230V)',
    cabinet: 'Cokół / wieniec górny',
    notes: 'NIE BEZPOŚREDNIO ZA AGD',
  },
  {
    id: 'led-loox',
    label: 'Zasilacz LED Häfele Loox5',
    cabinet: 'Wieniec górny / blenda',
    notes: 'Zapewnić wentylację i dostęp serwisowy',
  },
  {
    id: 'led-230v',
    label: 'Kabel oświetleniowy (LED 230V)',
    cabinet: 'Szafki wiszące',
    notes: 'Gdzie wyprowadzony ze ściany?',
  },
  {
    id: 'wodomierze',
    label: 'Wodomierze / filtry wody',
    cabinet: 'Szafka zlewozmywakowa',
    notes: 'Kolizja z koszem na odpady?',
  },
  {
    id: 'gniazda-blat',
    label: 'Gniazda robocze nad blatem',
    cabinet: 'Panel ścienny HPL',
    notes: 'Otwornica CNC w panelu HPL',
  },
]

export const defaultInstallations: InstallationsInput = {
  appliances: {
    fridge: {
      frontSystem: 'suwakowy',
      noHdfBack: true,
      ventGapMin50: true,
      inletGrille: true,
      outletGrille: true,
      visibleSideFrontMaterial: true,
      model: '',
      nicheHeight: '',
    },
    oven: {
      placement: 'slupek',
      noHdfBack: true,
      thermalShields: true,
      socketInNeighbourCabinet: true,
      model: '',
    },
    hob: {
      power: '400V',
      ventGap: '',
      metalTraverses: true,
      distanceToSink: '',
      distanceToSideWall: '',
      model: '',
    },
    dishwasher: {
      width: '60',
      varioHinge: false,
      steamProtectionStrip: true,
    },
    hood: {
      type: 'wyciag',
      ductAxisX: '',
      ductHeightY: '',
      ductDiameter: '',
    },
  },
  utilities: UTILITY_TEMPLATE.map((point) => ({
    id: point.id,
    label: point.label,
    x: '',
    y: '',
    cabinet: point.cabinet,
    notes: point.notes,
    behindAppliance: false,
  })),
}

export const defaultFinish: FinishAndLogisticsInput = {
  stylePackage: null,
  logistics: {
    elevator: '',
    staircase: '',
    parking: '',
    floorProtection: 'brak',
  },
  checklist: {
    photoDocumentation: false,
    serviceSpace: false,
    clientInformedNoChanges: false,
    drawerSystemConfirmed: false,
    sinkTemplateConfirmed: false,
    purGlueOnly: false,
  },
  sketchNotes: '',
}
