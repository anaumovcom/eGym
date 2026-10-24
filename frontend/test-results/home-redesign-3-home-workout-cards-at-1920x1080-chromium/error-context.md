# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: home-redesign.spec.ts >> 3 home workout cards at 1920x1080
- Location: e2e\home-redesign.spec.ts:7:5

# Error details

```
Error: expect(locator).toHaveCount(expected) failed

Locator:  getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link')
Expected: 7
Received: 6
Timeout:  5000ms

Call log:
  - Expect "toHaveCount" with timeout 5000ms
  - waiting for getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link')
    14 × locator resolved to 6 elements
       - unexpected value "6"

```

```
Error: No unmocked API calls, writes or WebSocket commands

expect(received).toEqual(expected) // deep equality

- Expected  - 1
+ Received  + 8

- Array []
+ Array [
+   "GET /api/scales/status",
+   "PUT /api/scales/activity",
+   "PUT /api/scales/activity",
+   "PUT /api/scales/activity",
+   "PUT /api/scales/activity",
+   "GET /api/scales/status",
+ ]
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e6]: F
    - navigation "Основная навигация" [ref=e7]:
      - link "Главная" [ref=e8] [cursor=pointer]:
        - /url: /dashboard
        - img [ref=e9]
        - generic [ref=e12]: Главная
      - link "Мои тренировки" [ref=e13] [cursor=pointer]:
        - /url: /builder
        - img [ref=e14]
        - generic [ref=e17]: Мои тренировки
      - link "Каталог" [ref=e18] [cursor=pointer]:
        - /url: /catalog
        - img [ref=e19]
        - generic [ref=e25]: Каталог
      - link "Календарь" [ref=e26] [cursor=pointer]:
        - /url: /calendar
        - img [ref=e27]
        - generic [ref=e29]: Календарь
      - link "Прогресс" [ref=e30] [cursor=pointer]:
        - /url: /progress
        - img [ref=e31]
        - generic [ref=e34]: Прогресс
      - link "Усталость мышц" [ref=e35] [cursor=pointer]:
        - /url: /fatigue
        - img [ref=e36]
        - generic [ref=e38]: Усталость мышц
    - generic [ref=e39]:
      - 'button "Меню профиля: Алексей" [ref=e40] [cursor=pointer]':
        - generic [ref=e41]: А
      - group "Состояние тренажёра и безопасность" [ref=e42]:
        - 'button "AI-тренер: локальная диагностика" [ref=e43] [cursor=pointer]':
          - generic [ref=e44]: AI · Выкл
        - generic "Усилие на двигателях" [ref=e45]:
          - generic [ref=e46]: Моторы
          - generic [ref=e47]: — %
          - generic [ref=e48]: — кг
        - 'button "Состояние тренажёра: Тренажёр готов" [ref=e50] [cursor=pointer]':
          - img [ref=e51]
          - status [ref=e54]: Тренажёр готов
        - button "Аварийная остановка" [ref=e55] [cursor=pointer]:
          - img [ref=e56]
          - generic [ref=e58]: Аварийная остановка
  - main [ref=e59]:
    - region "Какую тренировку выберете?" [ref=e60]:
      - generic [ref=e61]:
        - generic [ref=e62]:
          - heading "Какую тренировку выберете?" [level=1] [ref=e63]
          - paragraph [ref=e64]: Нажмите на карточку, чтобы посмотреть упражнения и начать. Перетащите, чтобы изменить порядок
        - button "Новая тренировка" [ref=e66] [cursor=pointer]:
          - img [ref=e67]
          - text: Новая тренировка
      - generic [ref=e68]:
        - generic [ref=e69]:
          - button "Выбрать тренировку «Спина и бицепс»" [ref=e70] [cursor=pointer]:
            - generic [ref=e71]: Последний раз 13 сентября
            - generic [ref=e72]: Спина и бицепс
            - generic [ref=e73]:
              - generic [ref=e74]:
                - generic [ref=e75]: "1"
                - generic [ref=e76]: Упражнение 1
              - generic [ref=e77]:
                - generic [ref=e78]: "2"
                - generic [ref=e79]: Упражнение 2
              - generic [ref=e80]:
                - generic [ref=e81]: "3"
                - generic [ref=e82]: Упражнение 3
              - generic [ref=e83]:
                - generic [ref=e84]: "4"
                - generic [ref=e85]: Упражнение 4
              - generic [ref=e86]:
                - generic [ref=e87]: "5"
                - generic [ref=e88]: Упражнение 5
              - generic [ref=e89]:
                - generic [ref=e90]: "6"
                - generic [ref=e91]: Упражнение 6
              - generic [ref=e92]:
                - generic [ref=e93]: "7"
                - generic [ref=e94]: Упражнение 7
            - generic [ref=e95]:
              - generic [ref=e96]:
                - generic [ref=e97]:
                  - img [ref=e98]
                  - text: 7 упражнений
                - generic [ref=e101]:
                  - img [ref=e102]
                  - text: ≈ 45 мин
              - generic [ref=e105]:
                - text: Начать
                - img [ref=e106]
          - button "Выбрать тренировку «Грудь и плечи»" [ref=e108] [cursor=pointer]:
            - generic [ref=e109]: Последний раз 13 сентября
            - generic [ref=e110]: Грудь и плечи
            - generic [ref=e111]:
              - generic [ref=e112]:
                - generic [ref=e113]: "1"
                - generic [ref=e114]: Упражнение 1
              - generic [ref=e115]:
                - generic [ref=e116]: "2"
                - generic [ref=e117]: Упражнение 2
              - generic [ref=e118]:
                - generic [ref=e119]: "3"
                - generic [ref=e120]: Упражнение 3
              - generic [ref=e121]:
                - generic [ref=e122]: "4"
                - generic [ref=e123]: Упражнение 4
              - generic [ref=e124]:
                - generic [ref=e125]: "5"
                - generic [ref=e126]: Упражнение 5
              - generic [ref=e127]:
                - generic [ref=e128]: "6"
                - generic [ref=e129]: Упражнение 6
              - generic [ref=e130]:
                - generic [ref=e131]: "7"
                - generic [ref=e132]: Упражнение 7
            - generic [ref=e133]:
              - generic [ref=e134]:
                - generic [ref=e135]:
                  - img [ref=e136]
                  - text: 7 упражнений
                - generic [ref=e139]:
                  - img [ref=e140]
                  - text: ≈ 45 мин
              - generic [ref=e143]:
                - text: Начать
                - img [ref=e144]
          - button "Выбрать тренировку «Ноги»" [ref=e146] [cursor=pointer]:
            - generic [ref=e147]: Последний раз 13 сентября
            - generic [ref=e148]: Ноги
            - generic [ref=e149]:
              - generic [ref=e150]:
                - generic [ref=e151]: "1"
                - generic [ref=e152]: Упражнение 1
              - generic [ref=e153]:
                - generic [ref=e154]: "2"
                - generic [ref=e155]: Упражнение 2
              - generic [ref=e156]:
                - generic [ref=e157]: "3"
                - generic [ref=e158]: Упражнение 3
              - generic [ref=e159]:
                - generic [ref=e160]: "4"
                - generic [ref=e161]: Упражнение 4
              - generic [ref=e162]:
                - generic [ref=e163]: "5"
                - generic [ref=e164]: Упражнение 5
              - generic [ref=e165]:
                - generic [ref=e166]: "6"
                - generic [ref=e167]: Упражнение 6
              - generic [ref=e168]:
                - generic [ref=e169]: "7"
                - generic [ref=e170]: Упражнение 7
            - generic [ref=e171]:
              - generic [ref=e172]:
                - generic [ref=e173]:
                  - img [ref=e174]
                  - text: 7 упражнений
                - generic [ref=e177]:
                  - img [ref=e178]
                  - text: ≈ 45 мин
              - generic [ref=e181]:
                - text: Начать
                - img [ref=e182]
        - status [ref=e184]
        - region "Восстановление мышц" [ref=e185]:
          - generic [ref=e186]:
            - heading "Усталость мышц" [level=2] [ref=e187]
            - paragraph [ref=e188]: Нажмите на мышцу
          - generic [ref=e189]:
            - generic [ref=e192]:
              - img [ref=e193]:
                - 'button "Икры: Нет данных" [ref=e194] [cursor=pointer]'
                - 'button "Квадрицепсы: Нет данных" [ref=e197] [cursor=pointer]'
                - 'button "Пресс: Нет данных" [ref=e200] [cursor=pointer]'
                - 'button "Косые мышцы живота: Нет данных" [ref=e202] [cursor=pointer]'
                - 'button "Предплечья: Нет данных" [ref=e210] [cursor=pointer]'
                - 'button "Бицепс: Нет данных" [ref=e213] [cursor=pointer]'
                - 'button "Передние дельты: Нет данных" [ref=e216] [cursor=pointer]'
                - 'button "Грудь: Перегрузка, 150 балл." [ref=e219] [cursor=pointer]'
                - 'button "Трапеции: Нет данных" [ref=e222] [cursor=pointer]'
              - img
            - generic [ref=e227]:
              - img [ref=e228]:
                - 'button "Трапеции: Нет данных" [ref=e229] [cursor=pointer]'
                - 'button "Икры: Нет данных" [ref=e231] [cursor=pointer]'
                - 'button "Бицепс бедра: Нет данных" [ref=e234] [cursor=pointer]'
                - 'button "Ягодицы: Нет данных" [ref=e237] [cursor=pointer]'
                - 'button "Предплечья: Нет данных" [ref=e245] [cursor=pointer]'
                - 'button "Трицепс: Нет данных" [ref=e248] [cursor=pointer]'
                - 'button "Широчайшие: Нет данных" [ref=e251] [cursor=pointer]'
                - 'button "Низ спины: Нет данных" [ref=e254] [cursor=pointer]'
                - 'button "Средняя трапеция: Нет данных" [ref=e256] [cursor=pointer]'
                - 'button "Задние дельты: Нет данных" [ref=e258] [cursor=pointer]'
              - img
          - 'generic "Цветовая шкала: от готовности к перегрузке; серый — нет данных" [ref=e261]':
            - paragraph [ref=e263]:
              - generic [ref=e264]: Готовность
              - generic [ref=e265]: Перегрузка
```

# Test source

```ts
  23  |   const excludedExercise = getExerciseDetails('smith-machine-bench-press')
  24  |   const builder = structuredClone(getWorkoutBuilderData())
  25  |   builder.selectedProgramId = 'e2e-saved-workout'
  26  |   builder.info.name = 'Сохранённая тренировка e2e'
  27  |   builder.programs = [{ ...builder.programs[0], id: builder.selectedProgramId, name: builder.info.name }]
  28  |   const settings = buildSystemSettingsData(defaultStage4DevFlags)
  29  |   const snapshot: HardwareSnapshot = {
  30  |     eventType: 'snapshot', emittedAt: '2026-09-15T10:00:00Z', machine: machineScenarios.ready,
  31  |     safety: { state: 'enabled', label: 'Безопасность включена', message: '', requiresService: false, activeEventId: null },
  32  |     emulatorMode: true, serviceMode: false, selectedUserId: 'alexey', userSelected: true,
  33  |     drives: [],
  34  |     motion: {
  35  |       moving: false, motionProfile: 'idle', barPositionMm: 0, leftPositionMm: 0, rightPositionMm: 0,
  36  |       syncDeltaMm: 0, amplitudePercent: 0, tempoLabel: 'Покой', repetitionCount: 0,
  37  |       currentSet: 0, targetSet: 0, targetReps: 0, direction: 'stopped',
  38  |     },
  39  |     calibrationRequired: true, calibrationActual: false, activeCalibrationId: null,
  40  |     commandQueueDepth: 0, lastCommand: null, diagnosticsStatus: 'idle', lastDiagnosticsAt: null, alerts: [],
  41  |   }
  42  | 
  43  |   await page.exposeFunction('__navigationCameraRequested', () => { cameraRequests.push('getUserMedia') })
  44  |   await page.addInitScript(() => {
  45  |     if (!localStorage.getItem('egym-app-store')) {
  46  |       localStorage.setItem('egym-app-store', JSON.stringify({ state: { selectedProgramId: 'e2e-saved-workout' }, version: 0 }))
  47  |     }
  48  |     const mediaDevices = navigator.mediaDevices ?? {}
  49  |     Object.defineProperty(mediaDevices, 'getUserMedia', {
  50  |       configurable: true,
  51  |       value: async () => {
  52  |         await (window as unknown as { __navigationCameraRequested: () => Promise<void> }).__navigationCameraRequested()
  53  |         throw new DOMException('Camera is blocked in navigation tests', 'NotAllowedError')
  54  |       },
  55  |     })
  56  |     if (!navigator.mediaDevices) Object.defineProperty(navigator, 'mediaDevices', { value: mediaDevices })
  57  |   })
  58  | 
  59  |   // Do not connect to a real device, even for the global realtime provider.
  60  |   await page.context().routeWebSocket((url) => url.pathname.startsWith('/api/'), (socket) => {
  61  |     socket.onMessage(() => { violations.push(`Unexpected WebSocket message: ${socket.url()}`) })
  62  |   })
  63  |   await page.context().route((url) => url.pathname.startsWith('/api/'), async (route) => {
  64  |     const request = route.request()
  65  |     const { pathname: path, search, searchParams } = new URL(request.url())
  66  |     const method = request.method()
  67  |     requests.push({ method, path, search })
  68  | 
  69  |     // Both selection-screen and persisted-selection sync are fulfilled locally.
  70  |     if (method === 'POST' && path === '/api/users/select') {
  71  |       await route.fulfill({ json: { currentUser: { id: request.postDataJSON().userId } } })
  72  |       return
  73  |     }
  74  |     if (method !== 'GET') {
  75  |       violations.push(`${method} ${path}`)
  76  |       await route.fulfill({ status: 405, json: { detail: 'Read-only e2e: mutation blocked' } })
  77  |       return
  78  |     }
  79  | 
  80  |     const responses: Record<string, unknown> = {
  81  |       '/api/users': { users: mockUsers },
  82  |       '/api/users/current': {
  83  |         id: 'alexey', name: 'Алексей', role: 'user', readinessPercent: 78, accent: 'gold',
  84  |         profile: { birthDate: null, heightCm: 183, weightKg: 92.4, photoUrl: null, notes: '' }, goals: [],
  85  |       },
  86  |       '/api/machine/status': machineScenarios.ready,
  87  |       '/api/hardware/status': snapshot,
  88  |       '/api/hardware/settings': settings,
  89  |       '/api/hardware/calibrations/current': null,
  90  |       '/api/dashboard': buildDashboardScenario(),
  91  |       '/api/builder': builder,
  92  |       '/api/calendar': getWorkoutCalendarData(searchParams.get('month') ?? undefined),
  93  |       '/api/exercises': { items: [exercise, excludedExercise], total: 2, availableFilters: { muscles: [...new Set([...exercise.muscles, ...excludedExercise.muscles])], equipment: [...new Set([exercise.equipment, excludedExercise.equipment])], difficulty: ['Beginner', 'Intermediate', 'Advanced'], force: ['Push', 'Pull', 'Static', 'Stretch'], mechanic: ['Compound', 'Isolation', 'Mobility'], grips: [...new Set([exercise.grips, excludedExercise.grips])] } },
  94  |       '/api/exercises/machine-pulldown': exercise,
  95  |       '/api/exercises/smith-machine-bench-press': excludedExercise,
  96  |       '/api/strength-modes': FALLBACK_STRENGTH_MODES,
  97  |       '/api/progress': buildProgressData({ user: getProfileSeed('alexey'), period: '30d', blacklistedSlugs: [], dev: defaultStage4DevFlags }),
  98  |       '/api/fatigue': buildFatigueData({ dev: defaultStage4DevFlags }),
  99  |       '/api/body-measurements': { measurements: [] },
  100 |       '/api/photo-progress': { photos: [] },
  101 |       '/api/achievements': { achievements: [] },
  102 |       // The Modbus page is read-only here: no port list, no connection, simulation flag off.
  103 |       '/api/modbus/ports': [],
  104 |       '/api/modbus/status': { connected: false, port: null, baud_rate: null, parity: null, slave_id: null, last_success_at: null, ok_count: 0, error_count: 0, error_message: null, simulation_mode: false },
  105 |     }
  106 |     if (Object.hasOwn(responses, path)) {
  107 |       await route.fulfill({ json: responses[path] })
  108 |       return
  109 |     }
  110 |     violations.push(`${method} ${path}`)
  111 |     await route.fulfill({ status: 404, json: { detail: 'Read-only e2e: missing fixture' } })
  112 |   })
  113 |   return { builder, exercise, settings, snapshot, requests, violations, cameraRequests }
  114 | }
  115 | 
  116 | export const test = base.extend<{ navigationApi: Awaited<ReturnType<typeof installNavigationApi>> }>({
  117 |   // Override the URL only for an already-running frontend; no backend is needed.
  118 |   baseURL: async ({ baseURL }, use) => { await use(process.env.EGYM_E2E_BASE_URL ?? baseURL ?? 'http://127.0.0.1:4174') },
  119 |   serviceWorkers: 'block',
  120 |   navigationApi: [async ({ page }, use) => {
  121 |     const api = await installNavigationApi(page)
  122 |     await use(api)
> 123 |     expect(api.violations, 'No unmocked API calls, writes or WebSocket commands').toEqual([])
      |                                                                                   ^ Error: No unmocked API calls, writes or WebSocket commands
  124 |     expect(api.cameraRequests, 'Navigation must not request the camera').toEqual([])
  125 |   }, { auto: true }],
  126 | })
  127 | 
  128 | export async function expectPrimaryNavigation(page: Page) {
  129 |   const navigation = page.getByRole('navigation', { name: 'Основная навигация', exact: true })
  130 |   await expect(navigation.getByRole('link')).toHaveCount(primaryNavigation.length)
  131 |   for (const [name, href] of primaryNavigation) {
  132 |     const link = navigation.getByRole('link', { name, exact: true })
  133 |     await expect(link).toBeVisible()
  134 |     await expect(link).toHaveAttribute('href', href)
  135 |   }
  136 | }
  137 | 
  138 | export async function openAppAsAlexey(page: Page) {
  139 |   await page.goto('/', { waitUntil: 'domcontentloaded' })
  140 |   await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  141 |   await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  142 |   await expect(page).toHaveURL(/\/dashboard$/)
  143 |   await expectPrimaryNavigation(page)
  144 | }
  145 | 
  146 | export async function openCatalogExerciseSetup(page: Page) {
  147 |   await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Каталог', exact: true }).click()
  148 |   await expect(page.getByRole('heading', { name: 'Каталог упражнений' })).toBeVisible()
  149 |   // Pick a weighted machine exercise: bodyweight exercises skip setup automatically.
  150 |   await page.getByPlaceholder('Найти упражнение...').fill('machine-pulldown')
  151 |   const card = page.getByRole('article', { name: 'Тяга верхнего блока в тренажёре' })
  152 |   await card.getByRole('button', { name: /^Открыть/ }).click()
  153 |   await page.getByRole('dialog').getByRole('button', { name: 'Начать упражнение', exact: true }).click()
  154 |   await expect(page).toHaveURL(/\/exercise-setup\?source=catalog&slug=machine-pulldown$/)
  155 |   await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
  156 | }
  157 | 
  158 | export async function savedBrowserState(page: Page) {
  159 |   return page.evaluate(() => ({ ...localStorage }))
  160 | }
```