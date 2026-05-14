import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { DashboardScreen } from '@/screens/dashboard/dashboard-screen'
import { WorkoutBuilderScreen } from '@/screens/builder/workout-builder-screen'
import { WorkoutCalendarScreen } from '@/screens/calendar/workout-calendar-screen'
import { ExerciseCatalogScreen } from '@/screens/catalog/exercise-catalog-screen'
import { ExerciseDetailsScreen } from '@/screens/catalog/exercise-details-screen'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import { ExerciseSummaryScreen } from '@/screens/exercise-summary/exercise-summary-screen'
import { PlaceholderScreen } from '@/screens/placeholder/placeholder-screen'
import { PhotoProgressScreen } from '@/screens/photo-progress/photo-progress-screen'
import { ProgramLibraryScreen } from '@/screens/programs/program-library-screen'
import { QuickStartScreen } from '@/screens/quick-start/quick-start-screen'
import { RestScreen } from '@/screens/rest/rest-screen'
import { TodayWorkoutScreen } from '@/screens/today/today-workout-screen'
import { UserSelectionScreen } from '@/screens/user-selection/user-selection-screen'
import { WorkoutSummaryScreen } from '@/screens/workout-summary/workout-summary-screen'
import { useAppStore } from '@/stores/app-store'

const placeholderTitles = {
  '/fatigue': 'Усталость',
  '/profile': 'Профиль',
  '/settings': 'Настройки',
} as const

function ProtectedAppRoute({ children }: { children: ReactElement }) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)

  if (!selectedUserId) {
    return <Navigate to="/" replace />
  }

  return children
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UserSelectionScreen />} />
        <Route path="/dashboard" element={<ProtectedAppRoute><DashboardScreen /></ProtectedAppRoute>} />
        <Route path="/quick-start" element={<ProtectedAppRoute><QuickStartScreen /></ProtectedAppRoute>} />
        <Route path="/today" element={<ProtectedAppRoute><TodayWorkoutScreen /></ProtectedAppRoute>} />
        <Route path="/calendar" element={<ProtectedAppRoute><WorkoutCalendarScreen /></ProtectedAppRoute>} />
        <Route path="/builder" element={<ProtectedAppRoute><WorkoutBuilderScreen /></ProtectedAppRoute>} />
        <Route path="/programs" element={<ProtectedAppRoute><ProgramLibraryScreen /></ProtectedAppRoute>} />
        <Route path="/catalog" element={<ProtectedAppRoute><ExerciseCatalogScreen /></ProtectedAppRoute>} />
        <Route path="/catalog/:slug" element={<ProtectedAppRoute><ExerciseDetailsScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-setup" element={<ProtectedAppRoute><ExerciseSetupScreen /></ProtectedAppRoute>} />
        <Route path="/photo-progress" element={<ProtectedAppRoute><PhotoProgressScreen /></ProtectedAppRoute>} />
        <Route path="/progress" element={<ProtectedAppRoute><PhotoProgressScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-session" element={<ProtectedAppRoute><ExerciseSessionScreen /></ProtectedAppRoute>} />
        <Route path="/rest" element={<ProtectedAppRoute><RestScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-summary" element={<ProtectedAppRoute><ExerciseSummaryScreen /></ProtectedAppRoute>} />
        <Route path="/workout-summary" element={<ProtectedAppRoute><WorkoutSummaryScreen /></ProtectedAppRoute>} />
        {Object.entries(placeholderTitles).map(([path, title]) => (
          <Route key={path} path={path} element={<ProtectedAppRoute><PlaceholderScreen title={title} /></ProtectedAppRoute>} />
        ))}
      </Routes>
    </BrowserRouter>
  )
}