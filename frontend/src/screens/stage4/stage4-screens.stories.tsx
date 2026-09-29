import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useLayoutEffect, useState } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { buildFatigueData, buildProgressData, fatigueModes, getProfileSeed, stage4Periods } from '@/mocks/stage4-data'
import { UserProfileScreen } from '@/screens/profile/user-profile-screen'
import { FatigueScreen } from '@/screens/fatigue/fatigue-screen'
import { ProgressScreen } from '@/screens/progress/progress-screen'
import { SystemSettingsScreen } from '@/screens/settings/system-settings-screen'
import { SettingsLayout } from '@/shared/ui/layout/service-access'
import { useAppStore } from '@/stores/app-store'
import { useStage4Store } from '@/stores/stage4-store'

const meta = {
  title: 'Screens/Stage 4',
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

function prepareState(userId: 'alexey' | 'elena' | 'guest' = 'alexey', devPatch: Partial<ReturnType<typeof useStage4Store.getState>['dev']> = {}) {
  useAppStore.setState({
    selectedUserId: userId,
    selectedExerciseSlug: 'machine-pulldown',
    selectedProgramId: 'back-biceps',
    selectedCalendarDayId: '2026-05-14',
    emergencyStopActive: false,
    favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
    blacklistedExerciseSlugs: ['smith-machine-bench-press'],
  })

  useStage4Store.getState().resetDevFlags()
  useStage4Store.getState().resetSettingsToDefaults()
  useStage4Store.getState().syncForUser(userId)
  useStage4Store.getState().patchDevFlags(devPatch)
}

function ProgressStory({ initialEntry }: { initialEntry: string }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [queryClient] = useState(() => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
    const { selectedUserId, blacklistedExerciseSlugs } = useAppStore.getState()
    const userId = selectedUserId ?? 'alexey'
    const user = getProfileSeed(userId)
    const dev = useStage4Store.getState().dev

    for (const { id: period } of stage4Periods) {
      const data = buildProgressData({ user, period, blacklistedSlugs: blacklistedExerciseSlugs, dev })
      const slugs = new Set(['machine-pulldown', ...data.exerciseOptions.map((exercise) => exercise.slug)])
      for (const slug of slugs) {
        client.setQueryData(['progress-screen', userId, period, slug], data)
      }
    }

    for (const { id: mode } of fatigueModes) {
      client.setQueryData(['fatigue-screen', userId, mode], buildFatigueData({ dev }))
    }

    return client
  })

  // The global preview already supplies MemoryRouter; do not nest another router.
  useLayoutEffect(() => {
    navigate(initialEntry, { replace: true })
  }, [initialEntry, navigate])

  return (
    <QueryClientProvider client={queryClient}>
      {location.pathname === '/progress' ? <ProgressScreen /> : location.pathname === '/fatigue' ? <FatigueScreen /> : null}
    </QueryClientProvider>
  )
}

export const ProgressOverview: Story = {
  render: () => {
    prepareState('alexey')

    return <ProgressStory initialEntry="/progress?tab=summary&period=30d" />
  },
}

export const ProgressRecoveryHighLoad: Story = {
  render: () => {
    prepareState('alexey', { highFatigue: true })

    return <ProgressStory initialEntry="/fatigue?mode=current&muscle=chest" />
  },
}

export const ProgressRecoveryAfterWorkout: Story = {
  render: () => {
    prepareState('elena')

    return <ProgressStory initialEntry="/fatigue?mode=after-workout&muscle=quads" />
  },
}

export const UserProfileGeneral: Story = {
  render: () => {
    prepareState('alexey')
    useStage4Store.getState().startProfileEdit()

    return (
      <MemoryRouter initialEntries={['/profile?tab=general']}>
        <Routes>
          <Route path="/profile" element={<UserProfileScreen />} />
        </Routes>
      </MemoryRouter>
    )
  },
}

function SettingsDiagnosticsStory() {
  const navigate = useNavigate()
  const location = useLocation()
  useLayoutEffect(() => {
    navigate('/settings?tab=diagnostics', { replace: true })
  }, [navigate])

  return location.pathname === '/settings' ? (
    <Routes>
      <Route path="/settings" element={<SettingsLayout />}>
        <Route index element={<SystemSettingsScreen />} />
      </Route>
    </Routes>
  ) : null
}

export const SettingsDiagnostics: Story = {
  render: () => {
    prepareState('alexey')
    return <SettingsDiagnosticsStory />
  },
}