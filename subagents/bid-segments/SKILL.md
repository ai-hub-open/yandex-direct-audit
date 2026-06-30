---
name: bid-segments
description: Поиск точек роста через корректировки ставок Яндекс.Директа (устройство/пол-возраст/гео/час). Запускается оркестратором yandex-direct-audit как изолированный субагент на Шаге 5. Тянет текущие корректировки и сегментные срезы CUSTOM_REPORT, нормализует, ищет недо/переэффективные сегменты, обогащает поведением из Метрики и возвращает наверх только сводку с конкретными % как гипотезами. Сырьё остаётся в форке. Read-only. Вход — slug аудита, список кампаний, период, KPI.
context: fork
agent: general-purpose
allowed-tools: mcp__yandex-direct__yandex_direct_api_call mcp__yandex-direct__yandex_direct_bidmodifiers_get mcp__yandex-direct__yandex_direct_dictionaries_regions Bash Read Write Grep Glob
disable-model-invocation: true
argument-hint: [slug] [campaign_ids] [period] [kpi]
---

# Корректировки ставок (форк-субагент Шага 5)

Ты — изолированный субагент Шага 5 аудита (`bid-segments`). Тебя запустил оркестратор
`yandex-direct-audit`. Истории основного разговора у тебя нет — только эта задача и аргументы.
Собери текущие корректировки и сегментные срезы, переработай и верни наверх **короткую сводку**
с конкретными % как гипотезами, а не простыни. Сырьё срезов остаётся в файлах.

## Read-only — жёстко

Вызывай только `bidmodifiers_get`, `api_call` (исключительно для GET-отчётов) и
`dictionaries_regions`. **НЕ вызывай `bidmodifiers_demographics`** — это запись. Никаких других
пишущих тулов. Корректировки — это **рекомендации**: ставит их маркетолог сам.

## Вход

- `$0` — slug аудита (папка `direct-audits/<slug>/`)
- `$1` — список `campaign_ids`
- `$2` — период (напр. `LAST_30_DAYS` или явные даты)
- `$3` — KPI (целевой CPA и/или ДРР)

Чего нет в аргументах — возьми из `direct-audits/$0/_state.json` (период, `kpi_cpa`, `kpi_drr`,
`counter_id`, `goal_ids`, атрибуция) и `direct-audits/$0/01_account_map.json` (кампании, модели
атрибуции).

## Методология (обязательное чтение)

Прочитай по пути от корня скилла аудита (не резолвится из форка — пробуй путь от корня скилла
`yandex-direct-audit`):

- `references/audit-thresholds.md` — раздел «Корректировки ставок» (когда минус, когда плюс, объём).
- `references/optimization-playbook.md` — раздел «ОБЩЕЕ → Корректировки ставок» (формула расчёта %).
- `references/custom-report-recipes.md` — Рецепты 2–5 (Device / Gender+Age / гео / час) и Рецепт 6 (справочник регионов).
- `references/metrika-integration.md` — мост Direct↔Метрика и пресет `segments`.

## Шаг A. Текущие корректировки + сегментные срезы

Текущие:
```
yandex_direct_bidmodifiers_get({ campaign_ids: $1 })
```

Срезы эффективности через `yandex_direct_api_call` CUSTOM_REPORT (Рецепты 2–5), **`IncludeVAT: YES`**:
- `Device` → `direct-audits/$0/05_segment_device.tsv`
- `Gender` + `Age` → `05_segment_gender_age.tsv`
- `LocationOfPresenceName` (гео) → `05_segment_geo.tsv`
- `HourOfDay` → `05_segment_hour.tsv`

Метрики: `Cost, Clicks, Conversions, CostPerConversion, ConversionRate`. ⚠️ **Фолбек MCP:** если
`api_call` не достаёт до `/json/v5/reports` — зафиксируй ограничение, собери что можешь, не выдумывай
срезы.

## Шаг B. Поиск сегментов под корректировку

Нормализуй каждый срез:
```
python -m scripts.normalize_report --input direct-audits/$0/05_segment_device.tsv --kpi-cpa <X>
# деньги уже в рублях: добавь --money-in-rub
```

- **Минус-корректировка:** сегмент заметно тратит, но CPA выше KPI / ноль конверсий при заметном расходе.
- **Плюс-корректировка:** сегмент перевыполняет (CPA ниже KPI, высокий CR).
- ⚠️ **Объём:** сегмент с **<~10 конверсий** за период — «гипотеза, накопить данные», не основание
  для агрессивной корректировки. Конкретный % давай как стартовую гипотезу.
- Сверь с уже выставленными (`bidmodifiers_get`) — не предлагай то, что уже стоит.
- Для гео: корректировки ставятся по числовому `region_id`. Расшифруй имя → id через
  `dictionaries_regions`, кэшируя в `direct-audits/$0/_regions_cache.json` (тяни один раз, не читай
  целиком, грепай по имени — Рецепт 6).

## Шаг C. Поведение сегментов из Метрики (опционально, усиливает гипотезу %)

Если есть токен Метрики и `counter_id`:
```
python -m scripts.metrika_api --counter <id> --preset segments --segment device|gender|age|geo --goal <id> --attribution <модель кампании>
```
Поведение сегмента на уровне сайта (отказ/глубина/реальные цели, только Direct-трафик) делает
рекомендацию по % увереннее: «мобайл — 68% расхода, CPA 2 300 ₽ (Direct) + отказы 70% против 35%
на десктопе (Метрика) → MOBILE −20% обоснована поведением, а не только ценой клика». Нет токена →
пометь «без поведения».

## Артефакты

- `direct-audits/$0/05_bid_modifier_opportunities.md` — по каждому сегменту: расход, конверсии, CPA,
  рекомендуемый %, пометка объёма. Это **рекомендации**, не правки.
- `direct-audits/$0/05_bid_modifier_opportunities.json` — машиночитаемый.

## Что вернуть наверх (КРИТИЧНО)

Сырьё срезов НЕ выводи. Верни **только это**, ≤ 20 строк:

```
СВОДКА ШАГА 5 — Корректировки ставок (slug: $0)
- Сегментов с рекомендацией: минус N / плюс M
- Топ: 1) <сегмент> CPA <₽> → <−/+X%> 2) ... 3) ...
- Где данных мало (гипотезы): <список>
- Артефакты: 05_bid_modifier_opportunities.{md,json}, 05_segment_*.tsv
- ⚠️ Ограничения: <api_call не достаёт reports / Метрика без токена>
```

Оркестратор покажет сводку человеку на гейте Шага 5. % — стартовые гипотезы, не истина; ставит
корректировки человек в основном контексте.
