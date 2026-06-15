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

## Рецепт 6: Справочник регионов (`dictionaries_regions`) — расшифровка гео

Это **не** CUSTOM_REPORT, а справочник (`Dictionaries.get`, `DictionaryNames: ["GeoRegions"]`), но логически он часть гео-анализа Шага 5, поэтому держим рецепт рядом.

### Когда он нужен (и когда НЕ нужен)

- **НЕ нужен**, если гео-срез собран Рецептом 4: поле `LocationOfPresenceName` уже отдаёт **имя** региона («Москва», «Санкт-Петербург»). Для простого «где тратим / где конвертим» справочник не требуется.
- **Нужен**, когда:
  1. рекомендуешь корректировку по гео — корректировки в Директе ставятся по **числовому `region_id`**, а отчёт дал только имя; нужно имя → id;
  2. надо **свернуть города в регион/округ** (агрегировать расход уровня города до области) — для этого нужна иерархия `ParentId`;
  3. отчёт где-то вернул числовой id вместо имени и его надо расшифровать.

### Вызов — один раз, в кэш

```
yandex_direct_dictionaries_regions()   // без параметров; вернёт всё дерево регионов
```

Справочник большой (~3 МБ, тысячи строк). Поэтому:
1. **Тяни один раз за весь аудит** и сразу сохраняй в `direct-audits/<slug>/_regions_cache.json`.
2. **Никогда не читай файл целиком в рассуждение** — только ищи по нему нужные регионы (см. ниже).
3. На повторных шагах бери из кэша, **не перезапрашивай API** (ошибочный/лишний вызов тоже жжёт квоту, см. бюджет квот в `mcp-tools-map.md`).

### Структура ответа

Каждый регион — объект примерно такого вида (точные имена полей сверь с ответом MCP):

```json
{
  "GeoRegionId": 213,
  "GeoRegionName": "Москва",
  "GeoRegionType": "City",
  "ParentId": 1
}
```

- `GeoRegionType` — уровень: `World / Country / Region / Administrative area / City / Village / City district` и т.п. (набор строк может отличаться — ориентируйся на ответ).
- `ParentId` — id родителя, по нему строится иерархия: Москва (213) → Московская область (1) → Россия (225) → Мир (0).
- Полезные ориентиры: `225` = Россия, `213` = Москва, `2` = Санкт-Петербург, `1` = Москва и область.

### Поиск по кэшу (имя → id и обратно)

Не загружай весь файл — ищи точечно. Через `jq`:

```bash
# имя → id (учитывая, что имя может встречаться у нескольких регионов)
jq '.[] | select(.GeoRegionName=="Москва") | {GeoRegionId, GeoRegionType, ParentId}' _regions_cache.json

# id → имя
jq '.[] | select(.GeoRegionId==213)' _regions_cache.json

# все города внутри региона (по ParentId)
jq '.[] | select(.ParentId==1) | .GeoRegionName' _regions_cache.json
```

(Путь к массиву зависит от того, как обёртка MCP завернула ответ — если регионы лежат под ключом, добавь его: `.regions[] | ...` или `.result.Regions[] | ...`.) Без `jq` подойдёт обычный греп по имени региона прямо в кэш-файле — он плоский, имя и id рядом.

### Подводные камни

- **Присутствие vs таргетинг.** `LocationOfPresenceName` — где пользователь физически (для корректировок по гео обычно нужен он). Есть ещё `TargetingLocationName` — регион таргетинга кампании. Не путай при джойне.
- **Неуникальные имена.** Одно имя может относиться к разным регионам (город и одноимённая область, тёзки в разных странах). Различай по `GeoRegionType` и `ParentId`, а не по одному имени.
- **Дубли www / вложенность** к регионам не относятся, но при сворачивании городов в область проверь, что не складываешь один и тот же расход дважды (город уже входит в область).

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
"AttributionModels": ["<модель из кампании>"]
```
до 10 целей за запрос. При указании целей колонки конверсий именуются по схеме `Conversions_<goal>_<model>`.

⚠️ **Модель не хардкодь и определяй отдельно для каждой кампании.** Подставляй Direct-код модели **из настроек самой кампании** (Шаг 1); если в кампании не задана — `LSCCD` (последний значимый, кросс-девайс). Ту же модель применяй и в Метрике (через единый словарь `metrika-integration.md` → раздел «Атрибуция»), чтобы срезы Директа и Метрики пересекались по одной логике. Допустимые коды: `FC/LC/LSC/LYDC/FCCD/LCCD/LSCCD/LYDCCD/AUTO`.

## Доступность полей

Поля чувствительны к регистру и со временем меняются. Перед хардкодом сверяйся с живым списком полей: `yandex.com/dev/direct/doc/ru/reports/fields-list`. По ЕПК (`UNIFIED_CAMPAIGN`) часть полей уровня критериев может не отдаваться. Если отчёт вернул ошибку по полю — убери его и повтори, не долби API в цикле (каждая ошибка ~20 баллов).
