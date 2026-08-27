import { ArrowLeft, Download, Printer } from 'lucide-react'
import { useMemo } from 'react'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import { formatMm } from '@/lib/calc'
import { downloadJson, exportFileName, parseSurvey } from '@/lib/export'
import { STYLE_PACKAGE_DETAILS } from '@/lib/stylePackages'
import { useSurveyStore } from '@/store/surveyStore'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-100 py-1.5 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">
        {value || '—'}
      </span>
    </div>
  )
}

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="print-avoid-break">
      <h3 className="mb-1 border-l-4 border-brand-500 bg-slate-100 px-2 py-1 text-xs font-bold tracking-wide text-slate-900 uppercase">
        {title}
      </h3>
      <div className="px-1">{children}</div>
    </div>
  )
}

const LAYOUT_LABEL = { I: 'I — jednorzędowa', L: 'L — narożna', U: 'U — podkowa' }
const YES_NO = (value: boolean) => (value ? 'TAK' : 'NIE')

export function Step5Summary() {
  // Selektory per-pole: zustand v5 wymaga stabilnych referencji.
  const customerDraft = useSurveyStore((state) => state.customer)
  const geometryDraft = useSurveyStore((state) => state.geometry)
  const installationsDraft = useSurveyStore((state) => state.installations)
  const finishDraft = useSurveyStore((state) => state.finish)
  const prev = useSurveyStore((state) => state.prev)

  const parsed = useMemo(
    () =>
      parseSurvey({
        customer: customerDraft,
        geometry: geometryDraft,
        installations: installationsDraft,
        finish: finishDraft,
      }),
    [customerDraft, geometryDraft, installationsDraft, finishDraft],
  )

  if (!parsed.ok) {
    return (
      <Card>
        <CardHeader
          title="Podsumowanie — brakuje danych"
          accent="red"
          description="Uzupełnij poniższe pola, żeby wygenerować kartę i plik JSON."
        />
        <CardBody>
          <Alert severity="critical">
            <ul className="list-inside list-disc space-y-1">
              {parsed.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </Alert>
          <Button variant="secondary" onClick={prev}>
            <ArrowLeft className="size-4" aria-hidden />
            Wróć i popraw
          </Button>
        </CardBody>
      </Card>
    )
  }

  const survey = parsed.data
  const { customer, geometry, installations, finish } = survey
  const stylePackage = finish.stylePackage
    ? STYLE_PACKAGE_DETAILS[finish.stylePackage]
    : null

  return (
    <div className="space-y-4">
      <div className="no-print flex flex-wrap gap-3">
        <Button
          onClick={() =>
            downloadJson(
              survey,
              exportFileName(customer.clientName, customer.measurementDate),
            )
          }
        >
          <Download className="size-4" aria-hidden />
          Pobierz dane (JSON)
        </Button>
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden />
          Drukuj / zapisz PDF
        </Button>
        <Button variant="ghost" onClick={prev}>
          <ArrowLeft className="size-4" aria-hidden />
          Wstecz
        </Button>
      </div>

      <Card className="print-page">
        <div className="border-b border-slate-200 px-4 py-3 text-center">
          <h1 className="text-base font-bold tracking-wide text-brand-900 uppercase">
            Karta pomiaru i inwentaryzacji zabudowy kuchennej
          </h1>
          <p className="text-xs text-slate-500">
            Etap 1.1 · Standard prefabrykacji CNC (Shift-Left) · Bounding Box
          </p>
        </div>

        <CardBody className="space-y-5">
          <Section title="1. Dane klienta i inwestycji">
            <Row label="Inwestor" value={customer.clientName} />
            <Row label="Telefon" value={customer.phone} />
            <Row label="E-mail" value={customer.email} />
            <Row label="Adres inwestycji" value={customer.address} />
            <Row label="Data pomiaru" value={customer.measurementDate} />
            <Row
              label="Planowany montaż"
              value={customer.plannedInstallation}
            />
            <Row label="Budżet" value={customer.budget} />
            <Row label="Pomiar wykonał" value={customer.surveyorName} />
          </Section>

          <Section title="2. Geometria — wymiary do CAD">
            <Row label="Układ zabudowy" value={LAYOUT_LABEL[geometry.layout]} />
            <Row
              label="Ściana A — min (do CAD)"
              value={formatMm(geometry.wallA.min)}
            />
            <Row
              label="Ściana B — min"
              value={formatMm(geometry.wallB.min)}
            />
            <Row
              label="Ściana C — min"
              value={formatMm(geometry.wallC.min)}
            />
            <Row
              label="Wysokość H — min"
              value={formatMm(geometry.height.min)}
            />
            <Row
              label="Max wysokość słupka (H − 30 mm)"
              value={formatMm(geometry.maxColumnHeight)}
            />
            <Row
              label="Kąt w narożniku"
              value={
                geometry.cornerAngle === null ? '—' : `${geometry.cornerAngle}°`
              }
            />
            <Row
              label="Rodzaj sufitu"
              value={
                geometry.ceilingType === 'podwieszany'
                  ? 'Podwieszany (karton-gips)'
                  : 'Twardy (beton / tynk)'
              }
            />
            <Row
              label="Spadek posadzki"
              value={formatMm(geometry.floorLevelDrop)}
            />
            {geometry.hasWindow ? (
              <>
                <Row
                  label="Okno — wys. parapetu"
                  value={formatMm(geometry.windowSillHeight)}
                />
                <Row
                  label="Okno — oś od lewej"
                  value={formatMm(geometry.windowAxisFromLeft)}
                />
                <Row
                  label="Okno — głębokość parapetu"
                  value={formatMm(geometry.windowSillDepth)}
                />
                <Row label="Okno — otwieranie" value={geometry.windowOpening} />
              </>
            ) : null}
            {geometry.hasBulkhead ? (
              <Row
                label="Podciąg (szer. × wys. × gł.)"
                value={`${formatMm(geometry.bulkheadWidth)} × ${formatMm(
                  geometry.bulkheadHeight,
                )} × ${formatMm(geometry.bulkheadDepth)}`}
              />
            ) : null}
          </Section>

          <Section title="2b. Przeszkody">
            <Row
              label="Kolizja baterii z oknem"
              value={YES_NO(geometry.obstacles.tapWindowCollision)}
            />
            <Row
              label="Grzejnik"
              value={
                geometry.obstacles.radiator
                  ? `TAK — odstaje ${formatMm(geometry.obstacles.radiatorProtrusion)}`
                  : 'NIE'
              }
            />
            <Row
              label="Drzwiczki rewizyjne"
              value={YES_NO(geometry.obstacles.inspectionHatch)}
            />
            <Row
              label="Szacht kominowy"
              value={YES_NO(geometry.obstacles.chimneyShaft)}
            />
            <Row
              label="Wnęka w ścianie"
              value={
                geometry.obstacles.wallNiche
                  ? `TAK — gł. ${formatMm(geometry.obstacles.wallNicheDepth)}`
                  : 'NIE'
              }
            />
            {geometry.obstacles.notes ? (
              <p className="mt-2 rounded bg-slate-50 p-2 text-sm whitespace-pre-wrap text-slate-700">
                {geometry.obstacles.notes}
              </p>
            ) : null}
          </Section>

          <Section title="3. AGD i wentylacja">
            <Row
              label="Lodówka — system frontu"
              value={
                installations.appliances.fridge.frontSystem === 'suwakowy'
                  ? 'Suwakowy (Blum 155°)'
                  : 'Door-on-Door'
              }
            />
            <Row
              label="Lodówka — model / nisza"
              value={`${installations.appliances.fridge.model} ${formatMm(
                installations.appliances.fridge.nicheHeight,
              )}`}
            />
            <Row
              label="Piekarnik"
              value={
                installations.appliances.oven.placement === 'slupek'
                  ? 'W słupku wysokim'
                  : 'W szafce pod blatem'
              }
            />
            <Row
              label="Płyta — zasilanie"
              value={installations.appliances.hob.power}
            />
            <Row
              label="Płyta — odstępy (zlew / ściana)"
              value={`${formatMm(installations.appliances.hob.distanceToSink)} / ${formatMm(installations.appliances.hob.distanceToSideWall)}`}
            />
            <Row
              label="Zmywarka"
              value={`${installations.appliances.dishwasher.width} cm${
                installations.appliances.dishwasher.varioHinge
                  ? ' · VarioHinge'
                  : ''
              }`}
            />
            <Row
              label="Okap"
              value={
                installations.appliances.hood.type === 'wyciag'
                  ? `Wyciąg — X ${formatMm(installations.appliances.hood.ductAxisX)}, Y ${formatMm(installations.appliances.hood.ductHeightY)}, fi ${formatMm(installations.appliances.hood.ductDiameter)}`
                  : 'Pochłaniacz (filtry węglowe)'
              }
            />
          </Section>

          <Section title="4. Przyłącza — osie X / Y">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-100 text-left">
                    <th className="border border-slate-300 px-2 py-1">Punkt</th>
                    <th className="border border-slate-300 px-2 py-1">X</th>
                    <th className="border border-slate-300 px-2 py-1">Y</th>
                    <th className="border border-slate-300 px-2 py-1">
                      Szafka / uwagi
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {installations.utilities.map((point) => (
                    <tr
                      key={point.id}
                      className={point.behindAppliance ? 'bg-red-50' : undefined}
                    >
                      <td className="border border-slate-300 px-2 py-1 font-medium">
                        {point.label}
                      </td>
                      <td className="border border-slate-300 px-2 py-1 tabular-nums">
                        {formatMm(point.x)}
                      </td>
                      <td className="border border-slate-300 px-2 py-1 tabular-nums">
                        {formatMm(point.y)}
                      </td>
                      <td className="border border-slate-300 px-2 py-1 text-slate-600">
                        {point.cabinet}
                        {point.notes ? ` — ${point.notes}` : ''}
                        {point.behindAppliance
                          ? ' — ⚠ GNIAZDO ZA AGD, DO PRZENIESIENIA'
                          : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section title="5. Pakiet materiałowy i logistyka">
            <Row
              label="Pakiet"
              value={stylePackage ? stylePackage.name : 'Nie wybrano'}
            />
            {stylePackage
              ? stylePackage.lines.map((line) => (
                  <p key={line} className="py-0.5 text-xs text-slate-600">
                    • {line}
                  </p>
                ))
              : null}
            <Row label="Winda" value={finish.logistics.elevator} />
            <Row label="Klatka / drzwi" value={finish.logistics.staircase} />
            <Row label="Parking" value={finish.logistics.parking} />
            <Row
              label="Ochrona posadzki"
              value={
                { brak: 'Nie wymagana', tektura: 'Tektura falista', hdf: 'Płyty HDF' }[
                  finish.logistics.floorProtection
                ]
              }
            />
          </Section>

          <Section title="6. Checklista">
            <Row
              label="Dokumentacja foto"
              value={YES_NO(finish.checklist.photoDocumentation)}
            />
            <Row
              label="Przestrzeń serwisowa 50–70 mm"
              value={YES_NO(finish.checklist.serviceSpace)}
            />
            <Row
              label="Klient poinformowany o braku zmian po CNC"
              value={YES_NO(finish.checklist.clientInformedNoChanges)}
            />
            <Row
              label="System szuflad wybrany"
              value={YES_NO(finish.checklist.drawerSystemConfirmed)}
            />
            <Row
              label="Zlew + szablon MDF"
              value={YES_NO(finish.checklist.sinkTemplateConfirmed)}
            />
            <Row
              label="Klej PUR"
              value={YES_NO(finish.checklist.purGlueOnly)}
            />
            {finish.sketchNotes ? (
              <p className="mt-2 rounded bg-slate-50 p-2 text-sm whitespace-pre-wrap text-slate-700">
                {finish.sketchNotes}
              </p>
            ) : null}
          </Section>

          <div className="flex justify-between gap-6 border-t border-slate-300 pt-8 text-center text-xs text-slate-500 print-avoid-break">
            <div className="w-5/12 border-t border-dotted border-slate-400 pt-1">
              Data i podpis inwestora
            </div>
            <div className="w-5/12 border-t border-dotted border-slate-400 pt-1">
              Podpis projektanta / wykonawcy
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
