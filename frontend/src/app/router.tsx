import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import { DashboardScreen } from '@/screens/dashboard/dashboard-screen'
import { WorkoutBuilderScreen } from '@/screens/builder/workout-builder-screen'
import { WorkoutCalendarScreen } from '@/screens/calendar/workout-calendar-screen'
import { ExerciseCatalogScreen } from '@/screens/catalog/exercise-catalog-screen'
import { ExerciseDetailsScreen } from '@/screens/catalog/exercise-details-screen'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import { ExerciseSummaryScreen } from '@/screens/exercise-summary/exercise-summary-screen'
import { FatigueScreen } from '@/screens/fatigue/fatigue-screen'
import { PlaceholderScreen } from '@/screens/placeholder/placeholder-screen'
import { UserProfileScreen } from '@/screens/profile/user-profile-screen'
import { ProgressScreen } from '@/screens/progress/progress-screen'
import { RestScreen } from '@/screens/rest/rest-screen'
import { SystemSettingsScreen } from '@/screens/settings/system-settings-screen'
import { UserSelectionScreen } from '@/screens/user-selection/user-selection-screen'
import { WorkoutSummaryScreen } from '@/screens/workout-summary/workout-summary-screen'
import { ModbusDebugScreen } from '@/screens/modbus-debug/modbus-debug-screen'
import { useAppStore } from '@/stores/app-store'
import { SettingsLayout } from '@/shared/ui/layout/service-access'

const placeholderTitles = {
  '/settings/legacy': 'Настройки',
} as const

function ProtectedAppRoute({ children }: { children: ReactElement }) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)

  if (!selectedUserId) {
    return <Navigate to="/" replace />
  }

  return children
}

function PhotoProgressRedirect() {
  const [params] = useSearchParams()
  return <Navigate to={params.get('source') === 'profile' ? '/profile?tab=photo' : '/progress?tab=photo'} replace />
}

export function AppRoutes() {
  return (
      <Routes>
        <Route path="/" element={<UserSelectionScreen />} />
        <Route path="/dashboard" element={<ProtectedAppRoute><DashboardScreen /></ProtectedAppRoute>} />
        <Route path="/quick-start" element={<ProtectedAppRoute><Navigate to="/catalog" replace /></ProtectedAppRoute>} />
        <Route path="/today" element={<ProtectedAppRoute><Navigate to="/dashboard" replace /></ProtectedAppRoute>} />
        <Route path="/calendar" element={<ProtectedAppRoute><WorkoutCalendarScreen /></ProtectedAppRoute>} />
        <Route path="/builder" element={<ProtectedAppRoute><WorkoutBuilderScreen /></ProtectedAppRoute>} />
        <Route path="/programs" element={<ProtectedAppRoute><Navigate to="/builder" replace /></ProtectedAppRoute>} />
        <Route path="/catalog" element={<ProtectedAppRoute><ExerciseCatalogScreen /></ProtectedAppRoute>} />
        <Route path="/catalog/:slug" element={<ProtectedAppRoute><ExerciseDetailsScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-setup" element={<ProtectedAppRoute><ExerciseSetupScreen /></ProtectedAppRoute>} />
        <Route path="/photo-progress" element={<ProtectedAppRoute><PhotoProgressRedirect /></ProtectedAppRoute>} />
        <Route path="/progress" element={<ProtectedAppRoute><ProgressScreen /></ProtectedAppRoute>} />
        <Route path="/fatigue" element={<ProtectedAppRoute><FatigueScreen /></ProtectedAppRoute>} />
        <Route path="/profile" element={<ProtectedAppRoute><UserProfileScreen /></ProtectedAppRoute>} />
        <Route path="/settings" element={<ProtectedAppRoute><SettingsLayout /></ProtectedAppRoute>}>
          <Route index element={<SystemSettingsScreen />} />
          <Route path="service/modbus" element={<Navigate to="/modbus" replace />} />
        </Route>
        <Route path="/modbus" element={<ProtectedAppRoute><ModbusDebugScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-session" element={<ProtectedAppRoute><ExerciseSessionScreen /></ProtectedAppRoute>} />
        <Route path="/rest" element={<ProtectedAppRoute><RestScreen /></ProtectedAppRoute>} />
        <Route path="/exercise-summary" element={<ProtectedAppRoute><ExerciseSummaryScreen /></ProtectedAppRoute>} />
        <Route path="/workout-summary" element={<ProtectedAppRoute><WorkoutSummaryScreen /></ProtectedAppRoute>} />
        <Route path="/modbus-debug" element={<ProtectedAppRoute><Navigate to="/modbus" replace /></ProtectedAppRoute>} />
        {Object.entries(placeholderTitles).map(([path, title]) => (
          <Route key={path} path={path} element={<ProtectedAppRoute><PlaceholderScreen title={title} /></ProtectedAppRoute>} />
        ))}
      </Routes>
  )
}

export function AppRouter() {
  return <BrowserRouter><AppRoutes /></BrowserRouter>
}