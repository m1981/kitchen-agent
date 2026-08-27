/**
 * Liczby z normy warsztatowej — jedyne miejsce, w którym żyją progi domenowe.
 *
 * Reguła i treść jej komunikatu czytają tę samą stałą, więc zmiana progu nie
 * może rozjechać się z tekstem ostrzeżenia. Źródło: karta pomiarowa Etap 1.1
 * (standard prefabrykacji CNC, Intar Wrocław).
 *
 * Patrz: docs/adr/0008-normy-jako-dane.md
 */

/** Twarde wytyczne montażowe i wentylacyjne. */
export const NORM = {
  /** Luz słupka pod sufit: przekątna przy stawianiu + blenda górna. */
  columnClearance: 30,
  /** Minimalna blenda maskująca przy prostej ścianie. */
  minFiller: 30,
  /** Blenda w narożniku przy kącie innym niż prosty. */
  cornerFiller: 50,
  /** Komin wentylacyjny za lodówką do zabudowy. */
  fridgeVentGap: 50,
  /** Przekrój kratki wlotowej w cokole i wylotowej w wieńcu [cm²]. */
  fridgeGrilleArea: 200,
  /** Szczelina wentylacyjna pod płytą indukcyjną. */
  hobVentGapMin: 5,
  hobVentGapMax: 20,
  /** Odstęp płyty od zlewu — rozdzielenie strefy mokrej i grzewczej. */
  hobToSink: 300,
  /** Odstęp płyty od ściany bocznej. */
  hobToSideWall: 300,
  /** Przestrzeń serwisowa za szafkami dolnymi na ominięcie rur. */
  serviceSpaceMin: 50,
  serviceSpaceMax: 70,
  /** Głębokość zabudowy AGD — powód zakazu gniazdek za sprzętem. */
  applianceDepth: 550,
} as const

/**
 * Heurystyki warsztatowe — progi, przy których zapala się ostrzeżenie miękkie.
 * To nie są normy, tylko doświadczenie: „powyżej tej wartości sprawdź dwa razy".
 */
export const THRESHOLD = {
  /** Odchyłka kąta od 90°, powyżej której traktujemy narożnik jako krzywy. */
  cornerAngleTolerance: 1,
  /** Rozrzut pomiaru 3-punktowego ściany. */
  wallSpreadWarning: 10,
  wallSpreadCritical: 25,
  /** Rozrzut wysokości pomieszczenia (nierówny sufit lub posadzka). */
  heightSpreadWarning: 15,
  /** Wysokość, poniżej której układ słupków i okapu wymaga weryfikacji. */
  lowCeiling: 2400,
  /** Spadek posadzki, powyżej którego zwykłe nóżki nie wystarczą. */
  floorDropWarning: 10,
  /** Nominalna wysokość blatu roboczego. */
  worktopHeight: 900,
  /** Wysokość parapetu, poniżej której brakuje miejsca na panel HPL i gniazda. */
  tightSillHeight: 1000,
  /** Rozrzut, powyżej którego blenda idzie od razu na wymiar narożnikowy. */
  fillerJumpToCorner: 20,
} as const
