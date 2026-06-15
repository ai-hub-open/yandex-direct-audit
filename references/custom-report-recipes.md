# Рецепты CUSTOM_REPORT через `yandex_direct_api_call`

Дедикейтед report-тулы MCP покрывают `campaign / ad / search_queries`. Срезы по площадкам и сегментам (устройство/пол/возраст/гео/час) собираем `CUSTOM_REPORT`'ом через сырой `yandex_direct_api_call` к эндпоинту отчётов.

## Прежде чем использовать

Сначала прочти раздел «Сырой api_call» в `mcp-tools-map.md`. **Проверь, что `api_call` достаёт до `/json/v5/reports`** (отдельный эндпоинт, формат ответа — TSV, не JSON). Если нет — это ограничение, фиксируй в отчёте и не выдумывай данные.

## Общая форма запроса к Reports

Тело CUSTOM_REPORT (передаётся в `api_call` как payload к reports-эндпоинту):

```json
{
  "params": {
    "SelectionCriteria": {
      "DateFrom": "2025-05-01",
      "DateTo": "2025-05-31",
      "Filter": []
    },
    "FieldNames": [],
    "ReportName": "audit_<уникальное_имя>",
    "ReportType": "CUSTOM_REPORT",
    "DateRangeType": "CUSTOM_DATE",
    "Format": "TSV",
    "IncludeVAT": "NO"
  }
}
```

Обязательные заголовки отчётов (их выставляет обёртка MCP; если делаешь руками — учитывай):
`processingMode: auto` (или офлайн с опросом), `returnMoneyInMicros: false` (чтобы деньги сразу в рублях; если обёртка не умеет — конвертируй скриптом), `skipReportHeader: true`, `skipReportSummary: true`.

⚠️ `ReportName` должен быть **уникальным** в рамках аккаунта — добавляй timestamp/slug, иначе повторный запрос вернёт ошибку «отчёт с таким именем уже есть».

---

## Рецепт 1: Площадки РСЯ (Шаг 4)

```json
{
  "FieldNames": [
    "Placement", "AdNetworkType", "CampaignName",
    "Impressions", "Clicks", "Ctr", "Cost",
    "Conversions", "CostPerConversion", "BounceRate"
  ],
  "SelectionCriteria": {
    "Filter": [
      { "Field": "AdNetworkType", "Operator": "EQUALS", "Values": ["AD_NETWORK"] }
    ]
  }
}
```

- Группировка по `Placement` идёт автоматически от набора полей.
- Если есть цели — добавь `Goals` и `AttributionModels` в params; поля конверсий разобьются по целям/моделям.
- `BounceRate` придёт только при связке с Метрикой — иначе пусто (см. ограничение №2 в `mcp-tools-map.md`).

## Рецепт 2: Срез по устройствам (Шаг 5)

```json
{
  "FieldNames": [
    "Device", "CampaignName",
    "Impressions", "Clicks", "Cost",
    "Conversions", "ConversionRate", "CostPerConversion"
  ]
}
```

`Device`: `DESKTOP / MOBILE / TABLET / SMART_TV`.

## Рецепт 3: Пол и возраст (Шаг 5)

```json
{
  "FieldNames": [
    "Gender", "Age", "CampaignName",
    "Clicks", "Cost", "Conversions", "CostPerConversion"
  ]
}
```

`Gender`: `GENDER_MALE / GENDER_FEMALE`. `Age`: `AGE_0_17 / AGE_18_24 / AGE_25_34 / AGE_35_44 / AGE_45_54 / AGE_55` (диапазоны могут отдаваться с суффиксами — сверяйся с ответом).

## Рецепт 4: География (Шаг 5)

```json
{
  "FieldNames": [
    "LocationOfPresenceName", "CampaignName",
    "Clicks", "Cost", "Conversions", "CostPerConversion"
  ]
}
```

`LocationOfPresenceName` — регион присутствия пользователя (где он физически). Есть ещё `TargetingLocationName` — регион таргетинга. Для корректировок по гео обычно интересен присутствие.

## Рецепт 5: Время суток (Шаг 5)

```json
{
  "FieldNames": [
    "HourOfDay", "CampaignName",
    "Clicks", "Cost", "Conversions", "CostPerConversion"
  ]
}
```

Можно добавить `DayOfWeek` для недельного паттерна. ⚠️ Некоторые срезы несовместимы с методом `bytime` — используй обычный CUSTOM_REPORT.

---

## Справочник полезных полей

**Метрики:** `Impressions, Clicks, Ctr, Cost, AvgCpc, AvgCpm, AvgImpressionPosition, AvgClickPosition, Conversions, ConversionRate, CostPerConversion, Revenue, Profit, GoalsRoi, Bounces, BounceRate, AvgPageviews, Sessions`.

**Срезы:** `CampaignId, CampaignName, CampaignType, AdGroupId, AdGroupName, AdId, Device, Age, Gender, IncomeGrade, LocationOfPresenceName, TargetingLocationName, Placement, AdNetworkType, Slot, CriteriaType, MatchType, Query, MatchedKeyword, Criterion, HourOfDay, DayOfWeek`.

**Фильтры (Operator):** `EQUALS, NOT_EQUALS, IN, NOT_IN, LESS_THAN, GREATER_THAN, STARTS_WITH_IGNORE_CASE` и др. Пример полезного фильтра «расход больше нуля»:
```json
{ "Field": "Cost", "Operator": "GREATER_THAN", "Values": ["0"] }
```

**Цели и атрибуция** (если считаем конверсии): в `params` добавь
```json
"Goals": ["<goal_id>"],
"AttributionModels": ["LYDCCD"]
```
до 10 целей за запрос. При указании целей колонки конверсий именуются по схеме `Conversions_<goal>_<model>`.

## Доступность полей

Поля чувствительны к регистру и со временем меняются. Перед хардкодом сверяйся с живым списком полей: `yandex.com/dev/direct/doc/ru/reports/fields-list`. По ЕПК (`UNIFIED_CAMPAIGN`) часть полей уровня критериев может не отдаваться. Если отчёт вернул ошибку по полю — убери его и повтори, не долби API в цикле (каждая ошибка ~20 баллов).
