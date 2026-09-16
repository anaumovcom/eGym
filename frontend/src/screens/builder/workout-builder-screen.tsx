import * as Dialog from '@radix-ui/react-dialog'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Dumbbell, Flame, Gauge, OctagonAlert, Plus, Repeat2, Replace, Settings2, SlidersHorizontal, Target, Timer, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { BuilderExerciseEditor, BuilderExerciseItem, BuilderGroupKind, BuilderLoadType, BuilderWorkoutGroup, WorkoutBuilderData } from '@/entities/builder/model/types'
import type { ExerciseDetails } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { StrengthSetPlan, StrengthSetType, StrengthTrainingMode } from '@/entities/strength/model/types'
import { buildStrengthPlan, getSetTypeLabel, normalizeStrengthDayType, normalizeStrengthModeId } from '@/features/strength/lib/strength-plan'
import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { CompactBodyMapMini, ExerciseVideoPlayer } from '@/shared/ui/stage2/screen-components'
import { ExercisePickerModal, isRecoveryEquipment, isWeightlessEquipment } from '@/shared/ui/training/exercise-picker-modal'
import { ValueStepper } from '@/shared/ui/training/value-stepper'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

const BUILDER_GROUP_KIND_OPTIONS: Array<{ id: BuilderGroupKind; label: string }> = [
  { id: 'single', label: 'Обычное' },
  { id: 'alternating', label: 'Чередование' },
  { id: 'superset', label: 'Суперсет' },
  { id: 'circuit', label: 'Круг' },
]

const BUILDER_LOAD_MODE_RULES: Record<string, { weightFactor: number; repsFactor: number; durationFactor: number; restDelta: number; description: string }> = {
  'Обычный вес': { weightFactor: 1, repsFactor: 1, durationFactor: 1, restDelta: 0, description: 'Без корректировок: в план попадают заданные вес, повторы, длительность и отдых.' },
  'Контроль техники': { weightFactor: 0.9, repsFactor: 0.9, durationFactor: 0.9, restDelta: 15, description: 'Для техники план снижает вес и целевые повторы/секунды на 10%, а отдых увеличивает на 15 сек.' },
  'Лёгкий режим': { weightFactor: 0.8, repsFactor: 0.8, durationFactor: 0.8, restDelta: 15, description: 'Для разгрузки план снижает вес и целевые повторы/секунды на 20%, а отдых увеличивает на 15 сек.' },
}

const BUILDER_TEMPO_RULES: Record<string, { weightFactor: number; repsFactor: number; durationFactor: number; restDelta: number; description: string }> = {
  'Обычный': { weightFactor: 1, repsFactor: 1, durationFactor: 1, restDelta: 0, description: 'Без корректировок темпа: параметры остаются такими, как заданы выше.' },
  'Плавный': { weightFactor: 1, repsFactor: 1, durationFactor: 1.1, restDelta: 15, description: 'Плавный темп добавляет 15 сек отдыха; если задана длительность, цель по времени увеличивается на 10%.' },
  'Контроль эксцентрики': { weightFactor: 0.9, repsFactor: 0.9, durationFactor: 1.15, restDelta: 30, description: 'Контроль эксцентрики снижает вес и повторы на 10%, увеличивает заданную длительность на 15% и добавляет 30 сек отдыха.' },
}

type ProgramMutationResult = {
  id: string
  status: string
}

function normalizeBuilderData(data: WorkoutBuilderData): WorkoutBuilderData {
  return {
    ...data,
    programs: data.programs.map((program) => ({
      ...program,
      canDelete: program.canDelete ?? ('can_delete' in program ? Boolean((program as typeof program & { can_delete?: boolean }).can_delete) : false),
    })),
  }
}

export function WorkoutBuilderScreen() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const resolvedUserId = selectedUserId ?? 'alexey'

  const selectedExerciseIdParam = searchParams.get('selectedExerciseId')
  const selectedProgramIdParam = searchParams.get('programId')
  const addSlugParam = searchParams.get('add')

  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Проверка подключения...',
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['workout-builder', resolvedUserId, selectedProgramIdParam, selectedExerciseIdParam],
    queryFn: () => {
      const params = new URLSearchParams({ userId: resolvedUserId })
      if (selectedProgramIdParam) {
        params.set('programId', selectedProgramIdParam)
      }
      if (selectedExerciseIdParam) {
        params.set('selectedExerciseId', selectedExerciseIdParam)
      }
      return apiGet<WorkoutBuilderData>(`/api/builder?${params.toString()}`).then(normalizeBuilderData)
    },
    placeholderData: keepPreviousData,
  })

  const [groups, setGroups] = useState(data?.groups ?? [])
  const [editor, setEditor] = useState(data?.selectedExercise ?? null)
  const [workoutTitle, setWorkoutTitle] = useState(data?.info.name ?? '')
  const [titleDraft, setTitleDraft] = useState(data?.info.name ?? '')
  const [isEditingWorkoutTitle, setIsEditingWorkoutTitle] = useState(false)
  const [groupDialogId, setGroupDialogId] = useState<string | null>(null)
  const [groupTitleDraft, setGroupTitleDraft] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'error'>('saved')
  const [replaceModalOpen, setReplaceModalOpen] = useState(false)
  const [replaceTargetExerciseId, setReplaceTargetExerciseId] = useState<string | null>(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addTargetPosition, setAddTargetPosition] = useState<{ groupId: string; index: number } | null>(null)
  const [createPending, setCreatePending] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const createPendingRef = useRef(false)
  const createDialogOpen = searchParams.get('create') === 'new'
  const lastSavedSnapshotRef = useRef<string | null>(null)
  const lastSavePromiseRef = useRef<Promise<void> | null>(null)
  const groupsRef = useRef(groups)
  const editorRef = useRef(editor)
  const workoutTitleRef = useRef(workoutTitle)
  const noteTextareaRef = useRef<HTMLTextAreaElement | null>(null)
  const selectedProgramId = data?.selectedProgramId ?? selectedProgramIdParam ?? ''
  const selectedExerciseId = data?.selectedExerciseId ?? selectedExerciseIdParam ?? groups[0]?.items[0]?.id ?? ''
  const figureGender = resolvedUserId === 'elena' ? 'female' : 'male'

  useEffect(() => {
    groupsRef.current = groups
  }, [groups])

  useEffect(() => {
    editorRef.current = editor
  }, [editor])

  useEffect(() => {
    workoutTitleRef.current = workoutTitle
  }, [workoutTitle])

  useEffect(() => {
    resizeBuilderTextarea(noteTextareaRef.current)
  }, [editor?.note])

  useEffect(() => {
    if (!data) {
      groupsRef.current = []
      editorRef.current = null
      setGroups([])
      setEditor(null)
      return
    }

    const nextGroups = mergeBuilderGroupsWithLocalStrength(data?.groups ?? [], groupsRef.current)
    const selectedItem = nextGroups.flatMap((group) => group.items).find((item) => item.id === data.selectedExerciseId)
    const editorSource = data.selectedExerciseId && data.selectedExercise
      ? {
          ...data.selectedExercise,
          strengthModeId: selectedItem?.strengthModeId ?? data.selectedExercise.strengthModeId,
          strengthDayType: selectedItem?.strengthDayType ?? data.selectedExercise.strengthDayType,
          strengthPlan: selectedItem?.strengthPlan?.length ? selectedItem.strengthPlan : data.selectedExercise.strengthPlan,
        }
      : null
    const nextEditor = editorSource ? normalizeBuilderEditor(editorSource, nextGroups, data.selectedExerciseId) : null
    groupsRef.current = nextGroups
    editorRef.current = nextEditor
    setGroups(nextGroups)
    setEditor(nextEditor)
    setWorkoutTitle(data.info.name)
    setTitleDraft(data.info.name)
    setIsEditingWorkoutTitle(false)
    lastSavedSnapshotRef.current = createBuilderSaveSnapshot(resolvedUserId, data.selectedProgramId, data.info.name, nextGroups, data.selectedExerciseId || null, nextEditor)
  }, [data, resolvedUserId])

  useEffect(() => {
    // Catalog hands over a chosen exercise: open the add flow on its configuration step.
    if (addSlugParam && data && selectedProgramIdParam) setAddModalOpen(true)
  }, [addSlugParam, data, selectedProgramIdParam])

  if (error) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить конструктор тренировки. Попробуйте открыть его ещё раз.</div>
      </FormaShell>
    )
  }

  if (isLoading || !data) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка конструктора тренировки…</div>
      </FormaShell>
    )
  }

  const exerciseItems = groups.flatMap((group) => group.items.map((item) => ({ groupId: group.id, item })))
  const selectedExerciseItem = exerciseItems.find(({ item }) => item.id === selectedExerciseId)
  const replaceTargetExerciseItem = exerciseItems.find(({ item }) => item.id === (replaceTargetExerciseId ?? selectedExerciseId))
  const activeGroupId = selectedExerciseItem?.groupId ?? groups[0]?.id ?? data.groups[0]?.id
  const selectedStrengthMode = editor ? data.strengthModes.find((mode) => mode.id === editor.strengthModeId) ?? data.strengthModes[0] : data.strengthModes[0]
  const selectedProgram = data.programs.find((program) => program.id === selectedProgramId)
  const hasPrograms = data.programs.length > 0

  async function persistBuilderPlan(nextGroups: BuilderWorkoutGroup[], nextSelectedExerciseId: string | null, nextEditor: WorkoutBuilderData['selectedExercise'] | null, nextWorkoutTitle: string) {
    if (!data || !selectedProgramId) {
      return
    }

    const snapshot = createBuilderSaveSnapshot(resolvedUserId, selectedProgramId, nextWorkoutTitle, nextGroups, nextSelectedExerciseId, nextEditor)
    if (snapshot === lastSavedSnapshotRef.current) {
      if (lastSavePromiseRef.current) {
        await lastSavePromiseRef.current
      }
      return
    }

    lastSavedSnapshotRef.current = snapshot

    let savePromise!: Promise<void>
    const payload: {
      userId: string
      programId: string
      workoutName: string
      groups: ReturnType<typeof serializeBuilderGroups>
      selectedExerciseId?: string
      selectedExercise?: WorkoutBuilderData['selectedExercise']
    } = {
      userId: resolvedUserId,
      programId: selectedProgramId,
      workoutName: nextWorkoutTitle,
      groups: serializeBuilderGroups(nextGroups),
    }

    if (nextSelectedExerciseId && nextEditor) {
      payload.selectedExerciseId = nextSelectedExerciseId
      payload.selectedExercise = nextEditor
    }

    savePromise = apiPut('/api/builder/plan', payload)
      .then(() => {
        setSaveStatus('saved')
      })
      .catch(() => {
        setSaveStatus('error')
        if (lastSavePromiseRef.current === savePromise) {
          lastSavedSnapshotRef.current = null
        }
      })
      .finally(() => {
        if (lastSavePromiseRef.current === savePromise) {
          lastSavePromiseRef.current = null
        }
      })

    setSaveStatus('saving')
    lastSavePromiseRef.current = savePromise
    await savePromise
  }

  function goToList() {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('programId')
      next.delete('selectedExerciseId')
      next.delete('add')
      return next
    })
  }

  async function handleDone() {
    if (selectedProgramId) {
      await persistBuilderPlan(groupsRef.current, selectedExerciseId || null, editorRef.current, workoutTitleRef.current)
      if (lastSavedSnapshotRef.current === null) {
        return
      }
    }
    goToList()
  }

  function retrySave() {
    lastSavedSnapshotRef.current = null
    void persistBuilderPlan(groupsRef.current, selectedExerciseId || null, editorRef.current, workoutTitleRef.current)
  }

  async function selectExercise(exerciseId: string, options?: { skipSave?: boolean }) {
    if (exerciseId === selectedExerciseId) {
      return
    }

    const currentEditor = editorRef.current
    if (!options?.skipSave && currentEditor) {
      await persistBuilderPlan(groupsRef.current, selectedExerciseId, currentEditor, workoutTitleRef.current)
    }

    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (selectedProgramId) {
          next.set('programId', selectedProgramId)
        }
        next.set('selectedExerciseId', exerciseId)
        return next
      },
      { preventScrollReset: true },
    )
  }

  function updateEditor(updater: (current: NonNullable<typeof editor>) => NonNullable<typeof editor>) {
    const currentEditor = editorRef.current
    if (!currentEditor) {
      return
    }

    const currentGroups = groupsRef.current
    const next = updater(currentEditor)
    const normalizedNext = normalizeBuilderEditor(next, currentGroups, selectedExerciseId)
    const nextGroups = applyEditorToGroups(currentGroups, selectedExerciseId, normalizedNext)

    groupsRef.current = nextGroups
    editorRef.current = normalizedNext
    setGroups(nextGroups)
    setEditor(normalizedNext)
    void persistBuilderPlan(nextGroups, selectedExerciseId, normalizedNext, workoutTitleRef.current)
  }

  async function saveWorkoutTitle(nextWorkoutTitle: string) {
    const normalizedTitle = nextWorkoutTitle.trim() || workoutTitleRef.current || data?.info.name || ''
    if (!normalizedTitle) {
      return
    }

    setWorkoutTitle(normalizedTitle)
    setTitleDraft(normalizedTitle)
    workoutTitleRef.current = normalizedTitle
    await persistBuilderPlan(groupsRef.current, selectedExerciseId || null, editorRef.current, normalizedTitle)
    queryClient.setQueriesData<WorkoutBuilderData>({ queryKey: ['workout-builder', resolvedUserId] }, (current) => {
      if (!current || current.selectedProgramId !== selectedProgramId) {
        return current
      }

      return {
        ...current,
        info: {
          ...current.info,
          name: normalizedTitle,
        },
        programs: current.programs.map((program) => (
          program.id === selectedProgramId
            ? { ...program, name: normalizedTitle }
            : program
        )),
      }
    })
  }

  async function saveGroups(nextGroups: BuilderWorkoutGroup[], nextSelectedExerciseId = selectedExerciseId || null, nextEditor = editorRef.current) {
    groupsRef.current = nextGroups
    setGroups(nextGroups)
    await persistBuilderPlan(nextGroups, nextSelectedExerciseId, nextEditor, workoutTitleRef.current)
  }

  async function updateGroup(groupId: string, updater: (group: BuilderWorkoutGroup) => BuilderWorkoutGroup) {
    const nextGroups = groupsRef.current.map((group) => (group.id === groupId ? updater(group) : group))
    await saveGroups(nextGroups)
  }

  async function saveGroupTitle(groupId: string, nextTitle: string) {
    const normalizedTitle = nextTitle.trim()
    const currentGroup = groupsRef.current.find((group) => group.id === groupId)
    if (!currentGroup) {
      return
    }

    if (!normalizedTitle || normalizedTitle === currentGroup.title) {
      setGroupTitleDraft(currentGroup.title)
      return
    }

    await updateGroup(groupId, (group) => ({ ...group, title: normalizedTitle }))
    setGroupTitleDraft(normalizedTitle)
  }

  function adjustGroupBreak(groupId: string, delta: number) {
    void updateGroup(groupId, (group) => {
      const currentRestSeconds = parseDurationSeconds(group.betweenRoundsRest) ?? 120
      return {
        ...group,
        betweenRoundsRest: `${Math.max(15, currentRestSeconds + delta * 15)} сек`,
      }
    })
  }

  function changeGroupKind(groupId: string, kind: BuilderGroupKind) {
    void updateGroup(groupId, (group) => ({ ...group, kind }))
  }

  function setCreateDialogOpen(open: boolean) {
    if (createPendingRef.current) {
      return
    }

    setCreateError(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (open) next.set('create', 'new')
      else next.delete('create')
      return next
    }, { replace: true, preventScrollReset: true })
  }

  async function handleCreateWorkout() {
    if (!data || !createDialogOpen || createPendingRef.current) {
      return
    }

    createPendingRef.current = true
    setCreatePending(true)
    setCreateError(null)
    try {
      // Do not leave the current plan while an autosave is pending or failed.
      if (selectedProgramId) {
        await persistBuilderPlan(groupsRef.current, selectedExerciseId || null, editorRef.current, workoutTitleRef.current)
        if (lastSavedSnapshotRef.current === null) {
          setCreateError('Не удалось сохранить текущую тренировку. Повторите попытку перед созданием новой.')
          return
        }
      }

      const existingCustomPrograms = data.programs.filter((program) => program.name.startsWith('Новая тренировка')).length
      const workoutName = existingCustomPrograms > 0 ? `Новая тренировка ${existingCustomPrograms + 1}` : 'Новая тренировка'

      const response = await apiPost<ProgramMutationResult>('/api/programs', {
        userId: resolvedUserId,
        name: workoutName,
        subtitle: 'Пустая тренировка',
        programType: 'strength',
        difficulty: 'easy',
        durationMinutes: 45,
        focusTags: [],
        description: 'Пустая программа для ручной сборки.',
        structure: {
          builderGroups: [
            {
              id: 'new-group-1',
              kind: 'single',
              title: 'Новая группа',
              betweenRoundsRest: '120 сек',
              items: [],
            },
          ],
        },
        recommendedToday: false,
      })

      void queryClient.invalidateQueries({ queryKey: ['workout-builder', resolvedUserId], refetchType: 'none' })
      void queryClient.invalidateQueries({ queryKey: ['dashboard', resolvedUserId] })
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.set('programId', response.id)
        next.delete('selectedExerciseId')
        next.delete('create')
        return next
      }, { replace: true, preventScrollReset: true })
    } catch {
      setCreateError('Не удалось создать тренировку. Попробуйте ещё раз.')
    } finally {
      createPendingRef.current = false
      setCreatePending(false)
    }
  }

  async function handleDeleteWorkout() {
    if (!data || !selectedProgramId || !selectedProgram) {
      return
    }

    await apiDelete(`/api/programs/${selectedProgramId}?userId=${encodeURIComponent(resolvedUserId)}`)

    queryClient.setQueriesData<WorkoutBuilderData>({ queryKey: ['workout-builder', resolvedUserId] }, (current) => {
      if (!current) {
        return current
      }

      const nextPrograms = current.programs.filter((program) => program.id !== selectedProgramId)
      const nextSelectedProgramId = current.selectedProgramId === selectedProgramId ? (nextPrograms[0]?.id ?? '') : current.selectedProgramId

      return {
        ...current,
        programs: nextPrograms,
        selectedProgramId: nextSelectedProgramId,
      }
    })

    await queryClient.invalidateQueries({ queryKey: ['workout-builder', resolvedUserId] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard', resolvedUserId] })
    setDeleteDialogOpen(false)
    goToList()
  }

  async function handleAddGroup() {
    const nextGroupId = `group-${Math.random().toString(36).slice(2, 8)}`
    const nextGroups = [
      ...groupsRef.current,
      {
        id: nextGroupId,
        kind: 'single' as const,
        title: 'Новая группа',
        betweenRoundsRest: '120 сек',
        items: [],
      },
    ]

    await saveGroups(nextGroups)
  }

  async function handleDeleteGroup(groupId: string) {
    if (groupsRef.current.length <= 1) {
      return
    }

    const nextGroups = groupsRef.current.filter((group) => group.id !== groupId)
    const remainingItems = nextGroups.flatMap((group) => group.items)
    const selectedStillExists = remainingItems.some((item) => item.id === selectedExerciseId)
    const nextSelectedExerciseId = selectedStillExists ? selectedExerciseId : remainingItems[0]?.id ?? null
    await saveGroups(nextGroups, nextSelectedExerciseId, selectedStillExists ? editorRef.current : null)
    if (nextSelectedExerciseId !== selectedExerciseId) {
      moveSelection(nextSelectedExerciseId)
    }
  }

  function moveSelection(exerciseId: string | null) {
    if (exerciseId) {
      void selectExercise(exerciseId, { skipSave: true })
      return
    }
    editorRef.current = null
    setEditor(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('selectedExerciseId')
      return next
    }, { preventScrollReset: true })
  }

  function handleSelectProgram(programId: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('programId', programId)
      next.delete('selectedExerciseId')
      return next
    })
  }

  async function handleReplaceExercise(details: ExerciseDetails) {
    const targetExerciseId = replaceTargetExerciseId ?? selectedExerciseId
    const currentNote = editor?.note ?? ''
    const loadType = getBuilderLoadType(details)
    const durationSeconds = getBuilderDuration(details)
    const strengthModeId = normalizeStrengthModeId(editor?.strengthModeId)
    const strengthDayType = normalizeStrengthDayType(strengthModeId, editor?.strengthDayType)
    const setParams = {
      reps: details.loadSettings.reps,
      weight: Math.round(details.loadSettings.weight),
      restSeconds: details.loadSettings.restSeconds,
      ...(durationSeconds ? { durationSeconds } : {}),
    }
    const effectiveSetParams = getEffectiveBuilderSetParams(loadType, setParams, details.loadSettings.mode, details.loadSettings.tempo)
    const strengthPlan = buildStrengthPlan(strengthModeId, strengthDayType, effectiveSetParams, loadType)
    const nextGroups = groups.map((group) => ({
        ...group,
        items: group.items.map((item) =>
          item.id === targetExerciseId
            ? {
                ...item,
                slug: details.slug,
                name: details.name,
                muscleGroup: formatBuilderMuscleGroup(details),
                muscles: details.muscles,
                affectsFatigue: !isRecoveryEquipment(details.equipment),
                sets: formatBuilderItemSets(loadType, details.loadSettings.sets, effectiveSetParams.reps, effectiveSetParams.durationSeconds),
                load: formatBuilderItemLoad(loadType, effectiveSetParams.weight),
                loadType,
                rest: `${effectiveSetParams.restSeconds} сек`,
                previewVideoUrl: details.previewVideoUrl,
                strengthModeId,
                strengthDayType,
                strengthPlan,
              }
            : item,
        ),
      }))

    await apiPut('/api/builder/plan', {
      userId: resolvedUserId,
      programId: selectedProgramId,
      workoutName: workoutTitleRef.current,
      groups: serializeBuilderGroups(nextGroups),
      selectedExerciseId: targetExerciseId,
      selectedExercise: {
        name: details.name,
        subtitle: formatBuilderSubtitle(details),
        setParams: {
          reps: details.loadSettings.reps,
          weight: Math.round(details.loadSettings.weight),
          restSeconds: details.loadSettings.restSeconds,
          durationSeconds,
        },
        loadType,
        loadMode: details.loadSettings.mode,
        tempo: details.loadSettings.tempo,
        strengthModeId,
        strengthDayType,
        strengthPlan,
        note: currentNote,
      },
    })

    setGroups(nextGroups)
    setEditor((current) =>
      current
        ? {
            ...current,
            name: details.name,
            subtitle: formatBuilderSubtitle(details),
            setParams: {
              reps: details.loadSettings.reps,
              weight: Math.round(details.loadSettings.weight),
              restSeconds: details.loadSettings.restSeconds,
              durationSeconds,
            },
            loadType,
            loadMode: details.loadSettings.mode,
            tempo: details.loadSettings.tempo,
            strengthModeId,
            strengthDayType,
            strengthPlan,
          }
        : current,
    )
    void selectExercise(targetExerciseId, { skipSave: true })
    setReplaceTargetExerciseId(null)
    setReplaceModalOpen(false)
  }

  async function handleAddExercise(details: ExerciseDetails) {
    const targetGroupId = addTargetPosition?.groupId ?? activeGroupId
    if (!targetGroupId) {
      return
    }

    const nextId = `${targetGroupId}-${details.slug}-${Math.random().toString(36).slice(2, 8)}`
    const loadType = getBuilderLoadType(details)
    const durationSeconds = getBuilderDuration(details)
    const setParams = {
      reps: details.loadSettings.reps,
      weight: Math.round(details.loadSettings.weight),
      restSeconds: details.loadSettings.restSeconds,
      ...(durationSeconds ? { durationSeconds } : {}),
    }
    const effectiveSetParams = getEffectiveBuilderSetParams(loadType, setParams, details.loadSettings.mode, details.loadSettings.tempo)
    const strengthPlan = buildStrengthPlan('basic', null, effectiveSetParams, loadType)
    const nextItem = {
      id: nextId,
      slug: details.slug,
      name: details.name,
      muscleGroup: formatBuilderMuscleGroup(details),
      muscles: details.muscles,
      affectsFatigue: !isRecoveryEquipment(details.equipment),
      sets: formatBuilderItemSets(loadType, details.loadSettings.sets, effectiveSetParams.reps, effectiveSetParams.durationSeconds),
      rest: `${effectiveSetParams.restSeconds} сек`,
      load: formatBuilderItemLoad(loadType, effectiveSetParams.weight),
      loadType,
      previewVideoUrl: details.previewVideoUrl,
      strengthModeId: 'basic',
      strengthDayType: null,
      strengthPlan,
    } satisfies BuilderExerciseItem

    const nextGroups = groups.map((group) =>
        group.id === targetGroupId
          ? {
              ...group,
              items: [
                ...group.items.slice(0, addTargetPosition?.index ?? group.items.length),
                nextItem,
                ...group.items.slice(addTargetPosition?.index ?? group.items.length),
              ],
            }
          : group,
      )

    const shouldSelectNewExercise = !selectedExerciseId
    const nextEditor = shouldSelectNewExercise
      ? normalizeBuilderEditor(
          {
            name: details.name,
            subtitle: formatBuilderSubtitle(details),
            setParams: {
              reps: details.loadSettings.reps,
              weight: Math.round(details.loadSettings.weight),
              restSeconds: details.loadSettings.restSeconds,
              durationSeconds,
            },
            loadType,
            loadMode: details.loadSettings.mode,
            tempo: details.loadSettings.tempo,
            strengthModeId: 'basic',
            strengthDayType: null,
            strengthPlan,
            note: '',
          },
          nextGroups,
          nextId,
        )
      : null

    const payload: {
      userId: string
      programId: string
      workoutName: string
      groups: ReturnType<typeof serializeBuilderGroups>
      selectedExerciseId?: string
      selectedExercise?: WorkoutBuilderData['selectedExercise']
    } = {
      userId: resolvedUserId,
      programId: selectedProgramId,
      workoutName: workoutTitleRef.current,
      groups: serializeBuilderGroups(nextGroups),
    }

    if (shouldSelectNewExercise && nextEditor) {
      payload.selectedExerciseId = nextId
      payload.selectedExercise = nextEditor
    }

    await apiPut('/api/builder/plan', payload)

    groupsRef.current = nextGroups
    setGroups(nextGroups)
    if (shouldSelectNewExercise && nextEditor) {
      editorRef.current = nextEditor
      setEditor(nextEditor)
    }
    setAddModalOpen(false)
    setAddTargetPosition(null)
    if (shouldSelectNewExercise) {
      void selectExercise(nextId, { skipSave: true })
    }
  }

  async function handleDeleteExercise(exerciseId = selectedExerciseId) {
    const nextGroups = groups.map((group) => ({
      ...group,
      items: group.items.filter((item) => item.id !== exerciseId),
    }))

    const remainingItems = nextGroups.flatMap((group) => group.items)
    const nextSelectedItem = remainingItems.find((item) => item.id === selectedExerciseId) ?? remainingItems[0]

    await apiPut('/api/builder/plan', {
      userId: resolvedUserId,
      programId: selectedProgramId,
      workoutName: workoutTitleRef.current,
      groups: serializeBuilderGroups(nextGroups),
      ...(nextSelectedItem ? { selectedExerciseId: nextSelectedItem.id } : {}),
    })

    groupsRef.current = nextGroups
    setGroups(nextGroups)
    moveSelection(nextSelectedItem?.id ?? null)
  }

  const isListView = !selectedProgramIdParam
  const groupDialog = groupDialogId ? groups.find((group) => group.id === groupDialogId) ?? null : null
  const groupDialogIndex = groupDialog ? groups.indexOf(groupDialog) : -1
  const weightlessSelected = selectedExerciseItem ? isWeightlessEquipment(selectedExerciseItem.item.load) || selectedExerciseItem.item.loadType === 'bodyweight' : false

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <Dialog.Root open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        {isListView ? (
          <section className="builder-list" aria-labelledby="builder-title">
            <header className="home-heading">
              <h1 id="builder-title" className="font-display font-bold text-white">Мои тренировки</h1>
              <p className="text-white/60">{hasPrograms ? 'Выберите тренировку, чтобы изменить упражнения и нагрузку.' : 'Все тренировки удалены. Создайте новую тренировку.'}</p>
            </header>
            <div className="builder-list-grid" data-count={data.programs.length}>
              {data.programs.map((program) => (
                <button key={program.id} type="button" className="home-workout-card builder-card" aria-label={`Открыть тренировку «${program.name}»`} onClick={() => handleSelectProgram(program.id)}>
                  <span className="home-card-top"><span className="home-card-icon"><Dumbbell aria-hidden="true" /></span></span>
                  <span className="home-card-title">{program.name}</span>
                  <span className="home-card-exercises">{program.subtitle}</span>
                  <span className="home-card-select">Изменить <ArrowRight aria-hidden="true" className="h-5 w-5" /></span>
                </button>
              ))}
              <Dialog.Trigger asChild>
                <button type="button" className="home-workout-card home-create-card" aria-label="Новая тренировка" disabled={createPending}>
                  <Plus aria-hidden="true" />
                  <span className="home-card-title">Новая тренировка</span>
                  <span className="text-sm text-white/60">Пустая тренировка для ручной сборки</span>
                </button>
              </Dialog.Trigger>
            </div>
          </section>
        ) : (
          <section className="builder-editor" aria-labelledby="builder-title">
            <header className="builder-header">
              <Button variant="secondary" iconLeft={<ArrowLeft aria-hidden="true" />} onClick={() => void handleDone()}>Мои тренировки</Button>
              <div className="builder-title">
                <h1 id="builder-title" className="builder-title-heading font-display font-bold text-white">
                {selectedProgram && isEditingWorkoutTitle ? (
                  <input
                    aria-label="Название тренировки"
                    title="Название тренировки"
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                    onBlur={() => {
                      setTitleDraft(workoutTitle)
                      setIsEditingWorkoutTitle(false)
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        void saveWorkoutTitle(titleDraft)
                        setIsEditingWorkoutTitle(false)
                      }
                      if (event.key === 'Escape') {
                        setTitleDraft(workoutTitle)
                        setIsEditingWorkoutTitle(false)
                      }
                    }}
                    autoFocus
                    className="builder-title-input font-display font-bold text-white"
                  />
                ) : (
                  <button
                    type="button"
                    aria-label={`Название тренировки: ${workoutTitle}. Нажмите, чтобы переименовать`}
                    onClick={() => {
                      setTitleDraft(workoutTitle)
                      setIsEditingWorkoutTitle(true)
                    }}
                    className="builder-title-button font-display font-bold text-white"
                  >
                    {workoutTitle}
                  </button>
                )}
                </h1>
                <div className="builder-title-meta">
                  {data.info.duration ? <span className="inline-flex items-center gap-2"><Timer aria-hidden="true" className="h-5 w-5" />{data.info.duration}</span> : null}
                  {data.warnings.map((warning) => <BuilderWarningIcon key={warning.title} warning={warning} />)}
                </div>
              </div>
              <Dialog.Trigger asChild>
                <Button variant="secondary" iconLeft={<Plus aria-hidden="true" />} disabled={createPending}>Новая тренировка</Button>
              </Dialog.Trigger>
            </header>

            <div className="builder-body">
              <aside className="builder-side" aria-label="Упражнения тренировки">
                {groups.map((group, index) => (
                  <section key={group.id} className="builder-group" aria-label={`Группа ${index + 1}: ${group.title}`}>
                    <header className="builder-group-heading">
                      <span className="min-w-0">
                        <small>{formatBuilderGroupKindLabel(group.kind)}</small>
                        <strong>{index + 1}. {group.title}</strong>
                      </span>
                      <button type="button" className="builder-icon-button" aria-label={`Настроить группу ${group.title}`} aria-haspopup="dialog" onClick={() => { setGroupTitleDraft(group.title); setGroupDialogId(group.id) }}>
                        <Settings2 aria-hidden="true" />
                      </button>
                    </header>
                    {group.items.length ? (
                      <ol className="builder-items">
                        {group.items.map((item, itemIndex) => (
                          <li key={item.id}>
                            <button
                              type="button"
                              className="builder-item"
                              aria-current={item.id === selectedExerciseId ? 'true' : undefined}
                              aria-label={`Выбрать упражнение ${item.name}`}
                              title={`Выбрать упражнение ${item.name}`}
                              onClick={() => void selectExercise(item.id)}
                            >
                              <span className="builder-item-index">{itemIndex + 1}</span>
                              <span className="builder-item-body">
                                <span className="builder-item-name">{item.name}</span>
                                <span className="builder-item-summary">{formatBuilderItemSummary(item)}</span>
                              </span>
                            </button>
                          </li>
                        ))}
                      </ol>
                    ) : null}
                    <button
                      type="button"
                      className="builder-add"
                      onClick={() => {
                        setAddTargetPosition({ groupId: group.id, index: group.items.length })
                        setAddModalOpen(true)
                      }}
                    >
                      <Plus aria-hidden="true" />
                      {group.items.length ? 'Добавить упражнение' : 'Добавь упражнения'}
                    </button>
                    {index < groups.length - 1 ? <div className="builder-group-rest">Перерыв после группы · {group.betweenRoundsRest ?? '120 сек'}</div> : null}
                  </section>
                ))}
                <Button variant="secondary" className="w-full" onClick={() => void handleAddGroup()}>Добавить группу</Button>
              </aside>

              <section className="builder-stage" aria-label="Выбранное упражнение">
                {editor && selectedExerciseItem ? (
                  <>
                    <header className="builder-stage-heading">
                      <div className="min-w-0">
                        <h2 className="font-display font-bold text-white">{editor.name}</h2>
                        <p className="text-white/60">{editor.subtitle}</p>
                      </div>
                      <div className="builder-stage-actions">
                        <Button
                          variant="secondary"
                          iconLeft={<Replace aria-hidden="true" />}
                          aria-label={`Заменить упражнение ${editor.name}`}
                          onClick={() => {
                            setReplaceTargetExerciseId(selectedExerciseId)
                            setReplaceModalOpen(true)
                          }}
                        >
                          Заменить
                        </Button>
                        <Button variant="secondary" className="builder-danger" iconLeft={<Trash2 aria-hidden="true" />} aria-label={`Удалить упражнение ${editor.name}`} onClick={() => void handleDeleteExercise(selectedExerciseId)}>Удалить</Button>
                      </div>
                    </header>

                    <div className="builder-stage-media">
                      <ExercisePlanVideo videoUrl={selectedExerciseItem.item.previewVideoUrl} title={selectedExerciseItem.item.name} />
                      <ExercisePlanMuscleMap
                        muscles={selectedExerciseItem.item.muscles}
                        fallbackLabel={selectedExerciseItem.item.muscleGroup}
                        figureGender={figureGender}
                        title={selectedExerciseItem.item.name}
                      />
                    </div>

                    <div className="builder-steppers">
                      <ValueStepper
                        label="Повторы"
                        value={editor.setParams.reps}
                        onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, reps: Math.max(1, state.setParams.reps + delta) } }))}
                        onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, reps: Math.max(1, value ?? state.setParams.reps) } }))}
                      />
                      <ValueStepper
                        label="Вес"
                        unit="кг"
                        value={editor.setParams.weight > 0 ? editor.setParams.weight : null}
                        emptyLabel={weightlessSelected ? 'вес тела' : '—'}
                        onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: Math.max(0, state.setParams.weight + delta) } }))}
                        onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: Math.max(0, value ?? 0) } }))}
                        onReset={() => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: 0 } }))}
                      />
                      <ValueStepper
                        label="Отдых"
                        unit="сек"
                        value={editor.setParams.restSeconds}
                        onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, restSeconds: Math.max(15, state.setParams.restSeconds + delta * 15) } }))}
                        onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, restSeconds: Math.max(15, value ?? state.setParams.restSeconds) } }))}
                      />
                      <ValueStepper
                        label="Длительность"
                        unit="сек"
                        value={editor.setParams.durationSeconds ?? null}
                        emptyLabel="не задана"
                        onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: adjustOptionalSeconds(state.setParams.durationSeconds, delta, 15) } }))}
                        onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: value ?? undefined } }))}
                        onReset={() => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: undefined } }))}
                      />
                    </div>

                    <ExercisePlanStrengthSets item={selectedExerciseItem.item} modes={data.strengthModes} />

                    <div>
                      <Button variant="secondary" iconLeft={<SlidersHorizontal aria-hidden="true" />} aria-haspopup="dialog" onClick={() => setDetailsOpen(true)}>Режим и комментарий</Button>
                    </div>
                  </>
                ) : (
                  <div className="forma-state">
                    <p className="font-display text-3xl font-bold text-white">Добавьте упражнение</p>
                    <p>Выберите упражнение слева или добавьте новое — здесь появятся видео, подходы и нагрузка.</p>
                  </div>
                )}
              </section>
            </div>

            <div className="builder-actions" role="group" aria-label="Действия с тренировкой">
              <Button onClick={() => void handleDone()} disabled={saveStatus === 'saving'}>Готово</Button>
              <span className="builder-save-status" role="status" data-status={saveStatus}>
                {saveStatus === 'saving' ? 'Сохранение…' : saveStatus === 'error' ? 'Не удалось сохранить изменения' : 'Все изменения сохранены'}
              </span>
              {saveStatus === 'error' ? <Button variant="secondary" onClick={retrySave}>Повторить</Button> : null}
              {selectedProgram ? (
                <Button variant="secondary" className="builder-danger builder-actions-delete" iconLeft={<Trash2 aria-hidden="true" />} aria-haspopup="dialog" onClick={() => setDeleteDialogOpen(true)}>Удалить тренировку</Button>
              ) : null}
            </div>
          </section>
        )}

        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="builder-dialog" aria-busy={createPending}>
            <Dialog.Title className="font-display text-3xl font-bold">Создать новую тренировку?</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">
              Будет создана пустая тренировка для добавления упражнений. Существующие тренировки сохранятся.
            </Dialog.Description>
            {createError ? <p role="alert" className="mt-4 text-[#ffb4a7]">{createError}</p> : null}
            <div className="mt-6 flex flex-wrap gap-3">
              <Dialog.Close asChild><Button variant="secondary" disabled={createPending}>Отмена</Button></Dialog.Close>
              <Button disabled={createPending} onClick={() => void handleCreateWorkout()}>
                {createPending ? 'Создание…' : 'Создать тренировку'}
              </Button>
            </div>
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={Boolean(groupDialog)} onOpenChange={(open) => { if (!open) setGroupDialogId(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="builder-dialog">
            {groupDialog ? (
              <>
                <Dialog.Title className="font-display text-3xl font-bold">Группа {groupDialogIndex + 1}</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-white/70">Название, режим выполнения и перерыв после группы.</Dialog.Description>
                <label className="builder-field">
                  <span>Название группы</span>
                  <input
                    value={groupTitleDraft}
                    onChange={(event) => setGroupTitleDraft(event.target.value)}
                    onBlur={() => void saveGroupTitle(groupDialog.id, groupTitleDraft)}
                    onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void saveGroupTitle(groupDialog.id, groupTitleDraft) } }}
                  />
                </label>
                <div className="builder-field">
                  <span id="group-kind-label">Режим выполнения</span>
                  <div className="builder-chips" role="group" aria-labelledby="group-kind-label">
                    {BUILDER_GROUP_KIND_OPTIONS.map((option) => (
                      <button key={option.id} type="button" aria-pressed={groupDialog.kind === option.id} className={cn('picker-chip', groupDialog.kind === option.id && 'picker-chip-active')} onClick={() => changeGroupKind(groupDialog.id, option.id)}>
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
                {groupDialogIndex < groups.length - 1 ? (
                  <ValueStepper
                    label="Перерыв после группы"
                    unit="сек"
                    value={parseDurationSeconds(groupDialog.betweenRoundsRest) ?? 120}
                    onChange={(delta) => adjustGroupBreak(groupDialog.id, delta)}
                  />
                ) : null}
                <div className="builder-dialog-actions">
                  <Button variant="secondary" className="builder-danger" iconLeft={<Trash2 aria-hidden="true" />} disabled={groups.length <= 1} onClick={() => { setGroupDialogId(null); void handleDeleteGroup(groupDialog.id) }}>Удалить группу</Button>
                  <Dialog.Close asChild><Button>Готово</Button></Dialog.Close>
                </div>
              </>
            ) : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={detailsOpen && Boolean(editor)} onOpenChange={setDetailsOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="builder-dialog">
            {editor ? (
              <>
                <Dialog.Title className="font-display text-3xl font-bold">Режим и комментарий</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-white/70">{editor.name}</Dialog.Description>
                <div className="mt-5 space-y-5">
                  <StrengthModeSelector
                    modes={data.strengthModes}
                    selectedMode={selectedStrengthMode}
                    selectedModeId={editor.strengthModeId}
                    selectedDayType={editor.strengthDayType}
                    onSelect={(modeId, dayType) => updateEditor((state) => ({ ...state, strengthModeId: modeId, strengthDayType: dayType }))}
                  />
                  <label className="builder-field">
                    <span>Комментарий</span>
                    <textarea
                      ref={noteTextareaRef}
                      rows={3}
                      value={editor.note}
                      onChange={(event) => updateEditor((state) => ({ ...state, note: event.target.value }))}
                      onInput={(event) => resizeBuilderTextarea(event.currentTarget)}
                      aria-label="Комментарий к упражнению"
                      title="Комментарий к упражнению"
                      placeholder="Добавьте заметку по технике или нагрузке"
                    />
                  </label>
                </div>
                <div className="builder-dialog-actions">
                  <Dialog.Close asChild><Button>Готово</Button></Dialog.Close>
                </div>
              </>
            ) : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="builder-dialog">
            <Dialog.Title className="font-display text-3xl font-bold">Удалить тренировку «{workoutTitle}»?</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">Тренировка исчезнет из списка и с главной. История выполнений в календаре сохранится.</Dialog.Description>
            <div className="builder-dialog-actions">
              <Dialog.Close asChild><Button variant="secondary">Отмена</Button></Dialog.Close>
              <Button variant="secondary" className="builder-danger" iconLeft={<Trash2 aria-hidden="true" />} onClick={() => void handleDeleteWorkout()}>Удалить</Button>
            </div>
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
      <ExercisePickerModal
        open={replaceModalOpen}
        onOpenChange={(open) => {
          setReplaceModalOpen(open)
          if (!open) {
            setReplaceTargetExerciseId(null)
          }
        }}
        userId={resolvedUserId}
        mode="replace"
        currentExerciseSlug={replaceTargetExerciseItem?.item.slug}
        currentExerciseName={replaceTargetExerciseItem?.item.name ?? editor?.name ?? ''}
        onSelect={handleReplaceExercise}
      />
      <ExercisePickerModal
        open={addModalOpen}
        onOpenChange={(open) => {
          setAddModalOpen(open)
          if (!open) {
            setAddTargetPosition(null)
            if (addSlugParam) {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                next.delete('add')
                return next
              }, { replace: true, preventScrollReset: true })
            }
          }
        }}
        userId={resolvedUserId}
        mode="add"
        initialSlug={addSlugParam}
        excludeSlugs={(addTargetPosition?.groupId ?? activeGroupId) ? groups.find((group) => group.id === (addTargetPosition?.groupId ?? activeGroupId))?.items.map((item) => item.slug) : undefined}
        onSelect={handleAddExercise}
      />
    </FormaShell>
  )
}

function formatBuilderItemSummary(item: BuilderExerciseItem) {
  return [item.sets, item.load, item.rest ? `отдых ${item.rest}` : null].filter(Boolean).join(' · ')
}

function formatBuilderMuscleGroup(details: ExerciseDetails) {
  const muscles = details.primaryMuscles.length > 0 ? details.primaryMuscles : details.muscles
  return muscles.slice(0, 2).join(', ')
}

function formatBuilderSubtitle(details: ExerciseDetails) {
  const muscles = details.primaryMuscles.length > 0 ? details.primaryMuscles : details.muscles
  return [details.secondaryName, muscles.join(', ')].filter(Boolean).join(' • ')
}

function formatBuilderGroupKindLabel(kind: BuilderGroupKind) {
  return kind === 'alternating' ? 'Группа чередования' : kind === 'superset' ? 'Суперсет' : kind === 'circuit' ? 'Круг' : 'Обычное упражнение'
}

function resizeBuilderTextarea(textarea: HTMLTextAreaElement | null) {
  if (!textarea) {
    return
  }

  textarea.style.height = 'auto'
  textarea.style.height = `${textarea.scrollHeight}px`
}

function serializeBuilderGroups(groups: BuilderWorkoutGroup[]) {
  return groups.map((group) => ({
    id: group.id,
    kind: group.kind,
    title: group.title,
    rounds: group.rounds,
    betweenExercisesRest: group.betweenExercisesRest,
    betweenRoundsRest: group.betweenRoundsRest,
    items: group.items.map((item) => ({
      id: item.id,
      slug: item.slug,
      name: item.name,
      muscleGroup: item.muscleGroup,
      sets: item.sets,
      rest: item.rest,
      load: item.load,
      loadType: item.loadType,
      strengthModeId: item.strengthModeId,
      strengthDayType: item.strengthDayType ?? null,
      strengthPlan: item.strengthPlan ?? [],
    })),
  }))
}

function createBuilderSaveSnapshot(userId: string, programId: string, workoutName: string, groups: BuilderWorkoutGroup[], selectedExerciseId: string | null, selectedExercise: WorkoutBuilderData['selectedExercise'] | null) {
  return JSON.stringify({ userId, programId, workoutName, groups: serializeBuilderGroups(groups), selectedExerciseId, selectedExercise })
}

function mergeBuilderGroupsWithLocalStrength(serverGroups: BuilderWorkoutGroup[], localGroups: BuilderWorkoutGroup[]) {
  if (localGroups.length === 0) {
    return serverGroups
  }

  const localItems = new Map(localGroups.flatMap((group) => group.items.map((item) => [item.id, item] as const)))

  return serverGroups.map((group) => ({
    ...group,
    items: group.items.map((item) => {
      const localItem = localItems.get(item.id)
      if (!localItem) {
        return item
      }

      const localModeId = normalizeStrengthModeId(localItem.strengthModeId)
      const serverModeId = normalizeStrengthModeId(item.strengthModeId)
      const localPlan = localItem.strengthPlan ?? []
      const serverPlan = item.strengthPlan ?? []
      const localHasChangedStrength = localModeId !== serverModeId || (localPlan.length > 0 && JSON.stringify(localPlan) !== JSON.stringify(serverPlan))

      if (!localHasChangedStrength) {
        return item
      }

      return {
        ...item,
        strengthModeId: localModeId,
        strengthDayType: localItem.strengthDayType ?? null,
        strengthPlan: localPlan,
      }
    }),
  }))
}

function applyEditorToGroups(groups: BuilderWorkoutGroup[], selectedExerciseId: string, editor: WorkoutBuilderData['selectedExercise']) {
  return groups.map((group) => ({
    ...group,
    items: group.items.map((item) => {
      if (item.id !== selectedExerciseId) {
        return item
      }

      const loadType = inferBuilderLoadTypeFromEditor(editor, item)
      const effectiveSetParams = getEffectiveBuilderSetParams(loadType, editor.setParams, editor.loadMode, editor.tempo)
      const strengthModeId = normalizeStrengthModeId(editor.strengthModeId)
      const strengthDayType = normalizeStrengthDayType(strengthModeId, editor.strengthDayType)
      const strengthPlan = buildStrengthPlan(strengthModeId, strengthDayType, effectiveSetParams, loadType)

      return {
        ...item,
        loadType,
        sets: formatBuilderItemSets(loadType, parseBuilderSetCount(item.sets), effectiveSetParams.reps, effectiveSetParams.durationSeconds),
        load: formatBuilderItemLoad(loadType, effectiveSetParams.weight),
        rest: `${effectiveSetParams.restSeconds} сек`,
        strengthModeId,
        strengthDayType,
        strengthPlan,
      }
    }),
  }))
}

function parseBuilderSetCount(currentValue: string) {
  const match = currentValue.match(/^(\d+)/)
  return Number(match?.[1] ?? '3')
}

function getBuilderLoadType(details: Pick<ExerciseDetails, 'equipment' | 'force'>): BuilderLoadType {
  if (details.force === 'Static') {
    return 'timed'
  }

  if (['Bodyweight', 'Собственный вес', 'Stretches', 'Растяжка', 'Recovery', 'Восстановление'].includes(details.equipment)) {
    return 'bodyweight'
  }

  return 'weighted'
}

function inferBuilderLoadTypeFromItem(item?: Pick<BuilderExerciseItem, 'load' | 'sets' | 'loadType'> | null): BuilderLoadType {
  if (item?.loadType) {
    return item.loadType
  }

  if (item?.sets.includes('сек')) {
    return 'timed'
  }

  if (item?.load.toLowerCase().includes('вес')) {
    return 'bodyweight'
  }

  return 'weighted'
}

function inferBuilderLoadTypeFromEditor(editor: BuilderExerciseEditor | null, item?: Pick<BuilderExerciseItem, 'load' | 'sets' | 'loadType'> | null): BuilderLoadType {
  if (editor?.loadType) {
    return editor.loadType
  }

  if (item) {
    return inferBuilderLoadTypeFromItem(item)
  }

  return editor?.setParams.weight ? 'weighted' : 'bodyweight'
}

function normalizeBuilderEditor(editor: WorkoutBuilderData['selectedExercise'], groups: BuilderWorkoutGroup[], selectedExerciseId: string) {
  const selectedItem = groups.flatMap((group) => group.items).find((item) => item.id === selectedExerciseId)
  const loadType = inferBuilderLoadTypeFromEditor(editor, selectedItem)
  const strengthModeId = normalizeStrengthModeId(editor.strengthModeId)
  const strengthDayType = normalizeStrengthDayType(strengthModeId, editor.strengthDayType)
  const setParams = {
    ...editor.setParams,
    durationSeconds: typeof editor.setParams.durationSeconds === 'number'
      ? editor.setParams.durationSeconds
      : parseDurationSeconds(selectedItem?.sets),
  }
  const effectiveSetParams = getEffectiveBuilderSetParams(loadType, setParams, editor.loadMode, editor.tempo)

  return {
    ...editor,
    loadType,
    setParams,
    effectiveSetParams,
    strengthModeId,
    strengthDayType,
    strengthPlan: buildStrengthPlan(strengthModeId, strengthDayType, effectiveSetParams, loadType),
  }
}

function formatBuilderItemLoad(loadType: BuilderLoadType, weight: number) {
  if (loadType !== 'weighted') {
    return 'вес тела'
  }

  if (weight <= 0) {
    return '—'
  }

  return `${formatBuilderWeight(weight)} кг`
}

function formatBuilderItemSets(loadType: BuilderLoadType, sets: number, reps: number, durationSeconds?: number) {
  if (loadType === 'timed' && typeof durationSeconds === 'number') {
    return `${sets}×${durationSeconds} сек`
  }

  const durationSuffix = typeof durationSeconds === 'number' ? ` · ${durationSeconds} сек` : ''
  return `${sets}×${reps}${durationSuffix}`
}

function getBuilderDuration(details: Pick<ExerciseDetails, 'equipment' | 'force' | 'loadSettings'>) {
  return getBuilderLoadType(details) === 'timed' ? details.loadSettings.reps : undefined
}

function parseDurationSeconds(value?: string) {
  const matches = [...(value?.matchAll(/(\d+)\s*сек/gi) ?? [])]
  const lastMatch = matches.at(-1)
  return lastMatch ? Number(lastMatch[1]) : undefined
}

function adjustOptionalSeconds(value: number | undefined, delta: number, step: number) {
  if (typeof value !== 'number') {
    return delta > 0 ? step : undefined
  }

  const next = value + delta * step
  return next > 0 ? next : undefined
}

function getBuilderLoadModeRule(mode: string) {
  return BUILDER_LOAD_MODE_RULES[mode] ?? BUILDER_LOAD_MODE_RULES['Обычный вес']
}

function getBuilderTempoRule(tempo: string) {
  return BUILDER_TEMPO_RULES[tempo] ?? BUILDER_TEMPO_RULES['Обычный']
}

function getEffectiveBuilderSetParams(loadType: BuilderLoadType, setParams: BuilderExerciseEditor['setParams'], loadMode: string, tempo: string) {
  const loadModeRule = getBuilderLoadModeRule(loadMode)
  const tempoRule = getBuilderTempoRule(tempo)
  const durationSeconds = typeof setParams.durationSeconds === 'number'
    ? Math.max(1, Math.round(setParams.durationSeconds * loadModeRule.durationFactor * tempoRule.durationFactor))
    : undefined

  return {
    reps: Math.max(1, Math.round(setParams.reps * loadModeRule.repsFactor * tempoRule.repsFactor)),
    weight: loadType === 'weighted'
      ? Math.max(0, Math.round(setParams.weight * loadModeRule.weightFactor * tempoRule.weightFactor))
      : Math.max(0, setParams.weight),
    restSeconds: Math.max(15, setParams.restSeconds + loadModeRule.restDelta + tempoRule.restDelta),
    durationSeconds,
  }
}

function formatBuilderWeight(weight: number) {
  return `${weight}`.replace(/(\.\d*?)0+$/, '$1').replace(/\.0$/, '')
}

function ExercisePlanVideo({ videoUrl, title }: { videoUrl?: string; title: string }) {
  if (!videoUrl) {
    return <div className="aspect-video w-full rounded-[22px] border border-white/8 bg-[#0b1017]" />
  }

  return (
    <ExerciseVideoPlayer
      videoUrl={videoUrl}
      videoLabel={`${title} · видео в плане`}
      lazyLoad
      wrapperClassName="aspect-video w-full rounded-[22px] border border-white/8 bg-[#0b1017]"
    />
  )
}

function ExercisePlanMuscleMap({ muscles, fallbackLabel, figureGender, title }: { muscles?: string[]; fallbackLabel: string; figureGender: 'male' | 'female'; title: string }) {
  const muscleLabels = muscles?.length ? muscles : [fallbackLabel]

  return (
    <CompactBodyMapMini
      muscles={muscleLabels}
      figureGender={figureGender}
      label={`${title} · мышцы в плане`}
      className="rounded-[26px] border-white/6 bg-[#0b1017]/72 p-3"
      figureContainerClassName="h-[220px] p-0"
      figureMarkupClassName="max-w-[112px]"
    />
  )
}

function ExercisePlanStrengthSets({ item, modes }: { item: BuilderExerciseItem; modes: StrengthTrainingMode[] }) {
  const strengthModeId = normalizeStrengthModeId(item.strengthModeId)
  const strengthDayType = normalizeStrengthDayType(strengthModeId, item.strengthDayType)
  const mode = modes.find((entry) => entry.id === strengthModeId)
  const dayLabel = mode?.dayOptions.find((option) => option.id === strengthDayType)?.label
  const plan = item.strengthPlan?.length ? item.strengthPlan : buildStrengthPlan(strengthModeId, strengthDayType, getBuilderItemSetParams(item), inferBuilderLoadTypeFromItem(item))

  return (
    <div className="rounded-[22px] border border-white/8 bg-[#0d1116]/82 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[#d6b05f]/18 bg-[#d6b05f]/10 px-3 py-1 text-xs font-semibold text-[#f2cf87]">
          <Target className="h-3.5 w-3.5" />
          <span>{mode?.title ?? 'Базовый режим'}</span>
          {dayLabel ? <span className="text-[#f2cf87]/58">• {dayLabel}</span> : null}
        </div>
        <div className="text-xs text-white/38">{formatStrengthPlanSummary(plan, item)}</div>
      </div>

      <div className="mt-2 space-y-1.5">
        {plan.map((set) => {
          const Icon = getStrengthSetIcon(set.setType)
          return (
            <div
              key={`${set.setNumber}-${set.label}-${set.targetRepsLabel}`}
              title={set.note}
              className={cn(
                'grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 rounded-[14px] border px-2.5 py-2',
                getStrengthSetToneClass(set.setType),
              )}
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/10 bg-black/18">
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0">
                  <div className="truncate font-semibold text-white">{formatStrengthSetMainLine(set, item)}</div>
                  <div className="mt-0.5 truncate text-[11px] opacity-68">{set.setNumber}. {getSetTypeLabel(set.setType)} · {set.rirLabel}</div>
                </div>
              </div>
              <div className="hidden items-center gap-1 rounded-full bg-white/6 px-2 py-1 text-[11px] text-white/58 2xl:inline-flex">
                <Repeat2 className="h-3 w-3" />
                {formatStrengthSetTargetMeta(set, item)}
              </div>
              <div className="inline-flex items-center gap-1 rounded-full bg-white/6 px-2 py-1 text-[11px] text-white/58">
                <Timer className="h-3 w-3" />
                {set.restSeconds} сек
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function getBuilderItemSetParams(item: BuilderExerciseItem) {
  const reps = parseBuilderTargetValue(item.sets)
  const restSeconds = parseDurationSeconds(item.rest) ?? 120
  const durationSeconds = parseDurationSeconds(item.sets)

  return {
    reps,
    weight: parseBuilderWeightValue(item.load),
    restSeconds,
    ...(durationSeconds ? { durationSeconds } : {}),
  }
}

function parseBuilderTargetValue(value: string) {
  const match = value.match(/[×x]\s*(\d+)/i)
  if (match) {
    return Math.max(1, Number(match[1]))
  }

  const fallback = value.match(/\d+/)
  return Math.max(1, Number(fallback?.[0] ?? '10'))
}

function parseBuilderWeightValue(value: string) {
  const match = value.replace(',', '.').match(/\d+(?:\.\d+)?/)
  return Number(match?.[0] ?? '0')
}

function formatStrengthSetMainLine(set: StrengthSetPlan, item: BuilderExerciseItem) {
  const target = item.loadType === 'timed'
    ? `${parseDurationSeconds(item.sets) ?? parseBuilderTargetValue(item.sets)} сек`
    : set.targetRepsLabel

  return `${set.recommendedWeightLabel} × ${target}`
}

function formatStrengthSetTargetMeta(set: StrengthSetPlan, item: BuilderExerciseItem) {
  if (item.loadType === 'timed') {
    return 'длительность'
  }

  if (set.targetRepsLabel === 'максимум') {
    return 'макс. повт.'
  }

  return 'повторы'
}

function formatStrengthPlanSummary(plan: StrengthSetPlan[], item: BuilderExerciseItem) {
  const restValues = plan.map((set) => set.restSeconds)
  const minRest = Math.min(...restValues)
  const maxRest = Math.max(...restValues)
  const restLabel = minRest === maxRest ? `${minRest} сек отдых` : `${minRest}–${maxRest} сек отдых`
  const volume = item.loadType === 'weighted' ? calculateStrengthPlanVolume(plan) : 0
  const volumeLabel = volume > 0 ? ` • ≈ ${formatBuilderWeight(volume)} кг` : ''

  return `${formatSetCountLabel(plan.length)} • ${restLabel}${volumeLabel}`
}

function calculateStrengthPlanVolume(plan: StrengthSetPlan[]) {
  return Math.round(
    plan.reduce((total, set) => {
      const weight = parseBuilderWeightValue(set.recommendedWeightLabel)
      const reps = getStrengthTargetMaxReps(set.targetRepsLabel)
      return total + weight * reps
    }, 0),
  )
}

function getStrengthTargetMaxReps(value: string) {
  const numbers = [...value.matchAll(/\d+/g)].map((match) => Number(match[0]))
  return numbers.length ? Math.max(...numbers) : 1
}

function formatSetCountLabel(count: number) {
  if (count % 10 === 1 && count % 100 !== 11) {
    return `${count} подход`
  }

  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) {
    return `${count} подхода`
  }

  return `${count} подходов`
}

function getStrengthSetIcon(setType: StrengthSetType) {
  if (setType === 'warmup') {
    return Gauge
  }

  if (setType === 'failure') {
    return Flame
  }

  return Dumbbell
}

function getStrengthSetToneClass(setType: StrengthSetType) {
  if (setType === 'warmup') {
    return 'border-white/8 bg-white/[0.045] text-white/62'
  }

  if (setType === 'failure') {
    return 'border-[#eb5345]/28 bg-[#eb5345]/10 text-[#ffb1a8]'
  }

  return 'border-[#d6b05f]/16 bg-[#d6b05f]/8 text-[#f2cf87]'
}

function BuilderWarningIcon({ warning }: { warning: WorkoutBuilderData['warnings'][number] }) {
  const Icon = warning.tone === 'success' ? CheckCircle2 : warning.tone === 'blocked' ? OctagonAlert : AlertTriangle

  return (
    <div
      title={`${warning.title}: ${warning.description}`}
      aria-label={`${warning.title}: ${warning.description}`}
      className={cn(
        'inline-flex h-11 items-center justify-center gap-2 rounded-2xl border px-3 text-xs font-semibold',
        warning.tone === 'success'
          ? 'border-[#6ecf71]/25 bg-[#6ecf71]/10 text-[#9ff5a2]'
          : warning.tone === 'blocked'
            ? 'border-[#eb5345]/28 bg-[#eb5345]/10 text-[#ffb1a8]'
            : 'border-[#f0d08c]/25 bg-[#d6b05f]/10 text-[#f0d08c]',
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="max-w-[150px] truncate">{warning.title}</span>
    </div>
  )
}

function StrengthModeSelector({ modes, selectedMode, selectedModeId, selectedDayType, onSelect }: { modes: StrengthTrainingMode[]; selectedMode?: StrengthTrainingMode; selectedModeId: string; selectedDayType?: string | null; onSelect: (modeId: string, dayType?: string | null) => void }) {
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    function handlePointerDown(event: MouseEvent) {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  if (modes.length === 0) {
    return null
  }

  return (
    <div ref={dropdownRef} className="relative">
      <div className="mb-2 text-sm text-white/45">
        <span>Режим силовой тренировки</span>
      </div>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label="Выбрать режим силовой тренировки"
        title="Выбрать режим силовой тренировки"
        className="flex w-full items-center justify-between gap-3 rounded-[22px] border border-[#d6b05f]/24 bg-[#d6b05f]/10 px-4 py-3 text-left transition hover:border-[#d6b05f]/40 hover:bg-[#d6b05f]/14"
      >
        <div className="min-w-0">
          <div className="truncate font-display text-xl font-bold text-white">{selectedMode?.title ?? 'Базовый режим'}</div>
          <div className="mt-1 truncate text-sm text-white/52">{selectedMode?.shortDescription ?? 'Выберите структуру подходов.'}</div>
        </div>
        <span className={cn('shrink-0 text-lg text-[#f2cf87] transition', open ? 'rotate-180' : undefined)}>⌄</span>
      </button>
      {open ? (
        <div className="absolute inset-x-0 top-[calc(100%+8px)] z-40 max-h-[360px] overflow-y-auto rounded-[24px] border border-white/10 bg-[#151922] p-2 shadow-[0_22px_70px_rgba(0,0,0,0.48)]">
          {modes.map((mode) => {
            const active = mode.id === selectedModeId
            return (
              <button
                key={mode.id}
                type="button"
                onClick={() => {
                  onSelect(mode.id, mode.defaultDayType ?? null)
                  setOpen(false)
                }}
                className={cn(
                  'w-full rounded-[18px] px-3 py-3 text-left transition',
                  active ? 'bg-[#d6b05f]/14 text-white' : 'text-white/62 hover:bg-white/7 hover:text-white',
                )}
              >
                <div className="font-display text-lg font-bold tracking-[-0.03em]">{mode.title}</div>
                <div className="mt-0.5 text-xs leading-5 opacity-70">{mode.shortDescription}</div>
              </button>
            )
          })}
        </div>
      ) : null}
      {selectedMode?.dayOptions.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {selectedMode.dayOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              title={option.description}
              onClick={() => onSelect(selectedMode.id, option.id)}
              className={cn(
                'rounded-full border px-3 py-2 text-xs transition',
                selectedDayType === option.id ? 'border-[#d6b05f]/35 bg-[#d6b05f]/14 text-[#f2cf87]' : 'border-white/8 bg-white/4 text-white/55 hover:text-white',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}