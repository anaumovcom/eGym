import type { RuntimeCalibrationState, RuntimeFlowSource, RuntimePhotoMode } from '@/entities/runtime/model/types'

export function parseRuntimeSource(value: string | null): RuntimeFlowSource {
  if (value === 'catalog' || value === 'quick-start' || value === 'today' || value === 'calendar' || value === 'programs' || value === 'builder') {
    return value
  }

  return 'today'
}

export function parseRuntimePhotoMode(value: string | null): RuntimePhotoMode | null {
  if (value === 'before') {
    return 'pre-workout'
  }

  if (value === 'after') {
    return 'post-workout'
  }

  if (value === 'manual') {
    return 'manual'
  }

  return null
}

export function parseCalibrationState(value: string | null): RuntimeCalibrationState | undefined {
  if (value === 'saved' || value === 'missing' || value === 'not-needed') {
    return value
  }

  return undefined
}

export function getRuntimeInitOptions(searchParams: URLSearchParams) {
  return {
    source: parseRuntimeSource(searchParams.get('source')),
    slug: searchParams.get('slug') ?? undefined,
    programId: searchParams.get('programId') ?? undefined,
    runId: searchParams.get('runId') ?? undefined,
    photoMode: parseRuntimePhotoMode(searchParams.get('photo')),
    calibrationState: parseCalibrationState(searchParams.get('calibration')),
  }
}

export function withSearch(path: string, search: string) {
  return search ? `${path}${search}` : path
}