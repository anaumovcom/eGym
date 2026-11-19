// Isolated Playwright entry: real settings/CacheStorage/Web Audio, no equipment or runtime mutations.
import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { CoachSettingsPanel } from '../../src/features/coach/ui/coach-settings-panel'
import { coachLiveRuntime } from '../../src/features/coach/live/coach-live-runtime'
import { useAppStore } from '../../src/stores/app-store'
import { useRuntimeStore } from '../../src/stores/runtime-store'
import { useStage4Store } from '../../src/stores/stage4-store'
import '../../src/app/styles.css'

useAppStore.setState({ selectedUserId: 'coach-e2e' })
const general = useStage4Store.getState().settingsSaved
useStage4Store.setState({ settingsSaved: { ...general, soundEnabled: true, voiceHintsEnabled: true, signalVolume: '70%' } })

function OfflineRepProbe() {
	const [result, setResult] = useState('')
	function count() {
		// Seed only frontend stores; no device connection, backend writes, or synthesized test tone.
		useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'push-up' })
		const seed = useRuntimeStore.getState().session!
		const session = { ...seed, dataSource: 'backend' as const, view: 'exercise-session' as const,
			exercises: seed.exercises.map(ex => ({ ...ex, kind: 'bodyweight' as const })) }
		useRuntimeStore.setState({ session })
		coachLiveRuntime.start()
		coachLiveRuntime.noteManualRep('coach-e2e', session, 0, 1)
		const cue = coachLiveRuntime.getSnapshot().lastCue
		setResult(`${cue?.clipId}: ${cue?.reason}`)
	}
	return <><button onClick={count}>Тест: подтвердить повтор</button><output data-testid="rep-result">{result}</output></>
}
createRoot(document.getElementById('root')!).render(<><CoachSettingsPanel /><OfflineRepProbe /></>)