import './exercise-technique-steps.css'

export function ExerciseTechniqueSteps({ steps, title = 'Как выполнять' }: { steps: string[]; title?: string }) {
  return (
    <section className="rt-technique-steps" aria-label={title}>
      <h3>{title}</h3>
      <ol>
        {steps.map((step, index) => <li key={index}>{step}</li>)}
      </ol>
    </section>
  )
}
