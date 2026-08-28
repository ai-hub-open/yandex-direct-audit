# Рецепты CUSTOM_REPORT через `yandex_direct_report_custom`

Дедикейтед report-тулы покрывают `campaign / ad / search_queries`. Срезы по площадкам и сегментам (устройство/пол/возраст/гео/час) собираются тулом `yandex_direct_report_custom`.

## Прежде чем использовать

Прочти в `mcp-tools-map.md` два раздела: **«CUSTOM_REPORT через `report_custom`»** (таблица параметров) и **«Правила объёма отчётов»** (чанкинг, `page_limit`, фильтры, офлайн-очередь). Рецепты ниже дают только состав полей — правила объёма обязательны к каждому из них.

## Общая форма вызова

```
yandex_direct_report_custom({
  report_type: "CUSTOM_REPORT",
  fields: [ ... ],                       // см. рецепты
  date_from: "2025-05-01",
  date_to:   "2025-05-31",
  campaign_ids: [ ... ],                 // при чанкинге — одна кампания
  filters: [ ... ],                      // см. рецепты
  page_limit: 3000,
  goals: [ <goal_id> ],                  // если цели известны
  attribution_models: [ "<код кампании>" ],
  wait_seconds: 55
})
```

- **НДС не задаём** — `include_vat` по умолчанию `true`, а это и есть политика аудита (считаем реальные деньги рекламодателя, чтобы расход по площадкам сходился с расходом по кампаниям).
- **Имя отчёта не задаём** — коннектор сам делает его уникальным.
- **Деньги приходят в рублях.** Ничего не делим.
- **Цели и атрибуция** — модель берётся из настроек конкретной кампании; правила и коды в `references/attribution.md`. При указании целей колонки конверсий именуются `Conversions_<goal>_<model>` — сверни их в один `Conversions` (сумма по целям **в рамках одной модели**) перед прогоном анализаторов.

---

## Рецепт 1: Площадки РСЯ (Шаг 4)

```
fields: [
  "CampaignName", "CampaignId", "AdNetworkType", "Placement",
  "Impressions", "Clicks", "Ctr", "Cost", "AvgCpc",
  "Conversions", "ConversionRate", "CostPerConversion",
  "Revenue", "BounceRate", "AvgPageviews"
],
filters: [
  { field: "AdNetworkType", operator: "EQUALS",       values: ["AD_NETWORK"] },
  { field: "Clicks",        operator: "GREATER_THAN", values: ["0"] }
],
page_limit: 3000
```

- Группировка по `Placement` идёт автоматически от набора полей.
- ⚠️ **`Device` и `LocationOfPresenceName` в этот набор НЕ добавляй.** Каждый из них дробит любую площадку на десятки подстрок и раздувает отчёт в разы. Разбивку «почему» собирай **вторым узким проходом** только по топ-20 площадкам-кандидатам (`filters` по `Placement` `IN`), и только если она реально нужна для вывода.
- Фильтр `Clicks > 0` отсекает площадки без трафика. Анализатор дублирует фильтры `AD_NETWORK` и `Impressions > 0` на своей стороне — на случай, если они не применились.
- `BounceRate` и `AvgPageviews` — это и есть поведение по площадке, которое раньше тянули из Метрики. Приходят при привязанном счётчике; пусто → сигнал по отказам молчит, вывод строим по расходу и конверсиям.
- Полный ruleset порогов — `references/rsya-minus-rules.md`; ядро — `scripts/analyze_placements.py`.

## Рецепт 2: Срез по устройствам (Шаг 5)

```
fields: [
  "Device", "CampaignName",
  "Impressions", "Clicks", "Cost",
  "Conversions", "ConversionRate", "CostPerConversion",
  "BounceRate", "AvgPageviews"
],
filters: [ { field: "Clicks", operator: "GREATER_THAN", values: ["0"] } ],
page_limit: 500
```

`Device`: `DESKTOP / MOBILE / TABLET / SMART_TV`.

## Рецепт 3: Пол и возраст (Шаг 5)

```
fields: [
  "Gender", "Age", "CampaignName",
  "Clicks", "Cost", "Conversions", "CostPerConversion",
  "BounceRate", "AvgPageviews"
],
filters: [ { field: "Clicks", operator: "GREATER_THAN", values: ["0"] } ],
page_limit: 500
```

`Gender`: `GENDER_MALE / GENDER_FEMALE`. `Age`: `AGE_0_17 / AGE_18_24 / AGE_25_34 / AGE_35_44 / AGE_45_54 / AGE_55` (диапазоны могут отдаваться с суффиксами — сверяйся с ответом).

## Рецепт 4: География (Шаг 5)

```
fields: [
  "LocationOfPresenceName", "CampaignName",
  "Clicks", "Cost", "Conversions", "CostPerConversion",
  "BounceRate", "AvgPageviews"
],
filters: [ { field: "Clicks", operator: "GREATER_THAN", values: ["0"] } ],
page_limit: 500
```

`LocationOfPresenceName` — регион присутствия пользователя (где он физически), приходит **именем** («Москва», «Санкт-Петербург»). Есть ещё `TargetingLocationName` — регион таргетинга. Для корректировок по гео обычно интересно присутствие.

Справочник регионов звать не нужно: имя региона у тебя уже есть, а корректировку маркетолог ставит в интерфейсе, выбирая регион из списка по названию — числовой `region_id` в рекомендации не требуется.

## Рецепт 5: Время суток (Шаг 5)

```
fields: [
  "HourOfDay", "CampaignName",
  "Clicks", "Cost", "Conversions", "CostPerConversion"
],
filters: [ { field: "Clicks", operator: "GREATER_THAN", values: ["0"] } ],
page_limit: 500
```

Можно добавить `DayOfWeek` для недельного паттерна — но помни, что он умножает число строк на 7.

---

## Справочник полезных полей

**Метрики:** `Impressions, Clicks, Ctr, Cost, AvgCpc, AvgCpm, AvgImpressionPosition, AvgClickPosition, Conversions, ConversionRate, CostPerConversion, Revenue, Profit, GoalsRoi, Bounces, BounceRate, AvgPageviews, Sessions`.

**Срезы:** `CampaignId, CampaignName, CampaignType, AdGroupId, AdGroupName, AdId, Device, Age, Gender, IncomeGrade, LocationOfPresenceName, TargetingLocationName, Placement, AdNetworkType, Slot, CriteriaType, MatchType, Query, MatchedKeyword, Criterion, HourOfDay, DayOfWeek`.

**Операторы фильтров:** `EQUALS, NOT_EQUALS, IN, NOT_IN, LESS_THAN, GREATER_THAN, STARTS_WITH_IGNORE_CASE` и др.

**Поведенческие поля** (`BounceRate, AvgPageviews, Bounces, Sessions`) и **конверсионные** (`Conversions, ConversionRate, CostPerConversion, Revenue, Profit, GoalsRoi`) наполняются только при привязанном счётчике и настроенных целях — см. `references/attribution.md`.

## Доступность полей

Поля чувствительны к регистру и со временем меняются. Перед хардкодом сверяйся с живым списком: `yandex.com/dev/direct/doc/ru/reports/fields-list`. По ЕПК (`UNIFIED_CAMPAIGN`) часть полей уровня критериев может не отдаваться. Если отчёт вернул ошибку по полю — убери его и повтори **один раз**, не долби API в цикле (каждая ошибка ~20 баллов).
