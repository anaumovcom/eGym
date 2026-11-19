import { Activity, Archive, Award, BookOpen, CalendarDays, Compass, Dumbbell, Fingerprint, Layers2, Route, Undo2 } from 'lucide-react'

const symbols = {
  journal: BookOpen, calendar: CalendarDays, return: Undo2, discovery: Compass, duet: Layers2,
  signature: Fingerprint, program: Route, exercise: Dumbbell, muscle: Activity, archive: Archive,
}

export function CollectionSymbol({ group }: { group: string }) {
  const Icon = symbols[group as keyof typeof symbols] ?? Award
  return <Icon aria-hidden="true" />
}
