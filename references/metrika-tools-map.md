# Коннектор Яндекс.Метрики: тулы, рецепты, правила

Метрика — **опциональный усилитель** аудита. Деньги и CPA всегда берём из Директа; Метрика даёт то, чего в Директе нет: список целей с достижениями, связку счётчика с кабинетом, время на сайте, посадочные, потерю кликов, динамику.

---

## Как найти коннектор

Имя коннектора задаёт пользователь (`metrikaCM`, `MetrikaDevadent`, `MetrikaXenia`…), поэтому **ищи тулы по суффиксу** `yandex_metrika_counters_get`, а не по префиксу. В сессии бывает несколько коннекторов Метрики — это разные аккаунты Яндекса. Если маркетолог назвал, где лежит счётчик, — бери тот коннектор и запиши префикс в `_state.json` → `metrika_prefix`.

Нет ни одного тула → `metrika_ok: false`, аудит идёт по Директу, непроверенное уходит в `limitations`.

## Разрешённые (read-only) тулы

| Тул | Зачем | Шаг |
|---|---|---|
| `yandex_metrika_accounts_get` | аккаунты Яндекса за коннектором | 0 |
| `yandex_metrika_counters_get` | найти счётчик по номеру/домену (`search`) | 0 |
| `yandex_metrika_counter_get` | детали одного счётчика | 0 |
| `yandex_metrika_goals_get` | цели + достижения за N дней (`stats_days`) | 0, 1 |
| `yandex_metrika_direct_clients_get` | какие кабинеты Директа видит счётчик | 0 |
| `yandex_metrika_report` | таблица метрик по группировкам | 2, 5, 6б |
| `yandex_metrika_report_bytime` | динамика по дням/неделям | ведение |
| `yandex_metrika_segments_get` | сегменты счётчика | по необходимости |

**Пишущие** (`goals_add/update/delete`, `segments_add/delete`) — в аудите никогда. В ведении — только `goals_add` / `segments_add`, через гейт и сначала с `dry_run: true`; `goals_update` / `goals_delete` не вызываются никогда (на цели завязаны стратегии).

---

## Рецепты

### M1. Счётчик и цели

```
yandex_metrika_counters_get({ search: "<номер из CounterIds или домен>", limit: 10 })
yandex_metrika_goals_get({ counter_id, stats_days: 30 })
```

- `reaches > 0` — цель живая.
- Счётчика из `CounterIds` нет в выдаче → он в другом аккаунте Яндекса. Попробуй другой коннектор Метрики, если он есть; нет — в `limitations`, это не находка по рекламе.
- **Подбор `goal_ids`:** сначала цели из `PriorityGoals` стратегий кампаний (на них учится автостратегия), потом живые пользовательские цели заявки/звонка/мессенджера. Автоцели («Автоцель: отправка формы», «…контактные данные») часто дублируют пользовательскую цель на форму — в один набор их не складывай, конверсии задвоятся.
- Десятки целей с нулём достижений — не находка high сама по себе (старые лендинги), а строка «почистить цели» в low. High — если на мёртвую цель учится стратегия активной кампании.

Сохрани ответ в `00_metrika_goals.json`.

### M2. Связка счётчика с кабинетом

```
yandex_metrika_direct_clients_get({ counter_id })
```

- Логин кабинета среди `chief_login` → связка в порядке.
- Список пуст / логина нет → **medium «проверить связку»**. Пустой список бывает и тогда, когда у аккаунта Метрики, через который подключён коннектор, просто нет доступа к кабинету Директа. Повышай до high, только если конверсии в отчётах Директа пустые при ненулевых кликах.

### M3. Потеря кликов и время на сайте по кампаниям

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  dimensions: ["ym:s:lastDirectClickOrder"],
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:pageDepth",
            "ym:s:avgVisitDurationSeconds","ym:s:goal<ID>reaches"],
  filters: "ym:s:lastTrafficSource=='ad'", limit: 100 })
```

Даты — **те же**, что у отчёта Директа на Шаге 2. Доля дошедших = визиты ÷ клики Директа: не меньше 80% — норма; 60–80% — medium; меньше 60% при 100+ кликах — high.

### M4. Посадочные страницы

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  dimensions: ["ym:s:startURL"],
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:pageDepth",
            "ym:s:avgVisitDurationSeconds","ym:s:anyGoalConversionRate"],
  filters: "ym:s:lastTrafficSource=='ad'", limit: 50, sort: ["-ym:s:visits"] })
```

Для разреза «кампания → посадочная» добавь `ym:s:lastDirectClickOrder` в `dimensions` и подними `limit` до 200. Страница меньше ~50 визитов — «мало данных».

### M5. Устройства (для форка Шага 5)

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  dimensions: ["ym:s:deviceCategory"],
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:avgVisitDurationSeconds","ym:s:goal<ID>reaches"],
  filters: "ym:s:lastTrafficSource=='ad'", limit: 10 })
```

### M6. Динамика (ведение, Фаза A)

```
yandex_metrika_report_bytime({ counter_id, date1: "56daysAgo", date2: "yesterday", group: "week",
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:goal<ID>reaches"],
  filters: "ym:s:lastTrafficSource=='ad'", top_keys: 10 })
```

### M7. Источники трафика (история каналов, `channel-history.md`)

Визиты и достижения целей по рекламным системам и UTM-меткам — показывает не-Директ каналы (VK, Telegram, посевы), если ссылки размечены. Расходов в ответе нет: их даёт маркетолог.

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  dimensions: ["ym:s:lastTrafficSource","ym:s:lastAdvEngine"],
  metrics: ["ym:s:visits","ym:s:goal<ID>reaches"], limit: 50, sort: ["-ym:s:visits"] })
# разметка UTM — тот же отчёт с dimensions: ["ym:s:lastUTMSource","ym:s:lastUTMMedium"]
```

Поле не принято API → см. «Правила и фолбеки» ниже, отметь в `limitations`.

---

## Атрибуция Директ ↔ Метрика

С 25.06.2026 Метрика считает старые модели по аналогам и сама переводит устаревшие имена (`lastsign…`, `first…`) в группировках и фильтрах. Поэтому в `dimensions`/`filters` пиши шаблон `ym:s:<модель>…` той же моделью, что в `attribution`.

| Директ | Метрика (`attribution`) |
|---|---|
| `FC` / `FCCD` | `cross_device_first` |
| `LC` / `LCCD` | `last` |
| `LSC` / `LSCCD` | `cross_device_last_significant` (по умолчанию) |
| `AUTO` | `automatic` |

Конверсии Метрики и Директа **не сводим в ноль**: Метрика считает к дате визита, Директ — к дате клика.

## Правила и фолбеки

- `sampled: true` на малом объёме → повтори с `accuracy: "full"` или помечай вывод «приблизительно».
- Ошибка по полю/группировке → убери его и повтори один раз; второй сбой — в `limitations`.
- Отчёты Метрики компактные, но всё равно ставь `limit` — ответ идёт через контекст.
