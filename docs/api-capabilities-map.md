# Карта возможностей API Яндекс.Директ и Яндекс.Метрика

> Справочный документ для проекта `yandex-direct-audit`.
> Что можно брать из API Директа и Метрики, что уже умеют наши MCP-серверы, и где дыры для качественной работы скиллов.
> Дата сборки: 2026-06-26. Источник — официальная документация `yandex.ru/dev` (проверено вживую) + аудит исходного кода двух локальных MCP-серверов.

---

## 0. Как читать этот документ

Документ отвечает на один вопрос: **что нам нужно «уметь брать» из API Директа и Метрики, чтобы наш funnel-скилл работал качественно** — и насколько мы это уже умеем.

Обозначения по всему тексту:
- ✅ — уже реализовано в нашем MCP-сервере, работает.
- ❌ — дыра: API это умеет, но наш MCP пока **не** предоставляет.
- ⚠️ — важная поправка или нюанс честности (расхождение с памятью/ожиданиями).

Главный вывод одной строкой:
- **Метрика** в нашем MCP покрыта почти полностью — добавлять почти нечего.
- **Директ** имеет 5 критичных дыр, которые напрямую ломают обещания конкретных скиллов (см. раздел 5).

---

## 1. Резюме: топ-приоритеты (что чинить в Директ-MCP)

| # | Дыра в Директ-MCP | Какой скилл блокирует | Приоритет |
|---|---|---|---|
| 1 | Конверсии/CPA/ROI в отчётах Директа (колонки зашиты в коде) | весь аудит «по деньгам», `yandex-direct-funnel` lifecycle | 🔴 Высокий |
| 2 | Привязка счётчика Метрики и целей к кампании | `metrika-goals-setup` | 🔴 Высокий |
| 3 | Управление автостратегиями (переключение стратегий) | `bidding-strategy` | 🔴 Высокий |
| 4 | Прогноз бюджета и цены клика (Forecast) | `frequency-calculator`, `bidding-strategy` | 🟠 Средний |
| 5 | Расширения объявлений (быстрые ссылки, уточнения, визитки) + ретаргетинг | `usp-generator`, сборка объявлений и РСЯ | 🟠 Средний |
| 6 | Changes (что изменилось) + аккаунтный минус-лист | экономия лимитов, `negative-keywords-builder` | 🟡 Низкий |

Метрика-MCP отдельных «дыр-блокеров» не имеет — мелкие пробелы перечислены в разделе 4.3.

---

## 2. Карта API Яндекс.Директа (версия 5)

Базовый принцип: каждый сервис — отдельный «отдел» по адресу `https://api.direct.yandex.com/json/v5/{сервис}`. Запросы — HTTPS POST (JSON или SOAP). Версия 5 актуальна; «живого» оперативного режима из v4 в ней нет. Обзор: https://yandex.ru/dev/direct/doc/ru/concepts/overview

### 2.1. Управление сущностями (структура аккаунта)

«Этажи» сверху вниз: Кампания → Группа → Объявление → Условия показа (ключи/аудитории), плюс переиспользуемые библиотеки.

| Сервис | Назначение простыми словами | Ключевые методы | Статус MCP |
|---|---|---|---|
| **Campaigns** | Кампании: бюджет, стратегия, сроки, минус-слова уровня кампании | add, update, delete, get, suspend, resume, archive, unarchive | ✅ (кроме archive/unarchive) |
| **AdGroups** | Группы: объединяют объявления с общими условиями (ключи, регион, аудитории) | add, get, update, delete | ✅ |
| **Ads** | Объявления: тексты, заголовки, картинки, ссылки | add, update, delete, get, suspend, resume, archive, unarchive, moderate | ✅ (кроме archive/unarchive) |
| **Keywords** | Ключевые фразы и автотаргетинг | add, update, delete, suspend, resume, get | ✅ |
| **AudienceTargets** | Ретаргетинг/интересы: «показывать тем, кто…» | add, get, delete, suspend, resume, setBids | ❌ |
| **RetargetingLists** | Правила ретаргетинга (списки, цели, сегменты) | add, get, update, delete | ❌ |
| **Sitelinks** | Быстрые ссылки (набор `SitelinksSet`) | add, get, delete (update нет) | ❌ |
| **VCards** | Визитки: телефон, адрес, часы, email | add, get, delete (update нет) | ❌ |
| **AdExtensions** | Уточнения (короткие преимущества под объявлением) | add, get, delete | ❌ |
| **AdImages** | Библиотека изображений аккаунта | add, get, delete | ✅ |
| **NegativeKeywordSharedSets** | Общий минус-лист уровня аккаунта (один набор → много кампаний) | add, get, update, delete | ❌ |

Смежные сервисы того же блока (существуют, у нас не реализованы): `Businesses`, `Creatives`, `AdVideos`, `TurboPages`, `Leads`, `Feeds`, `KeywordsResearch`, `DynamicTextAdTargets`, `SmartAdTargets`.

**Типы кампаний:** `TextCampaign` (текстово-графические), `MobileAppCampaign`, `DynamicTextCampaign`, `CpmBannerCampaign` (медийная), `SmartCampaign`, `UnifiedCampaign` (Единая перфоманс-кампания). ⚠️ Наш MCP создаёт только `TextCampaign` и только с поиском (сети принудительно выключены).

### 2.2. Ставки и стратегии

| Сервис | Назначение | Методы | Статус MCP |
|---|---|---|---|
| **Bids** | Ручные ставки (устаревающий способ) + данные подбора | get, set, setAuto | ❌ |
| **KeywordBids** | Ставки по фразам — актуальная замена Bids | get, set, setAuto | ❌ |
| **BidModifiers** | Корректировки ставок (множители) | add, get, set, delete | ⚠️ Частично (только demographics: пол/возраст) |

**KeywordBids.setAuto** умеет ставку под желаемый **объём трафика** (`SearchByTrafficVolume`): `TargetTrafficVolume` + `BidCeiling` (потолок). ⚠️ «Объём трафика» заменил старые «позиции/спецразмещение» — платим за долю аукционного трафика, а не за место.

**Типы корректировок BidModifiers (константы API):**
`MOBILE_ADJUSTMENT`, `TABLET_ADJUSTMENT`, `DESKTOP_ADJUSTMENT`, `DESKTOP_ONLY_ADJUSTMENT`, `DEMOGRAPHICS_ADJUSTMENT`, `RETARGETING_ADJUSTMENT`, `REGIONAL_ADJUSTMENT`, `VIDEO_ADJUSTMENT`, `SMART_AD_ADJUSTMENT`, `SERP_LAYOUT_ADJUSTMENT`, `INCOME_GRADE_ADJUSTMENT`, `AD_GROUP_ADJUSTMENT`.
⚠️ Корректировки `WEATHER` (по погоде) в API v5 **не существует**. Несколько корректировок **перемножаются**.

**Стратегии показа (BiddingStrategy)** — задаются отдельно для Поиска и для Сетей. Это сердце скилла `bidding-strategy`:

Поиск: `HIGHEST_POSITION` (ручное), `WB_MAXIMUM_CLICKS` (максимум кликов за недельный бюджет), `WB_MAXIMUM_CONVERSION_RATE`, `AVERAGE_CPC`, `AVERAGE_CPA`, `AVERAGE_CPA_MULTIPLE_GOALS`, `AVERAGE_CRR` (по ДРР), `PAY_FOR_CONVERSION` (оплата за конверсии), `PAY_FOR_CONVERSION_CRR`, `PAY_FOR_CONVERSION_MULTIPLE_GOALS`, `MAX_PROFIT`, `SERVING_OFF`.

Сети: `NETWORK_DEFAULT`, `MAXIMUM_COVERAGE`/`MANUAL_CPM`, `WB_MAXIMUM_CLICKS`, `WB_MAXIMUM_CONVERSION_RATE`, `AVERAGE_CPC/CPA/CRR`, `CP_/WB_MAXIMUM_IMPRESSIONS`, варианты по видео и повторным показам, `SERVING_OFF`.

⚠️ Наш MCP создаёт кампанию только с `HIGHEST_POSITION` на поиске + `SERVING_OFF` в сетях. Переключить автостратегию через MCP **нельзя** — это дыра #3.

Справочники: https://yandex.ru/dev/direct/doc/ru/objects/campaign-strategies · https://yandex.ru/dev/direct/doc/ru/annex/strategies

### 2.3. Прогнозирование (Forecast)

⚠️ **Отдельного сервиса прогноза в API v5 НЕТ.** Прогноз бюджета живёт в старом **API v4 (Live 4)** и продолжает работать.

Процесс асинхронный: `CreateNewForecast` (вернёт `ForecastID`) → `GetForecastList` (ждать статус `Done`) → `GetForecast` (забрать) → `DeleteForecastReport`.

Что возвращает (по каждой фразе и суммарно):
- `Shows` — прогноз показов;
- `Clicks` / `FirstPlaceClicks` / `PremiumClicks`;
- `CTR` / `FirstPlaceCTR` / `PremiumCTR`;
- `Min` / `Max` / `PremiumMin` / `PremiumMax` — **диапазон средней цены клика (CPC)** по блокам;
- `AuctionBids`, `Currency`.

Это источник для `frequency-calculator` (CPC + показы + CTR → расчёт частотности и бюджета). ⚠️ В нашем MCP прогноза нет (дыра #4); сейчас CPC берём из справочной таблицы-фолбека.

Документация: https://yandex.ru/dev/direct/doc/dg-v4/tasks/HowToCalculateBudget.html · https://yandex.ru/dev/direct/doc/dg-v4/live/GetForecast.html

### 2.4. Статистика и отчёты (Reports) — ключевой блок для аудита

Сервис: https://yandex.ru/dev/direct/doc/ru/reports · Endpoint: `https://api.direct.yandex.com/v5/reports`. Запрос — POST с объектом `ReportDefinition`. Формат ответа — только TSV (UTF-8), пустые ячейки `--`.

**Типы отчётов (ReportType):**

| Константа | Назначение |
|---|---|
| `ACCOUNT_PERFORMANCE_REPORT` | по аккаунту целиком |
| `CAMPAIGN_PERFORMANCE_REPORT` | по кампаниям |
| `ADGROUP_PERFORMANCE_REPORT` | по группам |
| `AD_PERFORMANCE_REPORT` | по объявлениям |
| `CRITERIA_PERFORMANCE_REPORT` | по условиям показа (ключи, автотаргетинг, ретаргетинг, аудитории) |
| `CUSTOM_REPORT` | произвольные группировки (самый гибкий) |
| `SEARCH_QUERY_PERFORMANCE_REPORT` | по реальным поисковым запросам (глубина 180 дней) |
| `REACH_AND_FREQUENCY_PERFORMANCE_REPORT` | по медийным (охватным) кампаниям |

#### Поля по конверсиям и связка с Метрикой (критично для аудита)

Конверсионные метрики:
- `Conversions` — число конверсий по Метрике;
- `ConversionRate` — конверсии / клики, %;
- `CostPerConversion` — стоимость конверсии (роль CPA; отдельного `AvgCpa` в v5 нет);
- `Revenue` — ценность конверсий (доход);
- `Profit` — прибыль = ценность − стоимость кликов;
- `GoalsRoi` — ROI = (Revenue − Cost) / Cost (это и есть ДРР/ROI);
- `PurchaseRevenue` / `PurchaseProfit` / `PurchaseGoalsRoi` — то же только по целям-покупкам.

Привязка целей — атрибут `Goals` (массив `goal_id`, макс. 10). Конверсионные поля разворачиваются в колонки на каждую связку **цель × модель атрибуции**: `<Поле>_<goal_id>_<model>`, например `Conversions_20002_LSCCD`, `GoalsRoi_1234567_FCCD`.

Модели атрибуции — атрибут `AttributionModels`: `LC` (последний переход), `FCCD` (первый, кросс-девайс), `LSCCD` (последний значимый, кросс-девайс), `AUTO`. Данные Метрики доступны с 30.07.2019; нужен установленный счётчик и настроенные цели.

⚠️ Прямого поля «ассоциированные конверсии» в Директе нет — это область Метрики; в Директе её роль играет выбор модели атрибуции.

#### Остальные поля (по категориям)

- **Идентификаторы:** `CampaignId/Name/Type`, `AdGroupId/Name`, `AdId`, `CriterionId/Criterion/CriterionType`, `MatchedKeyword`.
- **Срезы времени:** `Date`, `Week`, `Month`, `Quarter`, `Year` (только одно). Срезов «час суток»/«день недели» в полях API v5 нет.
- **Демография:** `Age`, `Gender`, `IncomeGrade`.
- **Устройства/сети:** `Device`, `MobilePlatform`, `CarrierType`, `AdNetworkType` (`SEARCH` vs `AD_NETWORK`), `Placement` (площадка РСЯ — домен), `ExternalNetworkName`.
- **География:** `LocationOfPresenceName/Id` (где пользователь) и `TargetingLocationName/Id` (на какой регион нацелен).
- **Позиция/формат:** `Slot` (`PREMIUMBLOCK`/`ALONE`/`SUGGEST`/…), `AdFormat`, `ClickType`.
- **Поисковые запросы** (только `SEARCH_QUERY_PERFORMANCE_REPORT`): `Query`, `MatchType`, `TargetingCategory`.
- **Базовые метрики:** `Impressions`, `Clicks`, `Ctr`, `Cost`, `AvgCpc`, `AvgCpm`, `AvgTrafficVolume`, `WeightedImpressions`, `WeightedCtr`, и др.
- **Поведенческие (из Метрики):** `Sessions`, `Bounces`, `BounceRate`, `AvgPageviews`.

**Фильтры:** `SelectionCriteria.Filter` — массив `{Field, Operator, Values}` (логика AND). Операторы: `EQUALS`, `NOT_EQUALS`, `IN`, `NOT_IN`, `GREATER_THAN`, `LESS_THAN`, `STARTS_WITH_*` и т.д. Деньги в фильтрах — целые «микроденьги» (× 1 000 000).

**Период (DateRangeType):** `TODAY`, `YESTERDAY`, `LAST_3/5/7/14/30/90/365_DAYS`, `THIS/LAST_WEEK*`, `THIS/LAST_MONTH`, `ALL_TIME`, `AUTO` (инкрементальная синхронизация), `CUSTOM_DATE` (+ `DateFrom`/`DateTo`).

**Лимиты Reports:** ≤20 запросов за 10 сек; ≤5 одновременных офлайн-отчётов; готовый отчёт хранится 5 часов; глубина статистики 3 года, `Query` — 180 дней.

⚠️ **Дыра #1:** у нас колонки отчётов **зашиты в коде** (см. раздел 4.1) — конверсий/CPA/ROI/разрезов нет.

Источники: https://yandex.ru/dev/direct/doc/ru/spec · https://yandex.ru/dev/direct/doc/ru/fields-list · https://yandex.ru/dev/direct/doc/ru/example-metrika

### 2.5. Контроль изменений, словари, агентские методы

- **Changes** — «что изменилось с момента X?», чтобы тянуть только дельту и экономить баллы. Методы: `checkDictionaries`, `checkCampaigns`, `check`. ❌ у нас нет (дыра #6). URL: https://yandex.ru/dev/direct/doc/ru/changes/changes
- **Dictionaries** — один метод `get`: `GeoRegions`, `Currencies`, `TimeZones`, `MetroStations`, `Constants`, `Interests`, `AudienceInterests`, `SupplySidePlatforms` и др. ✅ частично (регионы, валюты, интересы, все).
- **AgencyClients / Clients** — управление клиентами агентства и параметрами рекламодателя (валюта, НДС, `Restrictions` — потолки аккаунта и суточный лимит баллов API, `Settings`). ❌ у нас нет.
- ⚠️ Программного управления представителями/доступами в API v5 нет — только чтение; выдача доступа — в веб-интерфейсе.

### 2.6. Лимиты и баллы (units)

- Остаток баллов — в заголовке ответа `Units` (`израсходовано/осталось/суточный лимит`).
- Стоимость: `get` — 15 + 1/объект; `add`/`update` — 20 + 20/объект; любая ошибка — 20.
- Лимиты: ≤5 одновременных запросов; `get` — макс. 10 000 объектов (постранично через `Page`).
- Авторизация: OAuth 2.0, заголовок `Authorization: Bearer <token>`, для агентств — `Client-Login`. Есть песочница (Sandbox).
- URL: https://yandex.ru/dev/direct/doc/ru/concepts/units · https://yandex.ru/dev/direct/doc/ru/concepts/auth-token

---

## 3. Карта API Яндекс.Метрики

У Метрики четыре основных API + два «соседних». Обзор: https://yandex.ru/dev/metrika/ru/

### 3.1. Reporting API (отчёты) — `stat/v1/data`

«Конструктор отчётов»: задаёшь метрики (цифры) и dimensions (разрезы) за период — получаешь таблицу. Источник: https://yandex.ru/dev/metrika/ru/stat/

**Эндпоинты (5):** `/stat/v1/data` (таблица), `/data/bytime` (по времени, для графиков), `/data/drilldown` (дерево: кампания → группа → объявление → фраза), `/data/comparison` и `/comparison/drilldown` (сравнение сегментов/периодов).

**Ключевые параметры:** `ids` (счётчик), `metrics` (обязателен), `dimensions`, `date1/date2`, `filters` (сегментация), `sort`, `limit` (до 100 000 строк), `offset`, `accuracy` (управление семплированием: `low/medium/high/full` или доля), `preset`, `lang`, `timezone`.

**Два «мира» данных, не смешивать:** `ym:s:*` — визиты (сессии, конверсии, источники, поведение); `ym:pv:*` — просмотры/хиты.

**Группы метрик/измерений:**
- Поведение: `visits`, `users`, `pageviews`, `bounceRate` (% отказов), `pageDepth` (глубина), `avgVisitDurationSeconds` (время на сайте).
- Источники и UTM: `<attribution>TrafficSource`, `UTMSource/Medium/Campaign/Content/Term`.
- Конверсии по целям: `ym:s:goal<goal_id><метрика>` — `reaches`, `conversionRate`, `converted<currency>Revenue` и др.; плюс `anyGoal*` и `favoriteGoals*`.
- Ecommerce/доход: `ecommercePurchases`, `ecommerce<currency>ConvertedRevenue`, товары/корзины.
- Гео и демография: `regionCountry/City/Area`, `ageInterval`, `gender`.

### 3.2. Рекламные измерения Директа — `ym:ad:*` (самое ценное для PPC)

Статистика по рекламе Директа до уровня поисковой фразы и объявления, **с расходом**. Справочник: https://yandex.ru/dev/metrika/ru/stat/attrandmetr/dim_all

Измерения (все поддерживают `<attribution>`):
- `ym:ad:<attribution>DirectOrder` — кампания;
- `DirectBannerGroup` — группа;
- `DirectBanner` — объявление;
- `DirectPhraseOrCond` — условие показа / ключевая фраза;
- `DirectSearchPhrase` — реальный поисковый запрос;
- `DirectPlatformType` / `DirectPlatform` — площадка (поиск/сети).

Метрики (с расходом):
- `ym:ad:clicks`, `ym:ad:visits`, `ym:ad:users`;
- `ym:ad:<currency>AdCost` — расход (например `RUBConvertedAdCost`);
- `ym:ad:<currency>ConvertedAdCostPerVisit` — фактически CPC/цена за визит;
- поведенческие в рекламном разрезе: `bounceRate`, `pageviews`, `avgVisitDurationSeconds`;
- конверсии: `ym:ad:goal<goal_id>...`.

⚠️ **Нюанс честности:** расход в `ym:ad:*` подтягивается из связки Директ↔Метрика, но Метрика — не биллинг. Для точных финансов (списания, НДС, баланс) первоисточник — **API Директа**. Метрика хорошо отвечает «сколько визитов/конверсий и какого качества дала фраза», а расход тут — для прикидки CPA/ROI.

### 3.3. Модели атрибуции

Правило, какому источнику засчитать конверсию. Коды для API: `first`, `last`, `lastsign` (последний значимый), `last_yandex_direct_click` (последний клик по Директу), `automatic` (ML-атрибуция). Плюс кросс-девайс версии (`cross_device_*`).

Для аудита Директа смотрят `last_yandex_direct_click` (вклад рекламы) и `automatic` (рекомендация Яндекса для автостратегий). Сравнение `first` vs `last` показывает, кампания «привлекает» или «дожимает». Источник: https://yandex.ru/support/metrica/reports/attribution-model.html

### 3.4. Management API (управление)

Создаёт и настраивает объекты Метрики. Источник: https://yandex.ru/dev/metrika/ru/management/

- **Counters** — счётчики (CRUD).
- **Goals** — цели. Типы (`goal_type`): `url`, `number` (число просмотров), `step` (составная, до 5 шагов), `action` (JS-событие), `visit_duration`, `phone`, `email`, `search`, `messenger`, `file`, `social`, `chat`, `payment_system`. Поля: `conditions_json`, `depth`, `duration`, `default_price` (ценность цели), `is_favorite`.
- **Segments** — сохранённые сегменты по выражению.
- **Filters** — очистка данных (резать ботов/внутренний трафик).
- **Operations** — преобразования URL (склейка без UTM и т.п.).
- **Grants / Delegates** — доступы (`public_stat`/`view`/`edit`) и представители.
- **Labels** — метки счётчиков. **Chart Annotations** — отметки событий на графиках.

⚠️ Составная цель (`step`) — до 5 шагов, засчитывается только если все пройдены в одном визите по порядку. Это нужно для воронок B2B (демо-заявка → триал).

### 3.5. Data Import API (загрузка данных)

Догрузка внешних данных, чтобы видеть полную картину. Источник: https://yandex.ru/dev/metrika/ru/data-import/

- `expenses_upload` — расход по другим каналам (для единого ROI);
- `offline_conversions_upload` — офлайн-конверсии (оплаты, договоры);
- `calls_upload` — звонки (коллтрекинг);
- `user_params_upload` — атрибуты посетителей.

⚠️ **Ключевое для автостратегий со звонками/долгими сделками:** офлайн-конверсии и звонки превращают «заявку» в реальную «продажу» внутри Метрики — тогда Директ оптимизируется на настоящие деньги, а не на промежуточный клик.

### 3.6. Logs API (сырые данные)

Выгрузка неагрегированных данных построчно: каждый визит/хит. Источники `visits`/`hits`. Процесс: создать запрос → дождаться → скачать частями → удалить. Ограничения: период ≤1 год, нет данных за текущий день, хранение до 10 ГБ на счётчик. Полезно для своей модели атрибуции, склейки с CRM по `ClientId`, анализа путей и поиска фрода. Источник: https://yandex.ru/dev/metrika/ru/logs/

### 3.7. Соседние API

- **GA-совместимость (Core Reporting API v3, namespace `ga:`)** — прослойка под старый Google Analytics. ⚠️ Сильно урезана и с багами — **не рекомендуется**, для Директа всегда лучше родной `ym:ad:*`.
- **admetrica** — отдельный API под медийные (охватные) кампании (досмотры, post-view). Для перформанса в поиске/РСЯ не нужен. Источник: https://yandex.ru/dev/admetrica/doc/ru/

### 3.8. Доступ и лимиты

OAuth-токен Яндекса обязателен. Reporting — до 100 000 строк на запрос; семплирование через `accuracy`. Logs — ≤1 год на запрос, нет данных за сегодня. Отдельной песочницы в документации не нашли — для теста заводят обычный тестовый счётчик. Источник: https://yandex.ru/dev/metrika/ru/intro/authorization

---

## 4. Что уже умеют наши MCP-серверы

### 4.1. Директ-MCP (`E:\AI\yandex-direct-mcp`)

Стек: Bun/TypeScript, API Директа v5. Регистрация инструментов — `src/server.ts`; HTTP — `src/client.ts`; модули — `src/tools/*.ts`.

**Реализовано (30 инструментов):** campaigns (get/add/update/delete/suspend/resume), adgroups (get/add/update/delete), ads (get/add/update/delete/suspend/resume/moderate), adimages (add/get), bidmodifiers (demographics/get), keywords (get/add/update/delete/suspend/resume), reports (campaign/ad/search_queries), dictionaries (regions/currencies/interests/all).

⚠️ **Отчёты — колонки зашиты в коде** (`src/tools/reports.ts`), изменить нельзя, только период и фильтр по `CampaignId`:
- Campaign: `CampaignName, Date, Impressions, Clicks, Cost, Ctr, AvgCpc`
- Ad: `AdId, AdGroupName, CampaignName, Impressions, Clicks, Cost, Ctr`
- Search query: `Query, CampaignName, Impressions, Clicks, Cost, Ctr`

Конверсий/целей/CPA/ROI/разрезов по устройствам/гео/площадкам — нет.

⚠️ Кампания создаётся только как `TextCampaign` со стратегией `HIGHEST_POSITION` (поиск) + `SERVING_OFF` (сети).

### 4.2. Метрика-MCP (`E:\AI\mcp-server-yandex-metrika`)

Стек: Python (FastMCP), база `https://api-metrika.yandex.net`. Гибридная модель: 3 мета-инструмента (`ym_search` / `ym_execute` / `ym_execute_file`) поверх реестра из **66 actions**, плюс 10 промотированных удобных tool.

**Промотированные (видны напрямую):** `ym_search`, `ym_execute`, `ym_execute_file`, `ym_counters`, `ym_counter`, `ym_stat_data`, `ym_stat_data_bytime`, `ym_goals`, `ym_segments`, `ym_grants`, `ym_log_requests`, `ym_labels`.

**Реестр 66 actions по доменам:** Reporting (5 форматов отчёта), Counters (6), Goals (5 — полный CRUD, все типы целей), Filters (5), Grants (4), Operations (5), Segments (5), Labels (7), Accounts (2), Delegates (3), Annotations (4), Access Filters (4), **Logs API (8 — полностью)**, **Uploads (8 — офлайн-конверсии, звонки, расходы, параметры)**.

✅ **Важно:** измерения и метрики НЕ зашиты — передаются свободной строкой. То есть любые `ym:s:*` / `ym:pv:*` / `ym:ad:*` доступны через `ym_stat_data` / `ym_execute`. Все 5 форматов отчёта работают.

### 4.3. Мелкие пробелы Метрика-MCP (не блокеры)

A/B-эксперименты; Yandex Audience (внешние сегменты); Webvisor/записи сессий; Dashboards/сводки; подписки/мониторинг сайта; удаление уже загруженных офлайн-данных; отдельного API привязки коллтрекинг-провайдера нет (только `calls_upload`).

---

## 5. Gap-анализ: дыры Директ-MCP в привязке к скиллам

| Дыра | Что именно нельзя | Какой скилл страдает | Что API Директа реально умеет |
|---|---|---|---|
| **Конверсии в отчётах** | вытащить `Conversions`, `CostPerConversion`, `GoalsRoi`, `Revenue`, разрезы по устройствам/гео/площадкам | весь аудит lifecycle | `CUSTOM_REPORT` + атрибут `Goals` + `AttributionModels` |
| **Привязка Метрики к кампании** | задать `CounterIds` и `goal_ids` кампании, включить конверсионную стратегию | `metrika-goals-setup` | `campaigns.update` (поля счётчика и стратегии) |
| **Автостратегии** | переключить на «Максимум кликов», «Оптимизацию конверсий», «Оплату за конверсию» | `bidding-strategy` | `campaigns.update` (BiddingStrategy для Search/Network) |
| **Прогноз** | получить прогноз показов/кликов/CPC по фразам | `frequency-calculator`, `bidding-strategy` | API v4: `CreateNewForecast` → `GetForecast` |
| **Расширения объявлений** | быстрые ссылки, уточнения, визитки | `usp-generator`, сборка объявлений | Sitelinks, AdExtensions, VCards |
| **Ретаргетинг/РСЯ** | условия на аудитории, списки ретаргетинга | РСЯ-кампании | AudienceTargets, RetargetingLists |
| **Changes** | спросить «что изменилось» вместо полной выгрузки | экономия лимитов баллов | Changes.check |
| **Аккаунтный минус-лист** | общий стоп-лист бренда на все кампании | `negative-keywords-builder` | NegativeKeywordSharedSets |
| **Управление ставками** | задать ставку/потолок на фразу под объём трафика | ручное ведение | KeywordBids.set / setAuto |

---

## 6. Поправки к памяти проекта

Эти моменты стоит учесть — память/ожидания расходятся с реальным API:

1. **Прогноз бюджета — это API v4 (Live 4), не v5.** Метод `CreateNewForecast` → `GetForecast`. Ссылки «Forecast.GetForecast в v5» в скиллах `frequency-calculator`/`frequency` нужно поправить.
2. **«Объём трафика» заменил «позиции»** — управляется через `KeywordBids.setAuto` (`TargetTrafficVolume` + `BidCeiling`), в отчётах это поле `AvgTrafficVolume`.
3. **Для ставок — `KeywordBids`, а не устаревающий `Bids`.**
4. **ДРР/ROI в отчётах = `GoalsRoi`/`PurchaseGoalsRoi`.** Прямых «ассоциированных конверсий» в Директе нет — только выбор модели атрибуции.
5. **Не существуют (не выдумывать):** корректировка `WEATHER`; сервисы `Forecast`/`TrafficVolume` в v5; справочники `Banks`/`ProductTypes`/`MeasurementSystems`; метод `toggle` у BidModifiers; `update` у VCards и Sitelinks; `FeatureSettings` у Clients; программное управление представителями.

---

## 7. Источники (основные URL)

**Директ:**
- Обзор API: https://yandex.ru/dev/direct/doc/ru/concepts/overview
- Отчёты: https://yandex.ru/dev/direct/doc/ru/reports · Поля: https://yandex.ru/dev/direct/doc/ru/fields-list · Связка с Метрикой: https://yandex.ru/dev/direct/doc/ru/example-metrika
- Стратегии: https://yandex.ru/dev/direct/doc/ru/annex/strategies
- Прогноз (v4): https://yandex.ru/dev/direct/doc/dg-v4/live/GetForecast.html
- Changes: https://yandex.ru/dev/direct/doc/ru/changes/changes
- Баллы: https://yandex.ru/dev/direct/doc/ru/concepts/units

**Метрика:**
- Обзор: https://yandex.ru/dev/metrika/ru/
- Отчёты: https://yandex.ru/dev/metrika/ru/stat/ · Измерения/метрики: https://yandex.ru/dev/metrika/ru/stat/attrandmetr/dim_all
- Management: https://yandex.ru/dev/metrika/ru/management/
- Загрузка данных: https://yandex.ru/dev/metrika/ru/data-import/
- Logs API: https://yandex.ru/dev/metrika/ru/logs/
- Авторизация: https://yandex.ru/dev/metrika/ru/intro/authorization
