# Этап 5 — Backend foundation и API-контракты

## Цель

Создать production-ready основу Python-бэкенда и зафиксировать API-контракты, необходимые уже реализованному frontend на моках.

После этапа frontend должен уметь переключаться с MSW на реальный dev-backend для базовых сущностей без изменения UX.

---

## Основные источники из документации

* `docs/common/ui-and-navigation.md`
* `docs/common/ui-components.md`
* `docs/common/modals-panels-overlays.md`
* `docs/common/terminology.md`
* экранные документы с разделами данных.

---

## Backend setup

1. Создать backend-приложение на Python 3.12+.
2. Подключить FastAPI.
3. Подключить Pydantic v2.
4. Подключить SQLAlchemy 2.x.
5. Подключить Alembic.
6. Подключить PostgreSQL.
7. Подключить Redis.
8. Подключить pytest, Ruff, mypy/pyright.
9. Настроить OpenAPI-генерацию.
10. Настроить окружения: local, test, staging-like.

---

## Рекомендуемая структура backend

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    repositories/
    workers/
    realtime/
    hardware/
    tests/
```

---

## Базовые домены этапа

Реализовать каркас:

* пользователи;
* профили;
* настройки пользователя;
* статусы тренажёра;
* статусы приводов;
* статусы безопасности;
* системные уведомления;
* роли доступа;
* audit log опасных действий.

---

## API-контракты

Зафиксировать контракты для frontend:

* текущий пользователь;
* список пользователей;
* выбор пользователя;
* dashboard summary;
* machine status;
* drive statuses;
* safety status;
* notifications;
* общие справочники;
* health check;
* OpenAPI schema export.

Контракты должны совпадать с формой данных, которую уже использует MSW.

---

## База данных

Создать первые миграции:

* users;
* user_profiles;
* user_goals;
* body_measurements;
* app_settings;
* machine_status_snapshots;
* drive_status_snapshots;
* safety_events;
* audit_log.

---

## Инфраструктура качества

Настроить:

* unit-тесты;
* integration-тесты API;
* миграционные тесты;
* lint;
* type-check;
* форматирование;
* test database;
* сиды для dev-данных.

---

## Acceptance criteria

* Backend запускается локально.
* OpenAPI доступен и валиден.
* Frontend может получить пользователей, статусы и dashboard summary из реального backend.
* Моки frontend и реальные DTO не расходятся.
* Есть миграции и seed-данные.
* Есть базовый audit log для опасных действий.
* Все проверки backend проходят автоматически.
