# Коннектор Яндекс.Метрики: тулы, рецепты, правила

Метрика — **опциональный усилитель** аудита. Деньги и CPA всегда берём из Директа; Метрика даёт то, чего в Директе нет: список целей с достижениями, связку счётчика с кабинетом, время на сайте, посадочные, потерю кликов, динамику.

---

## Как найти коннектор

Имя коннектора задаёт пользователь (`metrikaCM`, `MetrikaDevadent`, `MetrikaXenia`…), поэтому **ищи тулы по суффиксу** `yandex_metrika_counters_get`, а не по префиксу. В сессии бывает несколько коннекторов Метрики — это разные аккаунты Яндекса. Если маркетолог назвал, где лежит счётчик, — бери тот коннектор и запиши префикс в `_state.json` → `metrika_prefix`.

Нет ни одного тула → `metrika_ok: false`, аудит идёт по Директу, непроверенное уходит в `limitations`.

## Две модели — два вопроса

Визиты в Метрике зависят от модели атрибуции, и разница большая. Живой счётчик, 30 дней, тот же фильтр
рекламного трафика (16.11.2026): **87 922** визита по последнему переходу против **126 909** по последнему
значимому — в 1,44 раза больше. Последний значимый переход записывает на кампанию и возвраты по закладкам
и внутренним переходам, хотя кликами они не были. Ни одно число не «неверное» — они отвечают на разные вопросы.

| Вопрос | Модель (`attribution`) | Рецепты | Подпись в отчёте |
|---|---|---|---|
| Сколько кликов стали визитами (потеря кликов) | `last` | M3 | «визиты по клику (последний переход)» |
| Поведение, посадочные, устройства, источники, динамика — то, что маркетолог сверит с кабинетом Метрики | `cross_device_last_significant` | M3б, M4–M7 | «визиты по последнему значимому переходу, все устройства — как в Метрике по умолчанию» |

**Правила:**

- **`attribution` в каждом вызове `report` и `report_bytime` — явно**, по таблице. Группировки и фильтры пиши
  **без модели в имени** (`ym:s:TrafficSource`, `ym:s:DirectClickOrder`): сервер сам подставит модель из
  `attribution`, и имя не разойдётся с параметром.
- **Модель в отчёте подписывай по полю `attribution` ответа**, а не по тому, что собирался запросить. Пришла
  не та модель — это сбой рецепта: в `limitations`, число не используй.
- **Не дели показатели из разных моделей.** Визиты по клику (M3) — только для доли дошедших (визиты ÷ клики
  Директа). Знаменатель конверсий и CR — клики Директа, конверсии и деньги — из отчёта Директа по модели
  кампании (`references/attribution.md`). Визиты Метрики знаменателем конверсий Директа не бывают.
- Сравниваешь с числами маркетолога из интерфейса Метрики — бери модель `cross_device_last_significant`
  и назови её рядом с числом.

---

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

### M3. Потеря кликов по кампаниям — модель `last`

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  dimensions: ["ym:s:DirectClickOrder"],
  metrics: ["ym:s:visits"],
  filters: "ym:s:TrafficSource=='ad'", limit: 1000 })
```

Даты — **те же**, что у отчёта Директа на Шаге 2. Доля дошедших = визиты по клику ÷ клики Директа: не меньше 80% — норма; 60–80% — medium; меньше 60% при 100+ кликах — high. В отчёте эти визиты подписаны «визиты по клику», в другие расчёты не идут.

### M3б. Поведение по кампаниям — модель `cross_device_last_significant`

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "cross_device_last_significant",
  dimensions: ["ym:s:DirectClickOrder"],
  metrics: ["ym:s:visits","ym:s:users","ym:s:bounceRate","ym:s:pageDepth",
            "ym:s:avgVisitDurationSeconds","ym:s:goal<ID>reaches"],
  filters: "ym:s:TrafficSource=='ad'", limit: 1000 })
```

Отказы, глубина, время на сайте — как маркетолог увидит их в Метрике. Визитов на человека (`visits ÷ users`) заметно больше 1,5 — кампания собирает возвраты своих же пользователей; это наблюдение, а не потеря денег.

### M4. Посадочные страницы

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "cross_device_last_significant",
  dimensions: ["ym:s:startURL"],
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:pageDepth",
            "ym:s:avgVisitDurationSeconds","ym:s:anyGoalConversionRate"],
  filters: "ym:s:TrafficSource=='ad'", limit: 50, sort: ["-ym:s:visits"] })
```

Для разреза «кампания → посадочная» добавь `ym:s:DirectClickOrder` в `dimensions` и подними `limit` до 200. Страница меньше ~50 визитов — «мало данных».

### M5. Устройства (для форка Шага 5)

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "cross_device_last_significant",
  dimensions: ["ym:s:deviceCategory"],
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:avgVisitDurationSeconds","ym:s:goal<ID>reaches"],
  filters: "ym:s:TrafficSource=='ad'", limit: 10 })
```

### M6. Динамика (ведение, Фаза A)

```
yandex_metrika_report_bytime({ counter_id, date1: "56daysAgo", date2: "yesterday", group: "week",
  attribution: "cross_device_last_significant",
  metrics: ["ym:s:visits","ym:s:bounceRate","ym:s:goal<ID>reaches"],
  filters: "ym:s:TrafficSource=='ad'", top_keys: 10 })
```

### M7. Источники трафика (история каналов, `channel-history.md`)

Визиты и достижения целей по рекламным системам и UTM-меткам — показывает не-Директ каналы (VK, Telegram, посевы), если ссылки размечены. Расходов в ответе нет: их даёт маркетолог.

```
yandex_metrika_report({ counter_id, date1, date2, attribution: "cross_device_last_significant",
  dimensions: ["ym:s:TrafficSource","ym:s:SourceEngine"],
  metrics: ["ym:s:visits","ym:s:goal<ID>reaches"], limit: 50, sort: ["-ym:s:visits"] })
# разметка UTM — тот же отчёт с dimensions: ["ym:s:UTMSource","ym:s:UTMMedium"]
```

### M8. Клики и расход Директа в Метрике (`ym:ad:*`) — только если отчёт Директа недоступен

Деньги и клики по умолчанию берём из Директа. Метрика отдаёт их отдельным пространством имён `ym:ad:*`:

```
yandex_metrika_direct_clients_get({ counter_id })                 # chief_login → direct_client_logins
yandex_metrika_report({ counter_id, date1, date2, attribution: "last",
  direct_client_logins: ["<chief_login>"],
  dimensions: ["ym:ad:directOrder"],
  metrics: ["ym:ad:clicks","ym:ad:RUBAdCost"], limit: 1000 })
```

Клики и расход от модели не зависят; `ym:ad:visits` зависит — для визитов есть M3 и M3б.

Пустой ответ при живых кампаниях — у аккаунта Метрики нет доступа к этому кабинету или логин не тот; это не «расходов нет».

Поле не принято API → см. «Правила и фолбеки» ниже, отметь в `limitations`.

---

## Атрибуция Директ ↔ Метрика

С 25.06.2026 Метрика считает старые модели по аналогам и сама переводит устаревшие имена (`lastsign…`, `first…`) в группировках и фильтрах. Поэтому в `dimensions`/`filters` пиши имена без модели (`ym:s:TrafficSource`) — сервер подставит модель из `attribution`. Таблица ниже — для сверки с моделью кампании в Директе; какую модель брать в рецептах Метрики, задаёт раздел «Две модели — два вопроса».

| Директ | Метрика (`attribution`) |
|---|---|
| `FC` / `FCCD` | `cross_device_first` |
| `LC` / `LCCD` | `last` |
| `LSC` / `LSCCD` | `cross_device_last_significant` (по умолчанию) |
| `AUTO` | `automatic` |

Конверсии Метрики и Директа **не сводим в ноль**: Метрика считает к дате визита, Директ — к дате клика.

## Имена метрик и группировок

Бери имена **только из рецептов и таблицы этого файла**; не придумывай и не перебирай наугад. Проверено на
живом сервере 16.11.2026:

| Пространство | Метрики | Группировки |
|---|---|---|
| визиты `ym:s:*` | `ym:s:visits`, `ym:s:users`, `ym:s:bounceRate`, `ym:s:pageDepth`, `ym:s:avgVisitDurationSeconds`, `ym:s:anyGoalConversionRate`, `ym:s:goal<ID>reaches`, `ym:s:goal<ID>conversionRate` | `ym:s:TrafficSource`, `ym:s:SourceEngine`, `ym:s:DirectClickOrder`, `ym:s:UTMSource`, `ym:s:UTMMedium`, `ym:s:UTMCampaign`, `ym:s:startURL`, `ym:s:deviceCategory`, `ym:s:regionCity`, `ym:s:date` |
| Директ `ym:ad:*` (нужен `direct_client_logins`) | `ym:ad:clicks`, `ym:ad:visits`, `ym:ad:RUBAdCost`, `ym:ad:RUBAdCostPerVisit` | `ym:ad:directOrder`, `ym:ad:directPhraseOrCond`, `ym:ad:directPlatformType` |

**`ym:s:*` и `ym:ad:*` в одном запросе не смешивай** — Метрика отклонит их как несовместимые. Имён
`ym:ad:cost`, `impressions`, `expense`, `spend` нет: сервер отвечает `400 invalid_parameter`.

## Правила и фолбеки

- **`attribution` не убирай никогда.** Ошибка в вызове с `attribution` → проверь имена группировок и фильтра
  (без модели в имени) и повтори **один раз** с той же моделью. Второй сбой — в `limitations`; отчёт без
  явной модели не строй.
- **Ошибка `400 invalid_parameter` — неверное имя или сочетание, а не «данных нет».** Сверь имя с таблицей
  выше и повтори один раз. Не вышло — в `limitations`: «не удалось запросить <что>: сервер не принял
  параметр». Вывод «Метрика этого не отдаёт» или «расходов нет» из такой ошибки **не делай**.
- **Проверочный запрос подтверждает только то, что в нём было.** `preset` и другие метрики не доказывают,
  что есть клики, расход или нужная модель; смотри `columns` и `attribution` ответа.
- **Пришли не все строки** — в ответе есть `note`, `total_rows` больше числа строк: догрузи тем же запросом
  с `offset` из `note` (`limit` до 1000). Не догрузил — по кампаниям пиши «данные по N из M строк»;
  `totals` уже посчитаны по всем строкам, их можно брать как итог.
- Ошибка по необязательной метрике (`goal<ID>reaches`, `avgVisitDurationSeconds`) → убери **эту метрику** и
  повтори один раз; `attribution`, группировки и фильтр не трогай. Второй сбой — в `limitations`.
- `sampled: true` на малом объёме → повтори с `accuracy: "full"` или помечай вывод «приблизительно».
- Отчёты Метрики компактные, но всё равно ставь `limit` — ответ идёт через контекст.
