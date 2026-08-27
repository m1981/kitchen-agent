import { useEffect } from 'react'
import type { FieldValues, UseFormWatch } from 'react-hook-form'

/**
 * Auto-save (Offline-First): każda zmiana inputa ląduje w zustandzie,
 * a middleware `persist` zrzuca ją do LocalStorage. Odświeżenie strony
 * odtwarza draft dokładnie tam, gdzie stolarz przerwał.
 */
export function useAutosave<T extends FieldValues>(
  watch: UseFormWatch<T>,
  save: (values: T) => void,
) {
  useEffect(() => {
    const subscription = watch((values) => {
      save(values as T)
    })
    return () => subscription.unsubscribe()
  }, [watch, save])
}
