import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Dumbbell, Flame, Gauge, ListTree, OctagonAlert, Plus, Repeat2, Replace, Target, Timer, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { CompactBodyMapMini, ExerciseVideoPlayer, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { ExercisePickerModal } from '@/shared/ui/training/exercise-picker-modal'
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
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null)
  const [groupTitleDraft, setGroupTitleDraft] = useState('')
  const [replaceModalOpen, setReplaceModalOpen] = useState(false)
  const [replaceTargetExerciseId, setReplaceTargetExerciseId] = useState<string | null>(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addTargetPosition, setAddTargetPosition] = useState<{ groupId: string; index: number } | null>(null)
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

  const fatigueSummary = useMemo(() => buildBuilderFatigueSummary(groups), [groups])

  if (error) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить конструктор тренировки. Проверьте backend API.</div>
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
      .then(() => undefined)
      .catch(() => {
        if (lastSavePromiseRef.current === savePromise) {
          lastSavedSnapshotRef.current = null
        }
      })
      .finally(() => {
        if (lastSavePromiseRef.current === savePromise) {
          lastSavePromiseRef.current = null
        }
      })

    lastSavePromiseRef.current = savePromise
    await savePromise
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

    if (!normalizedTitle) {
      setGroupTitleDraft(currentGroup.title)
      setEditingGroupId(null)
      return
    }

    await updateGroup(groupId, (group) => ({ ...group, title: normalizedTitle }))
    setGroupTitleDraft(normalizedTitle)
    setEditingGroupId(null)
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

  async function handleCreateWorkout() {
    if (!data) {
      return
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

    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('programId', response.id)
      next.delete('selectedExerciseId')
      return next
    })
  }

  async function handleDeleteWorkout() {
    if (!data || !selectedProgramId || !selectedProgram) {
      return
    }

    const fallbackProgram = data.programs.find((program) => program.id !== selectedProgramId)
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

    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (fallbackProgram) {
        next.set('programId', fallbackProgram.id)
      }
      else {
        next.delete('programId')
      }
      next.delete('selectedExerciseId')
      return next
    })
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
    const currentEditor = editorRef.current
    if (!currentEditor) {
      return
    }

    const nextGroups = groupsRef.current.filter((group) => group.id !== groupId)
    const remainingItems = nextGroups.flatMap((group) => group.items)
    if (remainingItems.length === 0) {
      return
    }

    const selectedStillExists = remainingItems.some((item) => item.id === selectedExerciseId)
    const nextSelectedExerciseId = selectedStillExists ? selectedExerciseId : remainingItems[0].id
    await saveGroups(nextGroups, nextSelectedExerciseId, currentEditor)
    if (nextSelectedExerciseId !== selectedExerciseId) {
      void selectExercise(nextSelectedExerciseId, { skipSave: true })
    }
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
                affectsFatigue: details.equipment !== 'Recovery',
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
      affectsFatigue: details.equipment !== 'Recovery',
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
    const nextGroups = groups
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.id !== exerciseId),
      }))
      .filter((group) => group.items.length > 0)

    const remainingItems = nextGroups.flatMap((group) => group.items)
    const nextSelectedItem = remainingItems.find((item) => item.id === selectedExerciseId) ?? remainingItems[0]
    if (!nextSelectedItem) {
      return
    }

    await apiPut('/api/builder/plan', {
      userId: resolvedUserId,
      programId: selectedProgramId,
      workoutName: workoutTitleRef.current,
      groups: serializeBuilderGroups(nextGroups),
      selectedExerciseId: nextSelectedItem.id,
    })

    setGroups(nextGroups)
    void selectExercise(nextSelectedItem.id, { skipSave: true })
  }

  function handleDownloadWorkoutJson() {
    const exportData = buildBuilderWorkoutJsonExport(workoutTitleRef.current, groupsRef.current)
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json;charset=utf-8' })
    const downloadUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')

    link.href = downloadUrl
    link.download = createBuilderWorkoutJsonFileName(workoutTitleRef.current)
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0)
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title={data.title}
        description=""
        actions={
          <div className="flex flex-wrap gap-3">
            <Button iconLeft={<Plus className="h-4 w-4" />} onClick={() => void handleCreateWorkout()}>Новая тренировка</Button>
          </div>
        }
      />

      <section className="mb-6 glass-panel rounded-[32px] p-3">
        <div className="flex flex-wrap gap-3">
          {data.programs.map((program) => {
            const active = program.id === selectedProgramId
            return (
              <button
                key={program.id}
                type="button"
                onClick={() => handleSelectProgram(program.id)}
                className={cn(
                  'min-w-[190px] rounded-[24px] border px-5 py-4 text-left transition',
                  active ? 'border-[#d6b05f]/35 bg-[#d6b05f]/12 text-white' : 'border-white/8 bg-white/4 text-white/64 hover:bg-white/7 hover:text-white',
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="font-display text-2xl font-bold tracking-[-0.04em]">{program.name}</span>
                  {program.recommendedToday ? <span className="rounded-full bg-[#6ecf71]/14 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#9ff5a2]">Сегодня</span> : null}
                </div>
                <div className="mt-1 text-xs text-white/42">{program.subtitle}</div>
              </button>
            )
          })}
          {!hasPrograms ? <div className="px-3 py-4 text-sm text-white/48">Все тренировки удалены. Создайте новую тренировку.</div> : null}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <section className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="mb-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm uppercase tracking-[0.24em] text-white/35">План тренировки</div>
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
                      className="mt-2 w-full rounded-[18px] border border-[#d6b05f]/35 bg-[#0f1217] px-3 py-2 font-display text-4xl font-bold text-white outline-none"
                    />
                  ) : selectedProgram ? (
                    <button
                      type="button"
                      onClick={() => {
                        setTitleDraft(workoutTitle)
                        setIsEditingWorkoutTitle(true)
                      }}
                      className="mt-2 text-left font-display text-4xl font-bold text-white transition hover:text-[#f2cf87]"
                    >
                      {workoutTitle}
                    </button>
                  ) : (
                    <div className="mt-2 font-display text-4xl font-bold text-white/72">{workoutTitle}</div>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {selectedProgram ? <Button variant="secondary" onClick={handleDownloadWorkoutJson}>JSON</Button> : null}
                  {selectedProgram ? <Button variant="secondary" onClick={() => void handleAddGroup()}>Добавить группу</Button> : null}
                  {selectedProgram ? (
                    <button
                      type="button"
                      onClick={() => void handleDeleteWorkout()}
                      aria-label={`Удалить тренировку ${workoutTitle}`}
                      title="Удалить тренировку"
                      className="inline-flex h-10 items-center justify-center gap-2 rounded-2xl border border-[#eb5345]/18 bg-[#eb5345]/8 px-4 text-sm font-semibold text-[#ff8d82] transition hover:bg-[#eb5345]/14 hover:text-[#ffb1a8]"
                    >
                      <Trash2 className="h-4.5 w-4.5" />
                      <span>Удалить тренировку</span>
                    </button>
                  ) : null}
                </div>
              </div>
              {data.warnings.length > 0 || data.info.duration ? (
                <div className="flex flex-wrap gap-2">
                  {data.info.duration ? (
                    <div className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/4 px-3 text-xs font-semibold text-white/68">
                      <Timer className="h-4 w-4 shrink-0" />
                      <span>{data.info.duration}</span>
                    </div>
                  ) : null}
                  {data.warnings.map((warning) => (
                    <BuilderWarningIcon key={warning.title} warning={warning} />
                  ))}
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              {groups.map((group, index) => (
                <div key={group.id} className="rounded-[28px] border border-white/8 bg-[#111419] p-5 pb-8">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs uppercase tracking-[0.18em] text-white/30">{formatBuilderGroupKindLabel(group.kind)}</div>
                      {editingGroupId === group.id ? (
                        <input
                          aria-label="Название группы"
                          title="Название группы"
                          value={groupTitleDraft}
                          onChange={(event) => setGroupTitleDraft(event.target.value)}
                          onBlur={() => {
                            setGroupTitleDraft(group.title)
                            setEditingGroupId(null)
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.preventDefault()
                              void saveGroupTitle(group.id, groupTitleDraft)
                            }

                            if (event.key === 'Escape') {
                              setGroupTitleDraft(group.title)
                              setEditingGroupId(null)
                            }
                          }}
                          autoFocus
                          className="mt-2 w-full rounded-[16px] border border-[#d6b05f]/35 bg-[#0f1217] px-3 py-2 font-display text-3xl font-bold text-white outline-none"
                        />
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setGroupTitleDraft(group.title)
                            setEditingGroupId(group.id)
                          }}
                          className="mt-2 text-left font-display text-3xl font-bold text-white transition hover:text-[#f2cf87]"
                        >
                          {index + 1}. {group.title}
                        </button>
                      )}
                      <div className="mt-2 text-sm text-white/45">{group.rounds ?? 'Основной блок'} {group.betweenExercisesRest ? `• Отдых между упражнениями ${group.betweenExercisesRest}` : ''}</div>
                    </div>
                    <div className="flex items-center gap-2 self-start">
                      <div className="flex items-center gap-1.5">
                        {BUILDER_GROUP_KIND_OPTIONS.map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => changeGroupKind(group.id, option.id)}
                            className={cn(
                              'rounded-full border px-3 py-1.5 text-xs transition',
                              group.kind === option.id
                                ? 'border-[#d6b05f]/35 bg-[#d6b05f]/14 text-[#f2cf87]'
                                : 'border-white/8 bg-white/4 text-white/55 hover:text-white',
                            )}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => void handleDeleteGroup(group.id)}
                        aria-label={`Удалить группу ${group.title}`}
                        title="Удалить группу"
                        className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#ff8d82] transition hover:bg-[#eb5345]/12 hover:text-[#ffb1a8]"
                      >
                        <Trash2 className="h-4.5 w-4.5" />
                      </button>
                    </div>
                  </div>

                  <div className="relative mt-4 rounded-[24px] border border-white/8">
                    <div className="overflow-x-auto rounded-[24px]">
                      <div>
                        <div className="grid min-w-[1040px] grid-cols-[minmax(420px,0.95fr)_minmax(500px,1.2fr)] gap-4 bg-white/4 px-5 py-3 text-sm text-white/45">
                          <div>Упражнение</div>
                          <div>Режим и подходы</div>
                        </div>
                        {group.items.length > 0 ? (
                          <InlineAddExerciseButton
                            onClick={() => {
                              setAddTargetPosition({ groupId: group.id, index: 0 })
                              setAddModalOpen(true)
                            }}
                          />
                        ) : (
                          <div className="min-w-[1040px] border-t border-white/8 px-5 py-8 text-center">
                            <button
                              type="button"
                              onClick={() => {
                                setAddTargetPosition({ groupId: group.id, index: 0 })
                                setAddModalOpen(true)
                              }}
                              className="inline-flex items-center gap-2 font-display text-2xl font-bold tracking-[-0.03em] text-white/58 transition hover:text-[#f2cf87]"
                            >
                              <Plus className="h-5 w-5" />
                              Добавь упражнения
                            </button>
                          </div>
                        )}
                        {group.items.map((item, itemIndex) => (
                          <div key={item.id}>
                            <div
                              className={cn(
                                'relative grid min-w-[1040px] grid-cols-[minmax(420px,0.95fr)_minmax(500px,1.2fr)] items-stretch gap-4 border-t border-white/8 py-4 pl-4 pr-2 text-sm text-white/74 transition hover:bg-white/[0.035]',
                                item.id === selectedExerciseId ? 'bg-[#d6b05f]/8 shadow-[inset_3px_0_0_rgba(214,176,95,0.55)]' : undefined,
                              )}
                            >
                              <button
                                type="button"
                                onClick={() => void selectExercise(item.id)}
                                aria-label={`Выбрать упражнение ${item.name}`}
                                title={`Выбрать упражнение ${item.name}`}
                                className="col-span-2 grid grid-cols-[minmax(420px,0.95fr)_minmax(500px,1.2fr)] gap-4 pr-10 text-left text-sm text-white/74"
                              >
                                <ExercisePlanMediaCard item={item} />
                                <ExercisePlanStrengthSets item={item} modes={data.strengthModes} />
                              </button>
                              <div className="absolute right-2 top-4 z-20">
                                <ExercisePlanRightPanel
                                  item={item}
                                  onReplace={() => {
                                    void selectExercise(item.id)
                                    setReplaceTargetExerciseId(item.id)
                                    setReplaceModalOpen(true)
                                  }}
                                  onDelete={() => void handleDeleteExercise(item.id)}
                                />
                              </div>
                            </div>
                            {itemIndex < group.items.length - 1 ? (
                              <InlineAddExerciseButton
                                onClick={() => {
                                  setAddTargetPosition({ groupId: group.id, index: itemIndex + 1 })
                                  setAddModalOpen(true)
                                }}
                              />
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                    {group.items.length > 0 ? (
                      <BottomInlineAddExerciseButton
                        onClick={() => {
                          setAddTargetPosition({ groupId: group.id, index: group.items.length })
                          setAddModalOpen(true)
                        }}
                      />
                    ) : null}
                  </div>
                  {index < groups.length - 1 ? (
                    <div className="mt-5 flex justify-end">
                      <div className="inline-flex items-center gap-2 rounded-2xl border border-white/8 bg-white/4 px-2 py-1.5 text-xs text-white/68">
                        <span>Перерыв после группы</span>
                        <button type="button" onClick={() => adjustGroupBreak(group.id, -1)} className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-[#0d1116] text-white/72 transition hover:text-white">-</button>
                        <span className="min-w-[54px] text-center font-semibold text-white">{group.betweenRoundsRest ?? '120 сек'}</span>
                        <button type="button" onClick={() => adjustGroupBreak(group.id, 1)} className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-[#0d1116] text-white/72 transition hover:text-white">+</button>
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-6">
            <section className="glass-panel rounded-[32px] p-5">
              <div className="mb-4 flex items-center gap-3 text-white/45"><ListTree className="h-4 w-4" />Сводка тренировки</div>
              <div className="grid gap-4 md:grid-cols-4">
                {data.summaryCards.map((card) => (
                  <div key={card.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                    <div className="font-display text-4xl font-bold text-white">{card.value}</div>
                    <div className="mt-2 text-sm text-white/45">{card.label}</div>
                    <div className="mt-1 text-xs text-white/32">{card.hint}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                <div className="rounded-[28px] border border-white/8 bg-[#0d1116]/82 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 text-sm text-white/45">
                        <Flame className="h-4 w-4 text-[#f08b2e]" />
                        Суммарная усталость мышц
                      </div>
                      <div className="mt-2 font-display text-4xl font-bold text-white">{fatigueSummary.totalScore}</div>
                    </div>
                    <div className="rounded-full border border-white/8 bg-white/5 px-3 py-1 text-xs text-white/58">
                      {fatigueSummary.muscles.length} мышц
                    </div>
                  </div>
                  <div className="mt-4 rounded-[26px] border border-white/6 bg-[#0b1017]/72 p-3">
                    <CompactBodyMapMini
                      muscles={fatigueSummary.highlightedMuscles}
                      figureGender={figureGender}
                      label="Суммарная усталость мышц тренировки"
                      className="rounded-[26px] border-white/6 bg-transparent p-0"
                      figureContainerClassName="h-[220px] p-0"
                      figureMarkupClassName="max-w-[112px]"
                    />
                  </div>
                </div>

                <div className="rounded-[28px] border border-white/8 bg-[#0d1116]/82 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
                  <div className="text-sm text-white/45">Наиболее нагруженные мышцы</div>
                  <div className="mt-3 grid gap-2">
                    {fatigueSummary.muscles.length > 0 ? fatigueSummary.muscles.map((muscle) => (
                      <div key={muscle.name} className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-2">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <span className="truncate text-white/78">{muscle.name}</span>
                          <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', getBuilderFatigueToneClass(muscle.status))}>{muscle.score}</span>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-white/8">
                          <div className={cn('h-full rounded-full transition-all', getBuilderFatigueBarClass(muscle.status), getBuilderFatigueWidthClass(muscle.score))} />
                        </div>
                      </div>
                    )) : (
                      <div className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-4 text-sm text-white/45">
                        В плане пока нет упражнений, создающих заметную усталость мышц.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel flex flex-col rounded-[32px] p-5 xl:sticky xl:top-4 xl:max-h-[calc(100vh-32px)] xl:self-start xl:overflow-hidden">
            {editor ? (
              <>
                <div className="shrink-0">
                  <div className="font-display text-2xl font-bold tracking-[-0.035em] text-white">{editor.name}</div>
                  <div className="mb-3 mt-2 text-white/45">{editor.subtitle}</div>
                </div>

                <div className="scrollbar-hidden min-h-0 flex-1 xl:overflow-y-auto xl:overscroll-contain">
                  {selectedExerciseItem ? (
                    <div className="mt-5 rounded-[30px] border border-white/8 bg-white/[0.035] p-3">
                      <ExercisePlanMuscleMap
                        muscles={selectedExerciseItem.item.muscles}
                        fallbackLabel={selectedExerciseItem.item.muscleGroup}
                        figureGender={figureGender}
                        title={selectedExerciseItem.item.name}
                      />
                    </div>
                  ) : null}

                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <ControlBlock
                      label="Повторы"
                      value={editor.setParams.reps}
                      onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, reps: Math.max(1, state.setParams.reps + delta) } }))}
                      onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, reps: Math.max(1, value ?? state.setParams.reps) } }))}
                    />
                    <ControlBlock
                      label="Вес"
                      value={editor.setParams.weight > 0 ? editor.setParams.weight : null}
                      suffix="кг"
                      emptyLabel="—"
                      onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: Math.max(0, state.setParams.weight + delta) } }))}
                      onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: Math.max(0, value ?? 0) } }))}
                      onReset={() => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, weight: 0 } }))}
                      resetLabel="Убрать"
                    />
                    <ControlBlock
                      label="Длительность"
                      value={editor.setParams.durationSeconds ?? null}
                      suffix={editor.setParams.durationSeconds ? 'сек' : undefined}
                      emptyLabel="не задана"
                      compactEmpty
                      onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: adjustOptionalSeconds(state.setParams.durationSeconds, delta, 15) } }))}
                      onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: value ?? undefined } }))}
                      onReset={() => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, durationSeconds: undefined } }))}
                      resetLabel="Убрать"
                    />
                    <ControlBlock
                      label="Отдых"
                      value={editor.setParams.restSeconds}
                      suffix="сек"
                      onChange={(delta) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, restSeconds: Math.max(15, state.setParams.restSeconds + delta * 15) } }))}
                      onValueCommit={(value) => updateEditor((state) => ({ ...state, setParams: { ...state.setParams, restSeconds: Math.max(15, value ?? state.setParams.restSeconds) } }))}
                    />
                  </div>

                  <div className="mt-5 space-y-4">
                    <StrengthModeSelector
                      modes={data.strengthModes}
                      selectedMode={selectedStrengthMode}
                      selectedModeId={editor.strengthModeId}
                      selectedDayType={editor.strengthDayType}
                      onSelect={(modeId, dayType) => updateEditor((state) => ({ ...state, strengthModeId: modeId, strengthDayType: dayType }))}
                    />
                    <div>
                      <div className="mb-2 text-sm text-white/45">Комментарий</div>
                      <textarea
                        ref={noteTextareaRef}
                        rows={3}
                        value={editor.note}
                        onChange={(event) => updateEditor((state) => ({ ...state, note: event.target.value }))}
                        onInput={(event) => resizeBuilderTextarea(event.currentTarget)}
                        aria-label="Комментарий к упражнению"
                        title="Комментарий к упражнению"
                        placeholder="Добавьте заметку по технике или нагрузке"
                        className="w-full resize-none overflow-hidden rounded-[24px] border border-white/8 bg-white/4 px-4 py-3 text-sm text-white outline-none placeholder:text-white/24"
                      />
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex min-h-[360px] flex-1 items-center justify-center rounded-[28px] border border-white/8 bg-white/[0.035] px-6 text-center">
                <div>
                  <div className="font-display text-3xl font-bold tracking-[-0.035em] text-white">Добавьте упражнение</div>
                  <div className="mt-2 text-sm text-white/45">Выберите упражнение в пустой группе, чтобы справа появились параметры нагрузки.</div>
                </div>
              </div>
            )}
          </section>
        </aside>
      </div>

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
          }
        }}
        userId={resolvedUserId}
        mode="add"
        title="Добавить упражнение"
        description="Каталог открыт в режиме быстрого добавления в текущую группу плана."
        excludeSlugs={(addTargetPosition?.groupId ?? activeGroupId) ? groups.find((group) => group.id === (addTargetPosition?.groupId ?? activeGroupId))?.items.map((item) => item.slug) : undefined}
        onSelect={handleAddExercise}
      />
    </FormaShell>
  )
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

function buildBuilderWorkoutJsonExport(workoutName: string, groups: BuilderWorkoutGroup[]) {
  return {
    workoutName,
    exercises: groups.flatMap((group) =>
      group.items.map((item) => {
        const loadType = inferBuilderLoadTypeFromItem(item)

        return {
          name: item.name,
          sets: item.strengthPlan?.length ?? parseBuilderSetCount(item.sets),
          weightKg: loadType === 'weighted' ? parseBuilderWeightValue(item.load) : null,
          durationSeconds: parseDurationSeconds(item.sets) ?? null,
          restBetweenSetsSeconds: parseDurationSeconds(item.rest) ?? null,
        }
      }),
    ),
  }
}

function createBuilderWorkoutJsonFileName(workoutName: string) {
  const sanitizedName = workoutName
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '')
    .replace(/\s+/g, '-')

  return `${sanitizedName || 'workout-plan'}.json`
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

  if (details.equipment === 'Bodyweight' || details.equipment === 'Собственный вес' || details.equipment === 'Stretches' || details.equipment === 'Recovery') {
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

type BuilderFatigueStatus = 'ready' | 'light' | 'medium' | 'high' | 'critical'

function buildBuilderFatigueSummary(groups: BuilderWorkoutGroup[]) {
  const totals = new Map<string, number>()

  for (const group of groups) {
    for (const item of group.items) {
      if (item.affectsFatigue === false) {
        continue
      }

      const muscleLabels = item.muscles?.length
        ? item.muscles
        : item.muscleGroup.split(',').map((entry) => entry.trim()).filter(Boolean)

      if (muscleLabels.length === 0) {
        continue
      }

      const setLoad = item.strengthPlan?.length
        ? item.strengthPlan.reduce((total, set) => total + getBuilderSetFatigueFactor(set.setType), 0)
        : parseBuilderSetCount(item.sets)

      muscleLabels.forEach((muscle, index) => {
        const roleFactor = index === 0 ? 1 : index === 1 ? 0.6 : index === 2 ? 0.35 : 0.2
        const score = setLoad * roleFactor * 12
        totals.set(muscle, (totals.get(muscle) ?? 0) + score)
      })
    }
  }

  const muscles = Array.from(totals.entries())
    .map(([name, score]) => ({
      name,
      score: Math.min(100, Math.round(score)),
      status: getBuilderFatigueStatus(score),
    }))
    .sort((left, right) => right.score - left.score)

  return {
    totalScore: muscles.reduce((total, muscle) => total + muscle.score, 0),
    muscles,
    highlightedMuscles: muscles.map((muscle) => muscle.name),
  }
}

function getBuilderSetFatigueFactor(setType: StrengthSetType) {
  if (setType === 'warmup') {
    return 0.6
  }

  if (setType === 'failure') {
    return 1.2
  }

  return 1
}

function getBuilderFatigueStatus(score: number): BuilderFatigueStatus {
  if (score >= 100) {
    return 'critical'
  }

  if (score >= 60) {
    return 'high'
  }

  if (score >= 30) {
    return 'medium'
  }

  if (score >= 10) {
    return 'light'
  }

  return 'ready'
}

function getBuilderFatigueToneClass(status: BuilderFatigueStatus) {
  return {
    ready: 'bg-[#163720] text-[#9ef0a8]',
    light: 'bg-[#2e3316] text-[#dfe890]',
    medium: 'bg-[#3a2b14] text-[#f2cf87]',
    high: 'bg-[#3a2014] text-[#f5b17e]',
    critical: 'bg-[#3a1816] text-[#ffb4a7]',
  }[status]
}

function getBuilderFatigueBarClass(status: BuilderFatigueStatus) {
  return {
    ready: 'bg-[#57c968]',
    light: 'bg-[#b9d94b]',
    medium: 'bg-[#f0bf43]',
    high: 'bg-[#f08b2e]',
    critical: 'bg-[#eb5345]',
  }[status]
}

function getBuilderFatigueWidthClass(score: number) {
  if (score >= 95) {
    return 'w-full'
  }

  if (score >= 85) {
    return 'w-11/12'
  }

  if (score >= 75) {
    return 'w-10/12'
  }

  if (score >= 65) {
    return 'w-8/12'
  }

  if (score >= 50) {
    return 'w-7/12'
  }

  if (score >= 35) {
    return 'w-5/12'
  }

  if (score >= 20) {
    return 'w-4/12'
  }

  if (score >= 10) {
    return 'w-3/12'
  }

  return 'w-2/12'
}

function formatBuilderWeight(weight: number) {
  return `${weight}`.replace(/(\.\d*?)0+$/, '$1').replace(/\.0$/, '')
}

function ExercisePlanMediaCard({ item }: { item: BuilderExerciseItem }) {
  const muscleLabels = item.muscles?.length ? item.muscles : [item.muscleGroup]

  return (
    <div className="h-full rounded-[28px] border border-white/8 bg-[#0d1116]/82 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition hover:border-[#d6b05f]/18">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-display text-2xl font-bold tracking-[-0.035em] text-white">{item.name}</div>
        </div>
      </div>

      <div className="grid gap-3">
        <ExercisePlanVideo videoUrl={item.previewVideoUrl} title={item.name} />
        <div className="flex flex-wrap gap-1.5">
          {muscleLabels.slice(0, 4).map((muscle) => (
            <span key={muscle} className="rounded-full border border-white/8 bg-white/5 px-2 py-1 text-[11px] text-white/55">
              {muscle}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function ExercisePlanRightPanel({ item, onReplace, onDelete }: { item: BuilderExerciseItem; onReplace: () => void; onDelete: () => void }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        type="button"
        onClick={onReplace}
        aria-label={`Заменить упражнение ${item.name}`}
        title="Заменить"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-white/58 transition hover:bg-white/6 hover:text-white"
      >
        <Replace className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Удалить упражнение ${item.name}`}
        title="Удалить"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#ffb1a8]/78 transition hover:bg-[#eb5345]/12 hover:text-[#ffb1a8]"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  )
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

function InlineAddExerciseButton({ onClick }: { onClick: () => void }) {
  return (
    <div className="relative z-10 h-0 min-w-[1040px]">
      <div className="absolute inset-x-0 top-0 flex -translate-y-1/2 justify-center pointer-events-none">
        <button
          type="button"
          onClick={onClick}
          aria-label="Добавить упражнение в эту позицию"
          title="Добавить упражнение"
          className="pointer-events-auto inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/8 bg-[#111419] text-white/26 transition hover:border-[#d6b05f]/24 hover:text-[#d6b05f]/80"
        >
          <Plus className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

function BottomInlineAddExerciseButton({ onClick }: { onClick: () => void }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex translate-y-1/2 justify-center">
      <button
        type="button"
        onClick={onClick}
        aria-label="Добавить упражнение в конец группы"
        title="Добавить упражнение"
        className="pointer-events-auto inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/8 bg-[#111419] text-white/26 transition hover:border-[#d6b05f]/24 hover:text-[#d6b05f]/80"
      >
        <Plus className="h-3 w-3" />
      </button>
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

function ControlBlock({ label, value, suffix, onChange, readOnly = false, onReset, resetLabel = 'Сбросить', onValueCommit, emptyLabel = '', compactEmpty = false }: { label: string; value: number | null; suffix?: string; onChange: (delta: number) => void; readOnly?: boolean; onReset?: () => void; resetLabel?: string; onValueCommit?: (value: number | null) => void; emptyLabel?: string; compactEmpty?: boolean }) {
  const [draft, setDraft] = useState(value === null ? '' : String(value))
  const isEmpty = value === null

  useEffect(() => {
    setDraft(value === null ? '' : String(value))
  }, [value])

  function commitDraft() {
    if (!onValueCommit) {
      setDraft(value === null ? '' : String(value))
      return
    }

    const normalized = draft.trim()
    if (!normalized) {
      onValueCommit(null)
      return
    }

    const parsed = Number(normalized.replace(',', '.'))
    if (!Number.isFinite(parsed)) {
      setDraft(value === null ? '' : String(value))
      return
    }

    onValueCommit(Math.round(parsed))
  }

  return (
    <div className={cn('rounded-[24px] border border-white/8 bg-white/4 p-4 transition-opacity', isEmpty ? 'opacity-75' : undefined)}>
      <div className="flex items-center justify-between gap-3 text-sm text-white/45">
        <span>{label}</span>
        {onReset ? <button type="button" onClick={onReset} className="text-xs text-white/32 transition hover:text-white/64">{resetLabel}</button> : null}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <button type="button" disabled={readOnly} onClick={() => onChange(-1)} className={cn('inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72', readOnly ? 'cursor-default opacity-35' : undefined)}>-</button>
        <div className="min-w-0 flex-1 text-center">
          <input
            type="text"
            inputMode="numeric"
            value={draft}
            onChange={(event) => setDraft(event.target.value.replace(/[^\d.,-]/g, ''))}
            onBlur={commitDraft}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                commitDraft()
              }

              if (event.key === 'Escape') {
                setDraft(value === null ? '' : String(value))
              }
            }}
            placeholder={emptyLabel}
            className={cn(
              'w-full bg-transparent text-center font-display font-bold text-white outline-none placeholder:text-white/30',
              compactEmpty ? 'text-[1.55rem]' : 'text-3xl',
            )}
          />
          {suffix ? <div className="text-xs text-white/35">{suffix}</div> : null}
        </div>
        <button type="button" disabled={readOnly} onClick={() => onChange(1)} className={cn('inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72', readOnly ? 'cursor-default opacity-35' : undefined)}>+</button>
      </div>
    </div>
  )
}