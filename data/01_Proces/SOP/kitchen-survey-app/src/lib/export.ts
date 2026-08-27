import { surveySchema, type Survey } from './schema.ts'
import type { SurveyDraft } from '@/store/surveyStore'

/** „Jan Kowalski” → „kowalski”; bez polskich znaków, bezpieczne w nazwie pliku. */
export function slugifyClient(name: string): string {
  const trimmed = name.trim()
  if (trimmed === '') return 'bez-nazwy'
  const parts = trimmed.split(/\s+/)
  const surname = parts[parts.length - 1] ?? trimmed
  return surname
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ł/gi, 'l')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export function exportFileName(clientName: string, date: string): string {
  return `pomiar_${slugifyClient(clientName)}_${date}.json`
}

export type ParsedSurvey =
  | { ok: true; data: Survey }
  | { ok: false; issues: string[] }

/**
 * Waliduje cały draft i zwraca dane wyjściowe (z wyliczonym `min`,
 * `spread`, `maxColumnHeight`) — to właśnie ląduje w pliku JSON.
 */
export function parseSurvey(draft: SurveyDraft): ParsedSurvey {
  const result = surveySchema.safeParse({ version: 1, ...draft })
  if (result.success) return { ok: true, data: result.data }
  return {
    ok: false,
    issues: result.error.issues.map(
      (issue) => `${issue.path.join('.') || 'formularz'}: ${issue.message}`,
    ),
  }
}

export function downloadJson(data: unknown, fileName: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
