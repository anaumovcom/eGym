import { buildFatigueData, buildProgressData, buildSystemSettingsData, getProfileSeed } from '@/mocks/stage4-data'

describe('stage4 mock data builders', () => {
  it('returns progress empty state when history is disabled', () => {
    const data = buildProgressData({
      user: getProfileSeed('guest'),
      period: '30d',
      blacklistedSlugs: [],
      dev: {
        machineReady: true,
        leftDriveError: false,
        rightDriveError: false,
        emergencyStop: false,
        safetyDisabled: false,
        noCalibration: false,
        highFatigue: false,
        criticalFatigue: false,
        noHistory: true,
        noPhotos: true,
        offlineHours: 0,
      },
    })

    expect(data.emptyState?.title).toContain('Недостаточно данных')
    expect(data.photoEntries).toHaveLength(0)
  })

  it('marks muscles critical when critical fatigue scenario is enabled', () => {
    const data = buildFatigueData({
      dev: {
        machineReady: true,
        leftDriveError: false,
        rightDriveError: false,
        emergencyStop: false,
        safetyDisabled: false,
        noCalibration: false,
        highFatigue: false,
        criticalFatigue: true,
        noHistory: false,
        noPhotos: false,
        offlineHours: 0,
      },
    })

    expect(data.muscles.some((item) => item.status === 'critical')).toBe(true)
  })

  it('increases missing calibrations in no-calibration scenario', () => {
    const data = buildSystemSettingsData({
      machineReady: true,
      leftDriveError: false,
      rightDriveError: false,
      emergencyStop: false,
      safetyDisabled: false,
      noCalibration: true,
      highFatigue: false,
      criticalFatigue: false,
      noHistory: false,
      noPhotos: false,
      offlineHours: 0,
    })

    expect(data.calibrations.missingCount).toBe('1')
  })
})