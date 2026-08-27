import { zodResolver } from '@hookform/resolvers/zod'
import { UserRound } from 'lucide-react'
import { useCallback } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { StepNav } from '@/components/StepNav'
import { Alert } from '@/components/ui/alert'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import { Field, Input } from '@/components/ui/field'
import { useAutosave } from '@/lib/useAutosave'
import {
  customerInfoSchema,
  type CustomerInfoInput,
} from '@/lib/schema'
import { useSurveyStore } from '@/store/surveyStore'

export function Step1Customer() {
  const customer = useSurveyStore((state) => state.customer)
  const setCustomer = useSurveyStore((state) => state.setCustomer)
  const markStepComplete = useSurveyStore((state) => state.markStepComplete)
  const next = useSurveyStore((state) => state.next)

  const form = useForm<CustomerInfoInput>({
    resolver: zodResolver(customerInfoSchema),
    defaultValues: customer,
    mode: 'onTouched',
  })

  const { register, handleSubmit, watch } = form

  const save = useCallback(
    (values: CustomerInfoInput) => setCustomer(values),
    [setCustomer],
  )
  useAutosave(watch, save)

  const onSubmit = handleSubmit((values) => {
    setCustomer(values as unknown as CustomerInfoInput)
    markStepComplete(0)
    next()
  })

  const futureDate =
    !!watch('measurementDate') &&
    new Date(`${watch('measurementDate')}T00:00:00`).getTime() > Date.now()

  return (
    <FormProvider {...form}>
      <form onSubmit={onSubmit} noValidate>
      <Card>
        <CardHeader
          title="1. Dane klienta i inwestycji"
          description="Dane trafiają na kartę pomiarową i do nazwy pliku eksportu."
          icon={<UserRound className="size-5" aria-hidden />}
        />
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              name="clientName"
              label="Klient / Inwestor"
              required
              className="sm:col-span-2"
            >
              <Input
                {...register('clientName')}
                placeholder="Imię i nazwisko"
                autoComplete="name"
              />
            </Field>

            <Field name="phone" label="Telefon" required>
              <Input
                {...register('phone')}
                type="tel"
                inputMode="tel"
                placeholder="+48 600 000 000"
                autoComplete="tel"
              />
            </Field>

            <Field name="email" label="E-mail">
              <Input
                {...register('email')}
                type="email"
                inputMode="email"
                placeholder="klient@example.com"
                autoComplete="email"
              />
            </Field>

            <Field
              name="address"
              label="Adres inwestycji / osiedle"
              required
              className="sm:col-span-2"
            >
              <Input
                {...register('address')}
                placeholder="np. Wrocław, Jagodno, ul. Vivaldiego 12/34"
              />
            </Field>

            <Field
              name="measurementDate"
              label="Data pomiaru"
              required
            >
              <Input
                {...register('measurementDate')}
                type="date"
              />
            </Field>

            <Field
              name="plannedInstallation"
              label="Planowany termin montażu"
              hint="Tekstowo — np. „4–5 tygodni od akceptacji projektu”."
            >
              <Input
                {...register('plannedInstallation')}
                placeholder="np. 4–5 tygodni"
              />
            </Field>

            <Field name="budget" label="Założony budżet klienta">
              <Input {...register('budget')} placeholder="np. 14 000 – 18 000 zł" />
            </Field>

            <Field
              name="surveyorName"
              label="Pomiar wykonał"
              hint="Podpis wykonawcy na wydruku."
            >
              <Input {...register('surveyorName')} placeholder="Imię i nazwisko" />
            </Field>
          </div>

          {futureDate ? (
            <Alert severity="warning">
              Data pomiaru jest w przyszłości — sprawdź, czy to nie literówka.
            </Alert>
          ) : null}
        </CardBody>
        <StepNav showBack={false} nextLabel="Dalej: geometria" />
      </Card>
      </form>
    </FormProvider>
  )
}
