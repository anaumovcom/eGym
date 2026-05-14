import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'
import { mockMachineHealth } from '@/mocks/data'

export function PlaceholderScreen({ title }: { title: string }) {
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)

  return (
    <FormaShell userName="Алексей" machine={mockMachineHealth} onStop={() => setEmergencyStopActive(true)}>
      <section className="glass-panel flex min-h-[70vh] flex-col items-center justify-center rounded-[36px] p-10 text-center">
        <div className="text-sm uppercase tracking-[0.3em] text-white/35">Stage 1 routing</div>
        <h1 className="font-display text-6xl font-bold tracking-[-0.08em] text-white">{title}</h1>
        <p className="mt-4 max-w-2xl text-lg leading-8 text-white/60">
          Экран уже включён в навигационный shell первого этапа. Полная функциональность будет добавляться на следующих этапах, но маршрутизация и общие состояния доступны уже сейчас.
        </p>
        <Button className="mt-6">Вернуться к сценарию этапа 1</Button>
      </section>
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}