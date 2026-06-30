# Внедрение rsya-minus в yandex-direct-audit (fork-субагенты) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перестроить скилл `yandex-direct-audit` по архитектуре «оркестратор + форк-субагенты», вынеся Шаги 3/4/5 в изолированные субагенты, и внести в него логику скилла `yandex-direct-rsya-minus` как ядро Шага 4.

**Architecture:** Оркестратор (SKILL.md) держит скоуп/состояние/гейты в основном контексте; три тяжёлых шага сбора данных делегируются субагентам с `context: fork`, которые пишут артефакты на диск и возвращают наверх сводку ≤20 строк. References и scripts централизованы в аудите; субагенты читают их по пути. При недоступности форка — фолбек на инлайн.

**Tech Stack:** Markdown (SKILL.md, references, субагенты), Python 3 (анализатор `analyze_placements.py` — stdlib-only), JSON (артефакты, evals, словарь паттернов). Среда — Claude Code / Cowork, скиллы грузятся через Skill-механизм.

## Global Constraints

- **Язык:** всё общение и содержание артефактов — русский; аудитория — маркетолог, не разработчик.
- **Read-only:** ни оркестратор, ни субагенты не вызывают пишущие тулы (`*_add/update/delete/suspend/resume/moderate`, `bidmodifiers_demographics`). `allowed-tools` субагентов физически не содержат пишущих тулов; запрет продублирован прозой.
- **НДС:** считаем С НДС — `IncludeVAT: YES` во всех CUSTOM_REPORT, где это в нашем контроле.
- **Деньги:** в отчётах — рубли; конвертация микро→рубли по разовой сверке поля `Cost` (`--money-in-rub`, если обёртка отдаёт рубли).
- **Атрибуция:** модель — отдельно по каждой кампании из `01_account_map.json`; нет — `LSCCD` ↔ `cross_device_last_significant`.
- **Репозиторий `E:\AI\yandex-direct-rsya-minus` НЕ редактируется** — только источник копирования.
- **Принцип возврата субагента:** сырьё (полные TSV) остаётся в файлах; наверх — сводка ≤20 строк по фиксированному шаблону.
- **Фолбек:** форк недоступен / путь не резолвится → оркестратор выполняет шаг инлайн по тем же reference/scripts.
- **Имена артефактов Шагов 3/4/5 сохраняются** (`03_/04_/05_*`), чтобы Шаг 7 не переписывать.
- **Источник правды плана:** `docs/superpowers/specs/2026-06-30-rsya-minus-into-audit-design.md`.

Пути источника (копируем ИЗ, не меняя):
- `E:\AI\yandex-direct-rsya-minus\scripts\analyze_placements.py`
- `E:\AI\yandex-direct-rsya-minus\assets\placement_patterns.json`
- `E:\AI\yandex-direct-rsya-minus\references\minus-rules.md`
- `E:\AI\yandex-direct-rsya-minus\references\rsya-report.md`

Корень цели (всё создаём/правим ЗДЕСЬ): `E:\AI\yandex-direct-audit\`

Временная папка для smoke-тестов (не коммитится): `C:\Users\G3000\AppData\Local\Temp\claude\e--AI-yandex-direct-audit\98422b9e-b85b-453f-84fe-29177f71309f\scratchpad`

---

### Task 1: Перенос анализатора площадок + словаря паттернов (с smoke-тестом)

**Files:**
- Create: `scripts/analyze_placements.py` (копия из rsya-minus, без правок логики)
- Create: `assets/placement_patterns.json` (копия из rsya-minus, без правок)
- Test (ephemeral): `<scratchpad>/placements_smoke.tsv` + прогон в `<scratchpad>/out`

**Interfaces:**
- Produces: CLI `python scripts/analyze_placements.py --input <tsv> --outdir <dir> [--tcpa N | --tcpa-map f.json] [--money-in-rub] [--min-clicks N] [--ctr-warn N] [--ctr-fraud N] [--bounce N] [--cpa-cand N] [--cpa-strong N]` → пишет `candidates.json`, `minus_list.txt`, `report.md`; печатает строку `OK: ... 🔴 X · 🟠 Y · 🟡 Z · ✅ W · ⚪ V. Экономия ≈ N ₽.`
- Зависит от: `assets/placement_patterns.json` лежит на два уровня вверх от скрипта (`<skill_root>/assets/`). `skill_dir = dirname(dirname(abspath(__file__)))`.

- [ ] **Step 1: Скопировать анализатор и словарь в аудит**

Скопировать содержимое `E:\AI\yandex-direct-rsya-minus\scripts\analyze_placements.py` → `E:\AI\yandex-direct-audit\scripts\analyze_placements.py` (побайтово, без изменений).
Скопировать `E:\AI\yandex-direct-rsya-minus\assets\placement_patterns.json` → `E:\AI\yandex-direct-audit\assets\placement_patterns.json`.

- [ ] **Step 2: Создать синтетический фикстур-TSV для smoke-теста**

Записать в `<scratchpad>/placements_smoke.tsv` (TAB-разделители, заголовок + 5 строк):

```
CampaignName	CampaignId	AdNetworkType	Placement	Device	LocationOfPresenceName	Impressions	Clicks	Ctr	Cost	AvgCpc	Conversions	ConversionRate	CostPerConversion	Revenue	BounceRate
РСЯ-1	101	AD_NETWORK	games.example.com	MOBILE	Москва	2000	10	0.50	300	30	0	0	0	0	
РСЯ-1	101	AD_NETWORK	expensive.example.net	DESKTOP	Москва	8000	40	0.50	2500	62	0	0	0	0	
РСЯ-1	101	AD_NETWORK	candidate.example.org	DESKTOP	Санкт-Петербург	7000	35	0.50	1400	40	0	0	0	0	
РСЯ-1	101	AD_NETWORK	good.example.com	DESKTOP	Москва	8333	50	0.60	1500	30	3	6.0	500	9000	
РСЯ-1	101	AD_NETWORK	lowdata.example.com	MOBILE	Казань	800	4	0.50	200	50	0	0	0	0	
```

- [ ] **Step 3: Прогнать анализатор на фикстуре**

Run:
```
cd /e/AI/yandex-direct-audit && python scripts/analyze_placements.py \
  --input "<scratchpad>/placements_smoke.tsv" \
  --outdir "<scratchpad>/out" --tcpa 1000 --money-in-rub
```
Expected (stdout): `OK: 5 площадок. 🔴 2 · 🟠 1 · 🟡 0 · ✅ 1 · ⚪ 1. Экономия ≈ 4200 ₽.`
(🔴 = games + expensive; 🟠 = candidate; ✅ = good; ⚪ = lowdata. Экономия = 300+2500+1400 = 4200, т.к. это расход 🔴+🟠 с нулём конверсий.)

- [ ] **Step 4: Проверить, что словарь паттернов найден и применён**

Run:
```
python -c "import os; assert os.path.exists(r'E:\AI\yandex-direct-audit\assets\placement_patterns.json'), 'нет словаря'; print('patterns OK')"
grep -c "games.example.com" "<scratchpad>/out/minus_list.txt"
```
Expected: `patterns OK`, затем `1` (мусорная площадка попала в minus_list). Если `0` — анализатор не видит словарь/не сворачивает trash; разобраться до перехода дальше.

- [ ] **Step 5: Проверить структуру выходных файлов**

Run:
```
python -c "import json; d=json.load(open(r'<scratchpad>/out/candidates.json',encoding='utf-8')); ps=d['placements']; print('placements:',len(ps)); print('severities:',sorted({p['severity'] for p in ps}))"
```
Expected: `placements: 5`, `severities: ['insufficient', 'minus_candidate', 'minus_sure', 'ok']`.

- [ ] **Step 6: Commit**

```
git add scripts/analyze_placements.py assets/placement_patterns.json
git commit -m "feat(audit): перенос анализатора площадок РСЯ из rsya-minus"
```

---

### Task 2: Перенос ruleset порогов минусации в references

**Files:**
- Create: `references/rsya-minus-rules.md` (адаптированная копия `minus-rules.md`)

**Interfaces:**
- Produces: reference, который читает субагент `rsya-placements` (Task 5) и инлайн-фолбек Шага 4.

- [ ] **Step 1: Скопировать и адаптировать ruleset**

Скопировать содержимое `E:\AI\yandex-direct-rsya-minus\references\minus-rules.md` → `references/rsya-minus-rules.md`. Правки при переносе (только формулировки контекста, НЕ логику порогов):
- Заменить упоминания «Это доказательная база скилла» → «Это доказательная база Шага 4 аудита (чистка площадок РСЯ)».
- Ссылку на `scripts/analyze_placements.py` оставить как есть (скрипт теперь в аудите по тому же относительному пути).
- Ссылку на `assets/placement_patterns.json` оставить как есть.
- Добавить первой строкой после заголовка курсивную сноску: `> Перенесено из скилла rsya-minus. Исполняемая правда — scripts/analyze_placements.py; пороги настраиваются флагами.`

- [ ] **Step 2: Проверить, что ключевые пороги на месте**

Run:
```
grep -E "2 × tCPA|2 \* tcpa|min-clicks|ctr-fraud|cpa-cand|Гейт объёма|превентивно" references/rsya-minus-rules.md
```
Expected: совпадения по гейту объёма, превентивному минусу мусора и порогам (denежный сигнал, rate-сигналы, CTR-фрод, CPA-кандидат). Файл не пустой, разделы «Сигнал 1/2/3», «Итоговые категории», «Тюнинг под нишу» присутствуют.

- [ ] **Step 3: Commit**

```
git add references/rsya-minus-rules.md
git commit -m "docs(audit): ruleset минусации площадок РСЯ в references"
```

---

### Task 3: НДС=YES и сверка рецепта площадок в custom-report-recipes.md

**Files:**
- Modify: `references/custom-report-recipes.md`

**Interfaces:**
- Consumes: тело отчёта по площадкам из `E:\AI\yandex-direct-rsya-minus\references\rsya-report.md` (поля, фильтры).
- Produces: Рецепт 1 и общая форма с `IncludeVAT: YES`, полным набором полей площадок и фильтром `Impressions > 0`.

- [ ] **Step 1: Перевести политику НДС на YES**

В `references/custom-report-recipes.md`:
- В «Общей форме запроса» заменить `"IncludeVAT": "NO"` → `"IncludeVAT": "YES"`.
- В строке про заголовки заменить пояснение `returnMoneyInMicros: false (чтобы деньги сразу в рублях...)` оставить как есть (это про микро, не про НДС).
- Под блоком общей формы добавить строку: `⚠️ Считаем С НДС (IncludeVAT: YES) — это реальные деньги рекламодателя; политика единая для всего аудита, чтобы расход по площадкам/сегментам сходился с расходом по кампаниям.`

- [ ] **Step 2: Дополнить Рецепт 1 (площадки) под rsya-minus**

Заменить `FieldNames` и `Filter` Рецепта 1 на сверенный с rsya-report.md набор:

```json
{
  "FieldNames": [
    "CampaignName", "CampaignId", "AdNetworkType", "Placement",
    "Device", "LocationOfPresenceName",
    "Impressions", "Clicks", "Ctr", "Cost", "AvgCpc",
    "Conversions", "ConversionRate", "CostPerConversion",
    "Revenue", "BounceRate"
  ],
  "SelectionCriteria": {
    "Filter": [
      { "Field": "AdNetworkType", "Operator": "EQUALS", "Values": ["AD_NETWORK"] },
      { "Field": "Impressions", "Operator": "GREATER_THAN", "Values": ["0"] }
    ]
  }
}
```

Под рецептом обновить пояснения: добавить `Device` и `LocationOfPresenceName` дробят площадку на под-строки — анализатор сворачивает их обратно; `IncludeVAT: YES`; `ReportName` уникален (timestamp/slug); анализатор сам дублирует фильтр `AD_NETWORK` и `Impressions>0`.

- [ ] **Step 3: Проверить отсутствие NO и наличие новых полей**

Run:
```
grep -c '"IncludeVAT": "NO"' references/custom-report-recipes.md
grep -E "AvgCpc|LocationOfPresenceName|Impressions.*GREATER_THAN" references/custom-report-recipes.md
```
Expected: первый `0` (не осталось NO), второй — совпадения по новым полям и фильтру.

- [ ] **Step 4: Commit**

```
git add references/custom-report-recipes.md
git commit -m "docs(audit): НДС=YES и полный рецепт площадок РСЯ"
```

---

### Task 4: Ссылка на ruleset минусации в audit-thresholds.md

**Files:**
- Modify: `references/audit-thresholds.md` (раздел «Площадки РСЯ (Шаг 4)»)

- [ ] **Step 1: Добавить ссылку на полный ruleset**

В разделе «### Площадки РСЯ (Шаг 4)» после первого абзаца добавить строку:
`> Полный исполняемый ruleset порогов (гейт объёма, сигналы 1–3, словарь мусорных имён, категории 🔴/🟠/🟡/✅/⚪) — `references/rsya-minus-rules.md`; ядро — `scripts/analyze_placements.py`. Этот раздел задаёт логику флагов, ruleset — конкретные пороги.`

- [ ] **Step 2: Проверить**

Run:
```
grep -E "rsya-minus-rules.md|analyze_placements.py" references/audit-thresholds.md
```
Expected: обе ссылки присутствуют в разделе площадок.

- [ ] **Step 3: Commit**

```
git add references/audit-thresholds.md
git commit -m "docs(audit): связь раздела площадок с ruleset минусации"
```

---

### Task 5: Субагент `rsya-placements` (Шаг 4 — ядро rsya-minus)

**Files:**
- Create: `subagents/rsya-placements/SKILL.md`

**Interfaces:**
- Consumes: `_state.json` (slug, period, goal_ids, attribution, tcpa/tcpa_map), `01_account_map.json` (сетевые кампании, модели атрибуции), `references/rsya-minus-rules.md`, `references/custom-report-recipes.md` (Рецепт 1), `references/metrika-integration.md` (placements-пресет), `scripts/analyze_placements.py`, `scripts/metrika_api.py`, `assets/placement_patterns.json`.
- Produces: `direct-audits/<slug>/04_placement_candidates.md`, `04_placement_candidates.json`, `minus_list.txt`, `04_placements.tsv`; возврат-сводку для оркестратора.

- [ ] **Step 1: Создать файл субагента с точным frontmatter**

Frontmatter (verbatim):

```yaml
---
name: rsya-placements
description: Чистка площадок РСЯ Яндекс.Директа. Запускается оркестратором yandex-direct-audit как изолированный субагент на Шаге 4. Собирает CUSTOM_REPORT по площадкам РСЯ, прогоняет анализатор минусации, обогащает поведением из Метрики и возвращает в основной контекст только компактную сводку + пути к артефактам (включая готовый minus_list.txt). Сырьё (полный TSV площадок) остаётся в форке. Read-only. Вход — slug аудита, список сетевых кампаний, период, целевой CPA, цели, атрибуция.
context: fork
agent: general-purpose
allowed-tools: mcp__yandex-direct__yandex_direct_api_call mcp__yandex-direct__yandex_direct_campaigns_get mcp__yandex-direct__yandex_direct_report_campaign Bash Read Write Grep Glob
disable-model-invocation: true
argument-hint: [slug] [campaign_ids] [period] [tcpa]
---
```

- [ ] **Step 2: Написать тело субагента**

Тело (проза, по стилю субагентов marketing-strategist) должно содержать ВСЕ разделы:

1. **Мишн-строка:** «Ты — изолированный субагент Шага 4 аудита (`rsya-placements`). Тебя запустил оркестратор `yandex-direct-audit`. Истории основного разговора у тебя нет — только эта задача и аргументы. Собери сырьё по площадкам, переработай и верни наверх короткую сводку, а не простыни. Решение и заливку делает человек в основном контексте.»
2. **Read-only напоминание:** только `campaigns_get` (пробник/контекст) и `api_call` исключительно для GET-отчёта; никаких пишущих тулов; соблазн «отключить площадку» → строка в `minus_list.txt`.
3. **Вход:** `$0` slug; `$1` сетевые campaign_ids; `$2` период; `$3` tCPA. Чего нет в аргументах — взять из `direct-audits/$0/_state.json` и `01_account_map.json` (сетевые кампании, модели атрибуции, goal_ids).
4. **Методология (обязательное чтение по пути от корня скилла аудита):** `references/rsya-minus-rules.md` целиком; `references/custom-report-recipes.md` (Рецепт 1); `references/metrika-integration.md` (мост, placements-пресет). Если относительный путь не резолвится — путь от корня скилла `yandex-direct-audit`.
5. **Шаг A — отчёт:** собрать CUSTOM_REPORT по площадкам через `api_call` (поля/фильтры Рецепта 1, `AdNetworkType=AD_NETWORK`, `Impressions>0`, `IncludeVAT: YES`, цели+атрибуция из скоупа). Сохранить сырьё как `direct-audits/$0/04_placements.tsv`. Сверить поле `Cost` (рубли vs микро). ⚠️ Если `api_call` не достаёт `/json/v5/reports` — зафиксировать ограничение, собрать что можно из `report_campaign` со срезом `AdNetworkType`, не выдумывать площадки.
6. **Шаг B — анализ:** прогнать `python scripts/analyze_placements.py --input direct-audits/$0/04_placements.tsv --outdir direct-audits/$0 --tcpa <tCPA>` (или `--tcpa-map`; добавить `--money-in-rub`, если деньги в рублях). Затем **переименовать** `direct-audits/$0/candidates.json` → `04_placement_candidates.json` и `report.md` → `04_placement_candidates.md`; `minus_list.txt` оставить.
7. **Шаг C — обогащение Метрикой (опц.):** `python -m scripts.metrika_api --counter <id> --preset placements --goal <id> --attribution <модель>`; джойн по `DirectPlatform` ↔ `Placement`; положить отказ/глубину рядом с расходом. Нет токена → пометить «без поведения».
8. **Что вернуть наверх (КРИТИЧНО):** сырьё TSV НЕ выводить. Вернуть ≤20 строк по шаблону:

```
СВОДКА ШАГА 4 — Площадки РСЯ (slug: $0)
- Площадок: N. 🔴 X · 🟠 Y · 🟡 Z · ✅ W · ⚪ V
- Потенциальная экономия (🔴+🟠 без конверсий): ≈ <₽>
- Топ-кандидаты: 1) <площадка> — <расход>, <причина> 2) ... 3) ...
- Артефакты: 04_placement_candidates.{md,json}, minus_list.txt, 04_placements.tsv
- ⚠️ Ограничения: <api_call не достаёт reports / Метрика без токена / мало данных>
```
9. **Финал:** «Оркестратор покажет сводку человеку на гейте Шага 4. Главный actionable — `minus_list.txt` (заливает маркетолог сам, по кампаниям). Скилл ничего не отключает.»

- [ ] **Step 3: Проверить frontmatter и read-only**

Run:
```
grep -E "context: fork|disable-model-invocation: true|agent: general-purpose" subagents/rsya-placements/SKILL.md
grep -E "_add|_update|_delete|_suspend|_resume|_moderate|bidmodifiers_demographics" subagents/rsya-placements/SKILL.md
```
Expected: первый — три совпадения (fork, disable, agent); второй — пусто (ни одного пишущего тула в allowed-tools/тексте, кроме слова в запрете — допускается в фразе-запрете, но НЕ в allowed-tools строке). Проверить глазами: строка `allowed-tools:` не содержит пишущих тулов.

- [ ] **Step 4: Проверить наличие шаблона возврата и ссылок на reference**

Run:
```
grep -E "СВОДКА ШАГА 4|rsya-minus-rules.md|analyze_placements.py|minus_list.txt|preset placements" subagents/rsya-placements/SKILL.md
```
Expected: совпадения по всем (шаблон возврата, ruleset, скрипт, minus_list, Метрика-пресет).

- [ ] **Step 5: Commit**

```
git add subagents/rsya-placements/SKILL.md
git commit -m "feat(audit): форк-субагент rsya-placements (Шаг 4, ядро rsya-minus)"
```

---

### Task 6: Субагент `search-queries` (Шаг 3 — минусация поисковых запросов)

**Files:**
- Create: `subagents/search-queries/SKILL.md`

**Interfaces:**
- Consumes: `_state.json`, `01_account_map.json` (поисковые кампании), `references/audit-thresholds.md` (раздел «Поисковые запросы → минусация»), `references/optimization-playbook.md` (ПОИСК → Минусовка), `references/metrika-integration.md` (queries-пресет), `scripts/normalize_report.py`, `scripts/metrika_api.py`.
- Produces: `direct-audits/<slug>/03_negative_candidates.md`, `03_negative_candidates.json`, `03_search_queries.tsv`; возврат-сводку.

- [ ] **Step 1: Создать файл субагента с точным frontmatter**

```yaml
---
name: search-queries
description: Майнинг поисковых запросов Яндекс.Директа под минусацию. Запускается оркестратором yandex-direct-audit как изолированный субагент на Шаге 3. Тянет огромный отчёт по поисковым запросам, нормализует, ищет кандидатов в минус-слова (расход без конверсий / высокий отказ), обогащает поведением из Метрики, группирует по темам и возвращает наверх только сводку + пути к артефактам. Сырьё (полный TSV запросов) остаётся в форке. Read-only. Вход — slug аудита, список поисковых кампаний, период.
context: fork
agent: general-purpose
allowed-tools: mcp__yandex-direct__yandex_direct_report_search_queries Bash Read Write Grep Glob
disable-model-invocation: true
argument-hint: [slug] [campaign_ids] [period]
---
```

- [ ] **Step 2: Написать тело субагента**

Разделы (по тому же каркасу, что Task 5):
1. Мишн-строка (изолированный субагент Шага 3, истории нет, верни сводку).
2. Read-only напоминание (только `report_search_queries`; кандидаты — рекомендации, не правки).
3. Вход: `$0` slug, `$1` поисковые campaign_ids (Поиск + поисковая часть ЕПК), `$2` период; чего нет — из `_state.json` / `01_account_map.json`.
4. Методология (читать по пути от корня скилла): раздел «Поисковые запросы → минусация» в `references/audit-thresholds.md`; «ПОИСК → Минусовка» в `references/optimization-playbook.md`; queries-часть `references/metrika-integration.md`.
5. Шаг A: `report_search_queries({campaign_ids, date_range})` → сохранить сырьё `direct-audits/$0/03_search_queries.tsv`. Сверить `Cost` (рубли/микро).
6. Шаг B: `python -m scripts.normalize_report --input direct-audits/$0/03_search_queries.tsv --kpi-cpa <X>` (+ `--money-in-rub` при рублях). Кандидаты — расход + 0 конверсий и/или высокий отказ. ⚠️ НЕ предлагать минус для запросов с <5 переходов. Сгруппировать по повторяющимся словам/темам (бесплатно/скачать/своими руками, инфо вместо коммерции, нецелевые конкуренты/гео). Сверить с `NegativeKeywords` из `01_account_map.json` — не дублировать.
7. Шаг C (опц.): `python -m scripts.metrika_api --counter <id> --preset queries --goal <id> --attribution <модель>`; джойн `DirectPhraseOrCond` ↔ запрос; низкий отказ + хорошая глубина → НЕ в минус (доработка посадочной), высокий отказ → уверенный кандидат.
8. Артефакты: `03_negative_candidates.md` (сгруппированные кандидаты: слово/тема + расход + отказ + причина) + `03_negative_candidates.json`.
9. Возврат ≤20 строк:

```
СВОДКА ШАГА 3 — Поисковые запросы (slug: $0)
- Запросов проанализировано: N; кандидатов в минус: M
- Топ-темы групп: 1) <тема> (<расход>) 2) ... 3) ...
- Потенциальная экономия: ≈ <₽>
- Артефакты: 03_negative_candidates.{md,json}, 03_search_queries.tsv
- ⚠️ Ограничения: <Метрика без токена / мало данных по части запросов>
```
10. Финал: «Это рекомендации, не правки. Оркестратор покажет сводку на гейте Шага 3.»

- [ ] **Step 3: Проверить frontmatter, read-only, шаблон**

Run:
```
grep -E "context: fork|disable-model-invocation: true" subagents/search-queries/SKILL.md
grep -E "СВОДКА ШАГА 3|normalize_report|preset queries|<5 переход|5 переход" subagents/search-queries/SKILL.md
grep -E "allowed-tools:.*(_add|_update|_delete|_suspend)" subagents/search-queries/SKILL.md
```
Expected: первый — 2 совпадения; второй — совпадения по шаблону/скрипту/Метрике/порогу 5 переходов; третий — пусто (нет пишущих тулов в allowed-tools).

- [ ] **Step 4: Commit**

```
git add subagents/search-queries/SKILL.md
git commit -m "feat(audit): форк-субагент search-queries (Шаг 3)"
```

---

### Task 7: Субагент `bid-segments` (Шаг 5 — корректировки ставок)

**Files:**
- Create: `subagents/bid-segments/SKILL.md`

**Interfaces:**
- Consumes: `_state.json`, `01_account_map.json`, `references/audit-thresholds.md` (Корректировки ставок), `references/optimization-playbook.md` (ОБЩЕЕ → Корректировки), `references/custom-report-recipes.md` (Рецепты 2–6), `references/metrika-integration.md` (segments-пресет), `scripts/normalize_report.py`, `scripts/metrika_api.py`.
- Produces: `direct-audits/<slug>/05_bid_modifier_opportunities.md`, `05_bid_modifier_opportunities.json`, срезы `05_segment_*.tsv`, `_regions_cache.json` (при гео); возврат-сводку.

- [ ] **Step 1: Создать файл субагента с точным frontmatter**

```yaml
---
name: bid-segments
description: Поиск точек роста через корректировки ставок Яндекс.Директа (устройство/пол-возраст/гео/час). Запускается оркестратором yandex-direct-audit как изолированный субагент на Шаге 5. Тянет текущие корректировки и сегментные срезы CUSTOM_REPORT, нормализует, ищет недо/переэффективные сегменты, обогащает поведением из Метрики и возвращает наверх только сводку с конкретными % как гипотезами. Сырьё остаётся в форке. Read-only. Вход — slug аудита, список кампаний, период, KPI.
context: fork
agent: general-purpose
allowed-tools: mcp__yandex-direct__yandex_direct_api_call mcp__yandex-direct__yandex_direct_bidmodifiers_get mcp__yandex-direct__yandex_direct_dictionaries_regions Bash Read Write Grep Glob
disable-model-invocation: true
argument-hint: [slug] [campaign_ids] [period] [kpi]
---
```

- [ ] **Step 2: Написать тело субагента**

Разделы:
1. Мишн-строка (изолированный субагент Шага 5).
2. Read-only напоминание (только `bidmodifiers_get`, `api_call` для отчётов, `dictionaries_regions`; НЕ `bidmodifiers_demographics` — это запись; корректировки — рекомендации).
3. Вход: `$0` slug, `$1` campaign_ids, `$2` период, `$3` KPI (tCPA/ДРР); counter_id/goal_ids из `_state.json`.
4. Методология (читать по пути): «Корректировки ставок» в `references/audit-thresholds.md`; «ОБЩЕЕ → Корректировки ставок» в `references/optimization-playbook.md`; Рецепты 2–6 в `references/custom-report-recipes.md`; segments-часть `references/metrika-integration.md`.
5. Шаг A: текущие — `bidmodifiers_get({campaign_ids})`. Срезы через `api_call` CUSTOM_REPORT (Рецепты 2–5): Device; Gender+Age; LocationOfPresenceName; HourOfDay. `IncludeVAT: YES`. Сохранить сырьё `05_segment_device.tsv` и т.д. Фолбек при недоступном `api_call` — зафиксировать ограничение.
6. Шаг B: `normalize_report.py` по каждому срезу. Сегмент много тратит + CPA выше KPI / 0 конверсий → минус-корректировка; перевыполняет → плюс. <~10 конверсий → «гипотеза, накопить». Сверить с уже выставленными (`bidmodifiers_get`) — не дублировать. Для гео — расшифровка `region_id` через `dictionaries_regions` (кэш `direct-audits/$0/_regions_cache.json`, не читать целиком, грепать по имени — Рецепт 6).
7. Шаг C (опц.): `metrika_api.py --preset segments --segment device|gender|age|geo --goal <id> --attribution <модель>` — поведение сегмента усиливает гипотезу %.
8. Артефакты: `05_bid_modifier_opportunities.md` + `05_bid_modifier_opportunities.json` (по каждому сегменту: расход, конверсии, CPA, рекомендуемый %, объём-пометка).
9. Возврат ≤20 строк:

```
СВОДКА ШАГА 5 — Корректировки ставок (slug: $0)
- Сегментов с рекомендацией: минус N / плюс M
- Топ: 1) <сегмент> CPA <₽> → <−/+X%> 2) ... 3) ...
- Где данных мало (гипотезы): <список>
- Артефакты: 05_bid_modifier_opportunities.{md,json}, 05_segment_*.tsv
- ⚠️ Ограничения: <api_call не достаёт reports / Метрика без токена>
```
10. Финал: «% — стартовые гипотезы, не истина. Оркестратор покажет сводку на гейте Шага 5.»

- [ ] **Step 3: Проверить**

Run:
```
grep -E "context: fork|disable-model-invocation: true" subagents/bid-segments/SKILL.md
grep -E "СВОДКА ШАГА 5|bidmodifiers_get|preset segments|dictionaries_regions" subagents/bid-segments/SKILL.md
grep -E "allowed-tools:.*bidmodifiers_demographics" subagents/bid-segments/SKILL.md
```
Expected: первый — 2 совпадения; второй — совпадения по шаблону/тулам/Метрике; третий — пусто (нет пишущего `bidmodifiers_demographics` в allowed-tools).

- [ ] **Step 4: Commit**

```
git add subagents/bid-segments/SKILL.md
git commit -m "feat(audit): форк-субагент bid-segments (Шаг 5)"
```

---

### Task 8: Перестроить оркестратор (SKILL.md)

**Files:**
- Modify: `SKILL.md` (раздел архитектуры, Шаги 3/4/5, карта артефактов, стиль, НДС)

**Interfaces:**
- Consumes: имена субагентов `search-queries` / `rsya-placements` / `bid-segments` (Tasks 5-7).
- Produces: оркестратор, который делегирует Шаги 3/4/5 и держит гейты в основном контексте.

- [ ] **Step 1: Добавить раздел «Архитектура: оркестратор + субагенты»**

После блока «## Как использовать scripts» (перед `# Workflow: 7 шагов`) вставить раздел с таблицей делегирования:

```markdown
## Архитектура: оркестратор + субагенты

Скилл работает как **оркестратор** в основном контексте: держит скоуп, `_state.json`, гейты и сборку финального отчёта. **Три тяжёлых шага сбора данных вынесены в изолированные субагенты** (`context: fork`) — чтобы гигантские TSV-отчёты не засоряли основной контекст к моменту сборки отчёта (Шаг 7).

| Шаг | Где исполняется | Почему |
|---|---|---|
| 0–2 (скоуп, инвентаризация, статистика кампаний) | **Инлайн** | Решения и гейты; Шаг 2 ведёт ключевой гейт |
| 3 — поисковые запросы | **Субагент** `/search-queries` | Огромный TSV всех запросов |
| 4 — площадки РСЯ | **Субагент** `/rsya-placements` | Тяжёлый отчёт по площадкам + ядро минусации |
| 5 — корректировки ставок | **Субагент** `/bid-segments` | Несколько сегментных срезов |
| 6–7 (объявления, сборка отчёта) | **Инлайн** | Анализ и синтез |

**Принцип возврата:** субагент собирает сырьё в своём контексте, пишет артефакты на диск и возвращает наверх **только сводку ≤20 строк**. Гейт и решение — у человека в основном контексте.

**Фолбек:** если субагенты недоступны (старая среда, ошибка форка, путь не резолвится) — оркестратор выполняет эти шаги **инлайн** по тем же reference/scripts. Делегирование — оптимизация, не жёсткая зависимость.

Субагенты лежат в `subagents/`, помечены `disable-model-invocation: true` (не запускаются сами) и read-only набором тулов. References и scripts — единые, в корне скилла; субагенты читают их по пути.
```

- [ ] **Step 2: Переписать Шаг 3 на делегирование**

Заменить тело «## Шаг 3. Майнинг поисковых запросов (минусация)» так, чтобы:
- Вызов субагента: `/search-queries <slug> "<поисковые campaign_ids>" "<период>"`.
- Сохранить требование читать reference (теперь это делает субагент; оркестратор лишь готовит вход — список поисковых кампаний из `01_account_map.json`).
- Добавить строку фолбека: «Субагент недоступен → выполни Шаг 3 инлайн по `references/audit-thresholds.md` (раздел поисковых запросов) и `optimization-playbook.md`.»
- Сохранить артефакты `03_negative_candidates.{md,json}` и `[GATE: маркетолог]` со сводкой субагента.

- [ ] **Step 3: Переписать Шаг 4 на делегирование (ядро rsya-minus)**

Заменить тело «## Шаг 4. Чистка площадок РСЯ»:
- Вызов: `/rsya-placements <slug> "<сетевые campaign_ids>" "<период>" "<tCPA>"`.
- Указать, что субагент даёт `04_placement_candidates.{md,json}` **и** готовый `minus_list.txt` (главный actionable, заливает маркетолог по кампаниям).
- Фолбек инлайн: по `references/rsya-minus-rules.md` + `scripts/analyze_placements.py` + Рецепт 1.
- Гейт: показать сводку субагента (🔴/🟠 счётчики + экономия + топ-кандидаты).

- [ ] **Step 4: Переписать Шаг 5 на делегирование**

Заменить тело «## Шаг 5. Корректировки ставок (точки роста)»:
- Вызов: `/bid-segments <slug> "<campaign_ids>" "<период>" "<KPI>"`.
- Фолбек инлайн: по `references/audit-thresholds.md` (Корректировки) + Рецепты 2–6 + `optimization-playbook.md`.
- Сохранить артефакты `05_bid_modifier_opportunities.{md,json}` и пометку про объём (<10 конверсий = гипотеза).

- [ ] **Step 5: Обновить НДС, карту артефактов и стиль**

- В Шаге 2 и в разделе «Стиль работы»: заменить «конвертируй из микро» оставить, но добавить «расход показываем **с НДС**».
- В «Главном принципе» / «Стиль работы» добавить строку про субагентов: «Шаги 3/4/5 исполняются изолированными субагентами; наверх — сводка, сырьё в файлах».
- В «# Карта артефактов» пометить, какие шаги исполняются субагентами (3/4/5), и что Шаг 4 дополнительно даёт `minus_list.txt`.
- В разделе «## Субагенты» (новый, в конце, по образцу marketing-strategist) — таблица трёх субагентов: имя, шаг, что делает, что возвращает; пометка `context: fork`, `disable-model-invocation: true`, фолбек.

- [ ] **Step 6: Проверить целостность SKILL.md**

Run:
```
grep -E "/search-queries|/rsya-placements|/bid-segments" SKILL.md
grep -E "Архитектура: оркестратор|Фолбек|с НДС|minus_list.txt" SKILL.md
grep -E "context: fork|disable-model-invocation" SKILL.md
```
Expected: все три вызова субагентов присутствуют; раздел архитектуры, фолбек, НДС, minus_list упомянуты; субагенты описаны.

- [ ] **Step 7: Проверить, что read-only формулировка цела**

Run:
```
grep -E "read-only|только чтение|не вызывает пишущ|строка-рекомендация" SKILL.md
```
Expected: разделы про read-only сохранены (Шаги 3/4/5 переписаны, но дисциплина не потеряна).

- [ ] **Step 8: Commit**

```
git add SKILL.md
git commit -m "feat(audit): оркестратор — делегирование Шагов 3/4/5 субагентам + НДС"
```

---

### Task 9: README пакета

**Files:**
- Create: `README.md`

- [ ] **Step 1: Написать README по образцу marketing-strategist**

Содержание: что делает скилл (read-only аудит, 7 шагов); архитектура «оркестратор + субагенты» (3 субагента, fork, фолбек); таблица навигации (`SKILL.md`, `subagents/`, `references/`, `scripts/`, `assets/`, `evals/`); дерево структуры (как в спеке §4); имена артефактов; пометка «read-only, решение за маркетологом»; пометка про НДС (с НДС); что Шаг 4 несёт логику бывшего rsya-minus.

- [ ] **Step 2: Проверить**

Run:
```
grep -E "оркестратор|субагент|read-only|rsya|minus_list" README.md
```
Expected: совпадения по архитектуре, read-only, происхождению Шага 4.

- [ ] **Step 3: Commit**

```
git add README.md
git commit -m "docs(audit): README пакета с архитектурой субагентов"
```

---

### Task 10: Обновить evals

**Files:**
- Modify: `evals/evals.json`

- [ ] **Step 1: Дополнить ожидания существующих кейсов и добавить проверки субагентов**

К кейсу 2 (РСЯ-площадки) добавить в `expectations`:
- `"Шаг 4 исполняется изолированным субагентом rsya-placements (context: fork); наверх возвращается сводка, сырьё TSV не вываливается в чат"`
- `"Отдаёт готовый minus_list.txt по кампаниям (🔴 минус точно + 🟠 кандидаты)"`
- `"Применяет анализатор площадок (пороги от целевого CPA, словарь мусорных имён, гейт объёма)"`

К кейсу 1 (общий аудит) добавить:
- `"Шаги 3, 4, 5 делегируются форк-субагентам; при недоступности форка выполняются инлайн по тем же reference"`
- `"Расход показывается с НДС"`

К кейсу 3 (CTR/корректировки) добавить:
- `"Шаг 5 исполняется субагентом bid-segments; корректировки — гипотезы с пометкой объёма"`

- [ ] **Step 2: Проверить валидность JSON**

Run:
```
python -c "import json; d=json.load(open(r'evals/evals.json',encoding='utf-8')); print('evals:',len(d['evals'])); print('ok json')"
grep -E "rsya-placements|minus_list|форк-субаген|с НДС|bid-segments" evals/evals.json
```
Expected: `evals: 4`, `ok json`; grep — совпадения по новым ожиданиям.

- [ ] **Step 3: Commit**

```
git add evals/evals.json
git commit -m "test(audit): evals под субагентов и minus_list"
```

---

### Task 11: Сквозная проверка интеграции

**Files:**
- Verify only (без новых файлов в репозитории; временные — в scratchpad)

- [ ] **Step 1: Сымитировать выход Шага 4 в папке аудита**

Создать `<scratchpad>/audit-demo/` и прогнать анализатор как это сделает субагент:
```
mkdir -p "<scratchpad>/audit-demo" && python scripts/analyze_placements.py \
  --input "<scratchpad>/placements_smoke.tsv" \
  --outdir "<scratchpad>/audit-demo" --tcpa 1000 --money-in-rub
```
Затем переименовать как делает субагент:
```
cd "<scratchpad>/audit-demo" && mv candidates.json 04_placement_candidates.json && mv report.md 04_placement_candidates.md && ls
```
Expected (ls): `04_placement_candidates.json  04_placement_candidates.md  minus_list.txt`.

- [ ] **Step 2: Проверить, что minus_list пригоден для поля ready_to_use**

Run:
```
cat "<scratchpad>/audit-demo/minus_list.txt"
```
Expected: блок `=== РСЯ-1 ===` с `🔴 минусовать точно:` (games.example.com, expensive.example.net) и `🟠 кандидаты:` (candidate.example.org).

- [ ] **Step 3: Проверить, что финальный рендер отчёта по-прежнему собирается**

Прогнать существующий рендер на демо-находках репозитория (Шаг 7 не менялся, но проверяем регрессию):
```
cd /e/AI/yandex-direct-audit && python -m scripts.render_report --input direct-audits/_demo/findings.json --output "<scratchpad>/audit-demo/АУДИТ_demo.pdf"
```
Expected: создан PDF или (если браузер не найден) рядом `.html`; скрипт завершился без трейсбэка. Если печать в PDF недоступна в среде — достаточно, что HTML собран без ошибки.

- [ ] **Step 4: Проверить полноту структуры скилла**

Run:
```
cd /e/AI/yandex-direct-audit && ls subagents/*/SKILL.md scripts/analyze_placements.py assets/placement_patterns.json references/rsya-minus-rules.md README.md
```
Expected: все шесть путей существуют (3 субагента + анализатор + словарь + ruleset + README).

- [ ] **Step 5: Проверить, что репозиторий rsya-minus не тронут**

Run:
```
cd /e/AI/yandex-direct-rsya-minus && git status --short
```
Expected: пусто (никаких изменений — источник остался неизменным).

- [ ] **Step 6: Финальный commit (если остались несохранённые изменения плана/доков)**

```
cd /e/AI/yandex-direct-audit && git add -A && git status
git commit -m "chore(audit): завершение интеграции rsya-minus в субагенты" || echo "нечего коммитить"
```

---

## Self-Review (выполнено автором плана)

**1. Покрытие спеки:** §4 структура → Tasks 1–10; §5.1 search-queries → Task 6; §5.2 rsya-placements → Task 5; §5.3 bid-segments → Task 7; §6 перенос файлов → Tasks 1–2 + §7; §7 НДС → Task 3 (+ Task 8 формулировки); §8 карта артефактов/Шаг 7 → Tasks 8, 11; §9 read-only → встроено в Tasks 5–8 (проверки grep); §10 evals → Task 10; §11 rsya-minus не трогаем → Task 11 Step 5; §12 проверки → Tasks 1, 5, 11. Пробелов нет.

**2. Плейсхолдеры:** в плане нет TBD/«добавить обработку ошибок» без кода — все шаги несут конкретные команды/контент. Тела субагентов заданы пораздельно с точным frontmatter (verbatim) и verbatim-шаблоном возврата.

**3. Согласованность имён:** артефакты `03_/04_/05_*` едины между субагентами (Tasks 5–7), оркестратором (Task 8) и Шагом 7 (Task 11). Имена субагентов `search-queries` / `rsya-placements` / `bid-segments` согласованы между frontmatter, вызовами в SKILL.md и evals. Переименование `candidates.json`→`04_placement_candidates.json` и `report.md`→`04_placement_candidates.md` согласовано в Task 5 Step 2.6 и Task 11 Step 1.
