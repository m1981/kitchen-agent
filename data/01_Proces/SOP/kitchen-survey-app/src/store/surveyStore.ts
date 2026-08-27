import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  defaultCustomer,
  defaultFinish,
  defaultGeometry,
  defaultInstallations,
  todayIso,
} from '@/lib/defaults'
import type {
  CustomerInfoInput,
  FinishAndLogisticsInput,
  InstallationsInput,
  RoomGeometryInput,
} from '@/lib/schema'

export const STEPS = [
  { id: 0, key: 'customer', title: 'Dane klienta', short: 'Klient' },
  { id: 1, key: 'geometry', title: 'Geometria pomieszczenia', short: 'Geometria' },
  { id: 2, key: 'installations', title: 'AGD i przyłącza', short: 'Instalacje' },
  { id: 3, key: 'finish', title: 'Pakiet i logistyka', short: 'Pakiet' },
  { id: 4, key: 'summary', title: 'Podsumowanie', short: 'Podsumowanie' },
] as const

export type StepIndex = 0 | 1 | 2 | 3 | 4

/** Surowy stan formularza (wartości wejściowe — stringi z inputów). */
export interface SurveyDraft {
  customer: CustomerInfoInput
  geometry: RoomGeometryInput
  installations: InstallationsInput
  finish: FinishAndLogisticsInput
}

interface SurveyState extends SurveyDraft {
  version: 1
  currentStep: StepIndex
  /** Kroki, które przeszły twardą walidację — sterują paskiem postępu. */
  completedSteps: number[]
  lastSavedAt: string | null

  setCustomer: (data: CustomerInfoInput) => void
  setGeometry: (data: RoomGeometryInput) => void
  setInstallations: (data: InstallationsInput) => void
  setFinish: (data: FinishAndLogisticsInput) => void
  markStepComplete: (step: number) => void
  goToStep: (step: StepIndex) => void
  next: () => void
  prev: () => void
  resetSession: () => void
}

const freshDraft = (): SurveyDraft => ({
  customer: { ...defaultCustomer, measurementDate: todayIso() },
  geometry: structuredClone(defaultGeometry),
  installations: structuredClone(defaultInstallations),
  finish: structuredClone(defaultFinish),
})

const lastStep = (STEPS.length - 1) as StepIndex

export const useSurveyStore = create<SurveyState>()(
  persist(
    (set) => ({
      version: 1,
      ...freshDraft(),
      currentStep: 0,
      completedSteps: [],
      lastSavedAt: null,

      setCustomer: (data) =>
        set({ customer: data, lastSavedAt: new Date().toISOString() }),
      setGeometry: (data) =>
        set({ geometry: data, lastSavedAt: new Date().toISOString() }),
      setInstallations: (data) =>
        set({ installations: data, lastSavedAt: new Date().toISOString() }),
      setFinish: (data) =>
        set({ finish: data, lastSavedAt: new Date().toISOString() }),

      markStepComplete: (step) =>
        set((state) =>
          state.completedSteps.includes(step)
            ? state
            : { completedSteps: [...state.completedSteps, step] },
        ),

      goToStep: (step) => set({ currentStep: step }),
      next: () =>
        set((state) => ({
          currentStep: Math.min(state.currentStep + 1, lastStep) as StepIndex,
        })),
      prev: () =>
        set((state) => ({
          currentStep: Math.max(state.currentStep - 1, 0) as StepIndex,
        })),

      resetSession: () =>
        set({
          ...freshDraft(),
          currentStep: 0,
          completedSteps: [],
          lastSavedAt: null,
        }),
    }),
    {
      name: 'kitchen-survey-draft-v1',
      version: 1,
      partialize: (state) => ({
        version: state.version,
        customer: state.customer,
        geometry: state.geometry,
        installations: state.installations,
        finish: state.finish,
        currentStep: state.currentStep,
        completedSteps: state.completedSteps,
        lastSavedAt: state.lastSavedAt,
      }),
    },
  ),
)
