import { zodResolver } from '@hookform/resolvers/zod'
import { UserRound } from 'lucide-react'
import { useCallback } from 'react'
import { useForm } from 'react-hook-form'
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

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = form

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
              label="Klient / Inwestor"
              required
              error={errors.clientName?.message}
              className="sm:col-span-2"
            >
              <Input
                {...register('clientName')}
                placeholder="Imię i nazwisko"
                autoComplete="name"
                invalid={!!errors.clientName}
              />
            </Field>

            <Field label="Telefon" required error={errors.phone?.message}>
              <Input
                {...register('phone')}
                type="tel"
                inputMode="tel"
                placeholder="+48 600 000 000"
                autoComplete="tel"
                invalid={!!errors.phone}
              />
            </Field>

            <Field label="E-mail" error={errors.email?.message}>
              <Input
                {...register('email')}
                type="email"
                inputMode="email"
                placeholder="klient@example.com"
                autoComplete="email"
                invalid={!!errors.email}
              />
            </Field>

            <Field
              label="Adres inwestycji / osiedle"
              required
              error={errors.address?.message}
              className="sm:col-span-2"
            >
              <Input
                {...register('address')}
                placeholder="np. Wrocław, Jagodno, ul. Vivaldiego 12/34"
                invalid={!!errors.address}
              />
            </Field>

            <Field
              label="Data pomiaru"
              required
              error={errors.measurementDate?.message}
            >
              <Input
                {...register('measurementDate')}
                type="date"
                invalid={!!errors.measurementDate}
              />
            </Field>

            <Field
              label="Planowany termin montażu"
              hint="Tekstowo — np. „4–5 tygodni od akceptacji projektu”."
              error={errors.plannedInstallation?.message}
            >
              <Input
                {...register('plannedInstallation')}
                placeholder="np. 4–5 tygodni"
              />
            </Field>

            <Field label="Założony budżet klienta" error={errors.budget?.message}>
              <Input {...register('budget')} placeholder="np. 14 000 – 18 000 zł" />
            </Field>

            <Field
              label="Pomiar wykonał"
              hint="Podpis wykonawcy na wydruku."
              error={errors.surveyorName?.message}
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
  )
}
