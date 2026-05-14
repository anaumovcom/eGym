import { useQuery } from '@tanstack/react-query'
import { BookOpenText } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProgramLibraryData } from '@/entities/program/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FilterChip, ProgramCard, ProgramDetailsPanel, SearchField, SectionIntro, SupportCard } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function ProgramLibraryScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const selectedProgramId = useAppStore((state) => state.selectedProgramId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const setSelectedProgramId = useAppStore((state) => state.setSelectedProgramId)
  const setSelectedCalendarDayId = useAppStore((state) => state.setSelectedCalendarDayId)

  const selected = searchParams.get('selected') ?? selectedProgramId ?? 'back-biceps'
  const search = searchParams.get('search') ?? ''
  const [activeCategory, setActiveCategory] = useState('Все')

  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Проверка подключения...',
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['program-library', selected],
    queryFn: () => apiGet<ProgramLibraryData>(`/api/programs?selected=${encodeURIComponent(selected)}`),
  })

  const filteredPrograms = useMemo(() => {
    if (!data) {
      return []
    }

    return data.allPrograms.filter((program) => {
      const matchesSearch = !search || `${program.name} ${program.subtitle} ${program.focusTags.join(' ')}`.toLowerCase().includes(search.toLowerCase())
      const matchesCategory = activeCategory === 'Все' || program.focusTags.some((tag) => tag.toLowerCase().includes(activeCategory.toLowerCase())) || program.subtitle.toLowerCase().includes(activeCategory.toLowerCase())
      return matchesSearch && matchesCategory
    })
  }, [activeCategory, data, search])

  if (isLoading || !data) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка библиотеки программ…</div>
      </FormaShell>
    )
  }

  if (error) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить библиотеку программ. Проверьте backend API.</div>
      </FormaShell>
    )
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title="Библиотека готовых программ"
        description="Выберите готовую тренировку, адаптируйте её под себя и добавьте в календарь. Экран покрывает сценарии быстрого запуска, адаптации и назначения плана."
        actions={
          <Button variant="secondary" iconLeft={<BookOpenText className="h-4 w-4" />} onClick={() => navigate('/builder')}>
            Открыть конструктор
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <section className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-center">
              <SearchField
                value={search}
                placeholder={data.searchPlaceholder}
                onChange={(value) =>
                  setSearchParams((current) => {
                    const next = new URLSearchParams(current)
                    if (value) {
                      next.set('search', value)
                    } else {
                      next.delete('search')
                    }
                    return next
                  })
                }
              />
              <div className="text-sm text-white/45">{filteredPrograms.length} программ</div>
            </div>

            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {data.categoryFilters.map((filter) => (
                  <FilterChip key={filter} label={filter} active={activeCategory === filter} onClick={() => setActiveCategory(filter)} />
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.durationFilters.map((filter) => (
                  <FilterChip key={filter} label={filter} />
                ))}
                {data.levelFilters.map((filter) => (
                  <FilterChip key={filter} label={filter} />
                ))}
                {data.equipmentFilters.map((filter) => (
                  <FilterChip key={filter} label={filter} />
                ))}
              </div>
            </div>
          </div>

          <section>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-sm uppercase tracking-[0.24em] text-white/35">Рекомендовано для вас</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">Готовые планы</div>
              </div>
              <Button variant="ghost">Показать все</Button>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              {data.recommended.map((program) => (
                <ProgramCard
                  key={program.id}
                  program={program}
                  selected={program.id === selected}
                  onSelect={() => {
                    setSelectedProgramId(program.id)
                    setSearchParams((current) => {
                      const next = new URLSearchParams(current)
                      next.set('selected', program.id)
                      return next
                    })
                  }}
                />
              ))}
            </div>
          </section>

          <section>
            <div className="mb-4 font-display text-3xl font-bold text-white">Все программы</div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filteredPrograms.map((program) => (
                <ProgramCard
                  key={program.id}
                  program={program}
                  selected={program.id === selected}
                  onSelect={() => {
                    setSelectedProgramId(program.id)
                    setSearchParams((current) => {
                      const next = new URLSearchParams(current)
                      next.set('selected', program.id)
                      return next
                    })
                  }}
                />
              ))}
            </div>
          </section>
        </section>

        <aside className="space-y-6">
          <ProgramDetailsPanel
            details={data.selectedProgram}
            onPrimary={() => navigate('/exercise-setup?source=programs&photo=before')}
            onAdapt={() => navigate('/builder')}
            onCalendar={() => {
              setSelectedCalendarDayId('2026-05-14')
              navigate('/calendar?selectedDayId=2026-05-14')
            }}
            onBuilder={() => navigate('/builder')}
          />
          <SupportCard />
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}