import type { Meta, StoryObj } from '@storybook/react-vite'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { FatigueScreen } from '@/screens/fatigue/fatigue-screen'
import { UserProfileScreen } from '@/screens/profile/user-profile-screen'
import { ProgressScreen } from '@/screens/progress/progress-screen'
import { SystemSettingsScreen } from '@/screens/settings/system-settings-screen'
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

export const ProgressOverview: Story = {
  render: () => {
    prepareState('alexey')

    return (
      <MemoryRouter initialEntries={['/progress?tab=summary&period=30d']}>
        <Routes>
          <Route path="/progress" element={<ProgressScreen />} />
        </Routes>
      </MemoryRouter>
    )
  },
}

export const FatigueHighLoad: Story = {
  render: () => {
    prepareState('alexey', { highFatigue: true })

    return (
      <MemoryRouter initialEntries={['/fatigue?mode=current&muscle=chest']}>
        <Routes>
          <Route path="/fatigue" element={<FatigueScreen />} />
        </Routes>
      </MemoryRouter>
    )
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

export const SettingsDiagnostics: Story = {
  render: () => {
    prepareState('alexey')

    return (
      <MemoryRouter initialEntries={['/settings?tab=diagnostics']}>
        <Routes>
          <Route path="/settings" element={<SystemSettingsScreen />} />
        </Routes>
      </MemoryRouter>
    )
  },
}