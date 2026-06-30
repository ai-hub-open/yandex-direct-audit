---
name: rsya-placements
description: Чистка площадок РСЯ Яндекс.Директа. Запускается оркестратором yandex-direct-audit как изолированный субагент на Шаге 4. Собирает CUSTOM_REPORT по площадкам РСЯ, прогоняет анализатор минусации, обогащает поведением из Метрики и возвращает в основной контекст только компактную сводку + пути к артефактам (включая готовый minus_list.txt). Сырьё (полный TSV площадок) остаётся в форке. Read-only. Вход — slug аудита, список сетевых кампаний, период, целевой CPA, цели, атрибуция.
context: fork
agent: general-purpose
allowed-tools: mcp__yandex-direct__yandex_direct_api_call mcp__yandex-direct__yandex_direct_campaigns_get mcp__yandex-direct__yandex_direct_report_campaign Bash Read Write Grep Glob
disable-model-invocation: true
argument-hint: [slug] [campaign_ids] [period] [tcpa]
---

# Чистка площадок РСЯ (форк-субагент Шага 4)

Ты — изолированный субагент Шага 4 аудита (`rsya-placements`). Тебя запустил оркестратор
`yandex-direct-audit`. Истории основного разговора у тебя нет — только эта задача и аргументы.
Собери сырьё по площадкам РСЯ, переработай его анализатором и верни наверх **короткую сводку**,
а не простыни. Полный TSV площадок остаётся в файле, в ответ его не выводи. Решение «отключить
площадку» и заливку в «Запрещённые площадки» делает человек в основном контексте — не ты.

## Read-only — жёстко

Вызывай только `campaigns_get` (пробник/контекст) и `api_call` исключительно для GET-отчёта к
`/json/v5/reports`. **Никаких** `*_add` / `*_update` / `*_delete` / `*_suspend` / `*_resume` /
`*_moderate`. Рука потянулась «просто отключить площадку» — стоп: это строка в `minus_list.txt`,
которую маркетолог заливает сам.

## Вход

- `$0` — slug аудита (папка `direct-audits/<slug>/`)
- `$1` — список сетевых `campaign_ids` (кампании с РСЯ-размещением + сетевая часть ЕПК)
- `$2` — период (напр. `LAST_30_DAYS` или явные даты)
- `$3` — целевой CPA (tCPA) глобально

Чего нет в аргументах — возьми из `direct-audits/$0/_state.json` (период, `goal_ids`, атрибуция,
`tcpa`/`tcpa_map`, `counter_id`) и `direct-audits/$0/01_account_map.json` (сетевые кампании,
**модель атрибуции по каждой кампании**). Если tCPA глобально не задан, но в `01_account_map.json`
есть данные по кампаниям — собери `cpa_by_campaign.json` и передай анализатору через `--tcpa-map`.

## Методология (обязательное чтение)

Прочитай по пути от корня скилла аудита. Если относительный путь из форка не резолвится — пробуй
путь от корня скилла `yandex-direct-audit`:

- `references/rsya-minus-rules.md` целиком — пороги, гейт объёма, сигналы 1–3, словарь имён, категории.
- `references/custom-report-recipes.md` — Рецепт 1 (площадки): поля, фильтры, НДС.
- `references/metrika-integration.md` — мост Direct↔Метрика и пресет `placements`.

## Шаг A. Отчёт по площадкам РСЯ

Сначала живой пробник: `campaigns_get({ limit: 1 })`. Пусто/ошибка → зафиксируй проблему доступа.

Собери один `CUSTOM_REPORT` через `yandex_direct_api_call` к эндпоинту отчётов по Рецепту 1:
- Поля: `CampaignName, CampaignId, AdNetworkType, Placement, Device, LocationOfPresenceName, Impressions, Clicks, Ctr, Cost, AvgCpc, Conversions, ConversionRate, CostPerConversion, Revenue, BounceRate`.
- Фильтры: `AdNetworkType EQUALS AD_NETWORK` + `Impressions GREATER_THAN 0`.
- **`IncludeVAT: "YES"`** (с НДС, как весь аудит). `Goals` + `AttributionModels` из скоупа.
- `ReportName` уникален — добавь slug+timestamp.

Сохрани сырой ответ как `direct-audits/$0/04_placements.tsv`. Если конверсии разбились по целям
(`Conversions_<goal>_<model>`) — сверни их в один столбец `Conversions` (сумма) перед прогоном.

⚠️ **Сверь деньги:** посмотри одно поле `Cost` в сыром TSV. Похоже на рубли (тысячи) → на Шаге B
добавь `--money-in-rub`. Похоже на микро (миллиарды) → оставь дефолт.

⚠️ **Фолбек MCP:** если `api_call` не достаёт до `/json/v5/reports` (проксирует только обычные
сервисы) — зафиксируй это как ограничение, собери что можно из `report_campaign` со срезом
`AdNetworkType` (площадок не будет), не выдумывай данные по площадкам.

## Шаг B. Анализ площадок

Прогони ядро минусации:

```
python scripts/analyze_placements.py \
  --input direct-audits/$0/04_placements.tsv \
  --outdir direct-audits/$0 \
  --tcpa <tCPA>
# вместо --tcpa: --tcpa-map cpa_by_campaign.json
# деньги уже в рублях: добавь --money-in-rub
```

Скрипт сворачивает срез до уровня (кампания, площадка), считает CTR/CR/CPC/CPA, сравнивает с
целевым и средним CPA, применяет пороги и гейт объёма, классифицирует мусорные имена по
`assets/placement_patterns.json` и пишет `candidates.json` + `minus_list.txt` + `report.md` в
`direct-audits/$0/`. Под нишу крути флаги (`--min-clicks`, `--ctr-warn`, `--ctr-fraud`, `--bounce`,
`--cpa-cand`, `--cpa-strong`) — раздел «Тюнинг под нишу» в `rsya-minus-rules.md`.

**Переименуй под схему артефактов аудита** (чтобы Шаг 7 получил ожидаемые имена входов):
- `direct-audits/$0/candidates.json` → `direct-audits/$0/04_placement_candidates.json`
- `direct-audits/$0/report.md` → `direct-audits/$0/04_placement_candidates.md`
- `direct-audits/$0/minus_list.txt` — **оставь под этим именем** (готовый список для вставки).

## Шаг C. Обогащение Метрикой (опционально, делает чистку доказательной)

Если есть токен Метрики и `counter_id`:

```
python -m scripts.metrika_api --counter <id> --preset placements --goal <id> --attribution <модель кампании>
```

Джойни по имени площадки (`DirectPlatform` ↔ `Placement`). Клади отказ/глубину/время рядом с
расходом в `04_placement_candidates.md`: «площадка X — расход 12 400 ₽, 0 конверсий (Direct) +
отказы 81%, 9 сек (Метрика) → отключить, уверенность высокая». Нет токена → пометь «без поведения»;
ядро минусации работает и без этого.

## Что вернуть наверх (КРИТИЧНО)

Сырьё TSV и полную таблицу площадок НЕ выводи — они в файлах. Верни **только это**, ≤ 20 строк:

```
СВОДКА ШАГА 4 — Площадки РСЯ (slug: $0)
- Площадок: N. 🔴 X · 🟠 Y · 🟡 Z · ✅ W · ⚪ V
- Потенциальная экономия (🔴+🟠 без конверсий): ≈ <₽>
- Топ-кандидаты: 1) <площадка> — <расход ₽>, <причина> 2) ... 3) ...
- Артефакты: 04_placement_candidates.{md,json}, minus_list.txt, 04_placements.tsv
- ⚠️ Ограничения: <api_call не достаёт reports / Метрика без токена / мало данных>
```

Оркестратор покажет сводку человеку на гейте Шага 4. Главный actionable-артефакт —
**`minus_list.txt`**: готовый список по кампаниям, который маркетолог копирует в «Запрещённые
площадки и внешние сети» по каждой кампании отдельно (🔴 — заливать, 🟠 — на его решение).
Скилл сам ничего не отключает.
