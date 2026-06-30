# Внедрение phrase-minus в yandex-direct-audit (апгрейд Шага 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`).
> Зеркало интеграции rsya-minus (см. `2026-06-30-rsya-minus-into-audit.md`), но для Шага 3.

**Goal:** Внести движок скилла `yandex-direct-phrase-minus` (внутреннее имя `search-query-miner`) внутрь аудита как ядро Шага 3, апгрейдив уже существующий форк-субагент `search-queries`.

**Architecture:** То же, что rsya-minus: тяжёлый сбор в форк-субагенте, ядро-анализатор + словарь + ruleset централизованы в аудите, фолбек на инлайн, read-only, сводка ≤20 строк. Шаг 3 теперь даёт ДВА результата: минусацию запросов (минус-слова кампании + минус-фразы группы) и действия по ключевым фразам (ставки/статус по CPA).

**Tech Stack:** Python 3 (stdlib-only, фикс кодировки уже в источнике), Markdown, JSON.

## Global Constraints

- Язык — русский; аудитория — маркетолог.
- Read-only на всех уровнях; `allowed-tools` субагента без пишущих тулов.
- Деньги: микро→рубли по сверке `Cost` (`--money-in-rub`, если рубли). НДС-политика аудита — YES (для дедикейтед `report_search_queries` НДС зависит от обёртки).
- Атрибуция — по кампании из `01_account_map.json`; нет — `LSCCD`.
- **Репозиторий `E:\AI\yandex-direct-phrase-minus` НЕ редактируется** — только источник копирования (это git-репо, оставить нетронутым).
- Имена артефактов: `03_negative_candidates.json` (вход Шага 7) сохраняется; добавляются `minus_keywords.txt` и `03_phrase_actions.md`.
- Работа на ветке `feature/rsya-minus-into-audit` (PR #1).

Пути источника (копируем ИЗ, не меняя):
- `E:\AI\yandex-direct-phrase-minus\scripts\query_analyzer.py`
- `E:\AI\yandex-direct-phrase-minus\scripts\run_analysis.py`
- `E:\AI\yandex-direct-phrase-minus\assets\query_patterns.json`
- `E:\AI\yandex-direct-phrase-minus\references\mcp-report-mapping.md` + `how-to-apply.md`

Корень цели: `E:\AI\yandex-direct-audit\`. Скретчпад: `C:\Users\G3000\AppData\Local\Temp\claude\e--AI-yandex-direct-audit\98422b9e-b85b-453f-84fe-29177f71309f\scratchpad`.

---

### Task 1: Перенос ядра phrase-minus (+ smoke-тест)

**Files:** Create `scripts/query_analyzer.py`, `scripts/run_analysis.py`, `assets/query_patterns.json`.

**Interfaces:** `python scripts/run_analysis.py (--rows r.json | --input f.tsv) --outdir <dir> --tcpa N [--money-in-rub] [--target-geo "..."] [--competitors "..."] [--no-conversions]` → пишет `queries_candidates.json`, `minus_keywords.txt`, `phrase_actions.md`. `run_analysis` импортирует `query_analyzer` из своей папки; патёрны грузит из `<skill_root>/assets/query_patterns.json`.

- [ ] **Step 1: Скопировать 3 файла** (Copy-Item, побайтово) из источника в аудит.

- [ ] **Step 2: Создать TSV-фикстур** `<scratch>/queries_smoke.tsv` (TAB, англо-заголовки как в отчёте аудита):

```
CampaignName	AdGroupName	Criteria	Query	Impressions	Clicks	Cost	Conversions
C	G	эвакуатор межгород	эвакуатор межгород 1000 км	400	40	1200	0
C	G	эвакуатор спб	эвакуатор спб срочно	300	30	600	3
C	G	эвакуатор дешево	эвакуатор дешево скачать прайс	50	5	100	0
C	G	эвакуатор цена	эвакуатор цена бесплатно	200	20	1600	2
```

- [ ] **Step 3: Прогнать анализатор**
Run: `python scripts/run_analysis.py --input "<scratch>/queries_smoke.tsv" --outdir "<scratch>/qout" --tcpa 500 --money-in-rub`
Expected (stdout):
```
Фразы: 🔴 stop 1 · 🟠 lower 1 · 🟢 raise 1 · ⚪ hold 1 · ✅ keep 0.
Минус-слова (кампания): 2 · минус-фразы (группа): 1 · review: 0 · экономия ≈ 1300 ₽.
```
(stop=«эвакуатор межгород» 1200≥2×500; lower=«эвакуатор цена» CPA 800≥1.5×500; raise=«эвакуатор спб» CPA 200<среднего 700; hold=«эвакуатор дешево» 5 кл; минус-слова=«скачать»,«бесплатно»; группа=«эвакуатор межгород 1000 км»; экономия=100+1200.)

- [ ] **Step 4: Проверить словарь и файлы**
Run:
```
python -c "import os;assert os.path.exists(r'E:\AI\yandex-direct-audit\assets\query_patterns.json');print('patterns OK')"
python -c "import json;d=json.load(open(r'<scratch>/qout/queries_candidates.json',encoding='utf-8'));print('words',len(d['minus_words_campaign']),'group',len(d['minus_phrases_group']),'phrases_enabled',d['phrases_enabled'])"
```
Expected: `patterns OK`; `words 2 group 1 phrases_enabled True`. И `minus_keywords.txt` содержит «скачать» и «Уровень КАМПАНИИ».

- [ ] **Step 5: Commit** `feat(audit): перенос движка минусации запросов из phrase-minus`.

---

### Task 2: references/phrase-minus-rules.md

**Files:** Create `references/phrase-minus-rules.md` — свод из источника: (1) ruleset порогов (stop ≥2×CPA/0конв; lower ≥1.5×CPA; raise <среднего по кампании; hold <30 кликов/0конв; минус-фраза группы ≥25 кликов/0конв/без паттерна; словарь категорий free/info/job/used/watch/geo/competitor; режим «без конверсий» — паттерны работают, ставки и групповые минусы отключены), (2) маппинг полей `report_search_queries`→строки (из `mcp-report-mapping.md`), (3) куда вносить минусы/ставки (из `how-to-apply.md`). Заголовок-сноска: перенесено из phrase-minus.

- [ ] **Step 1:** Написать файл (свод трёх блоков).
- [ ] **Step 2: Проверить** Grep: `2× *CPA|≥25|phrase-min|без конверсий|Уровень КАМПАНИИ|Минус-фразы` присутствуют.
- [ ] **Step 3: Commit** `docs(audit): ruleset минусации запросов phrase-minus в references`.

---

### Task 3: Апгрейд субагента search-queries

**Files:** Modify `subagents/search-queries/SKILL.md`.

Переписать тело субагента на движок phrase-minus, сохранив frontmatter (`context: fork`, read-only `report_search_queries Bash Read Write Grep Glob`, `disable-model-invocation`). Аргумент-хинт расширить: `[slug] [campaign_ids] [period] [tcpa]`.

Тело:
1. Мишн + read-only (как было).
2. Вход: `$0..$3` (+ tCPA); счётчик/цели/гео/конкуренты из `_state.json`/`01_account_map.json`.
3. Методология: `references/phrase-minus-rules.md` (целиком), + queries-часть `metrika-integration.md`.
4. Шаг A: `report_search_queries({campaign_ids,date_range})` → сырьё `03_search_queries.tsv`. Сверка денег. Проверка конверсий: пусто/нет колонки → запускать с `--no-conversions` и поднять «алярму» (нет целей Метрики).
5. Шаг B: `python scripts/run_analysis.py --input direct-audits/$0/03_search_queries.tsv --outdir direct-audits/$0 --tcpa <X> [--money-in-rub] [--target-geo "..."] [--competitors "..."] [--no-conversions]`. Затем переименовать `queries_candidates.json`→`03_negative_candidates.json`, `phrase_actions.md`→`03_phrase_actions.md`; `minus_keywords.txt` оставить.
6. Шаг C: Метрика `--preset queries` как кросс-чек поведения (низкий отказ → не минусовать «слепые» групповые фразы).
7. Возврат ≤20 строк (шаблон с двумя блоками — действия по фразам + минусация):
```
СВОДКА ШАГА 3 — Поисковые запросы (slug: $0)
- Фразы: 🔴 stop X · 🟠 lower Y · 🟢 raise Z · ⚪ hold W
- Минус-слова (кампания): N · минус-фразы (группа): M · проверь вручную: K
- Экономия: ≈ <₽>
- Артефакты: 03_negative_candidates.json, minus_keywords.txt, 03_phrase_actions.md, 03_search_queries.tsv
- ⚠️ Ограничения: <без конверсий (нет целей Метрики) / Метрика без токена / мало данных>
```

- [ ] **Step 1:** Переписать тело.
- [ ] **Step 2: Проверить** Grep: frontmatter (`context: fork`,`disable-model-invocation`); `run_analysis.py|minus_keywords.txt|03_phrase_actions.md|СВОДКА ШАГА 3|no-conversions`; allowed-tools без пишущих.
- [ ] **Step 3: Commit** `feat(audit): субагент search-queries на движке phrase-minus (Шаг 3)`.

---

### Task 4: Оркестратор SKILL.md

**Files:** Modify `SKILL.md`.

- [ ] **Step 1:** В списке scripts добавить `query_analyzer.py` + `run_analysis.py` (ядро минусации запросов, Шаг 3).
- [ ] **Step 2:** Переписать тело Шага 3: вызов `/search-queries <slug> "<поисковые campaign_ids>" "<период>" "<tCPA>"`; два результата (минусация + действия по фразам); фолбек инлайн по `references/phrase-minus-rules.md` + `run_analysis.py`; артефакты `03_negative_candidates.json` + `minus_keywords.txt` + `03_phrase_actions.md`; гейт.
- [ ] **Step 3:** Карта артефактов: к Шагу 3 добавить `minus_keywords.txt` + `03_phrase_actions.md`. Раздел «Субагенты»: строку `/search-queries` обновить (движок phrase-minus, два результата).
- [ ] **Step 4: Проверить** Grep: `run_analysis.py|03_phrase_actions.md|minus_keywords.txt`; read-only цело.
- [ ] **Step 5: Commit** `feat(audit): оркестратор — Шаг 3 на движке phrase-minus`.

---

### Task 5: README

**Files:** Modify `README.md`.
- [ ] **Step 1:** Шаг 3 — два результата (минусация + действия по фразам); в дерево добавить `query_analyzer.py`, `run_analysis.py`, `query_patterns.json`, `phrase-minus-rules.md`; пометка «Шаг 3 = движок бывшего phrase-minus».
- [ ] **Step 2: Проверить** Grep `phrase-minus|run_analysis|minus_keywords|phrase_actions`.
- [ ] **Step 3: Commit** `docs(audit): README — Шаг 3 на движке phrase-minus`.

---

### Task 6: evals

**Files:** Modify `evals/evals.json`.
- [ ] **Step 1:** Кейс 1 — дополнить: «Шаг 3 даёт минус-слова кампании + минус-фразы группы (minus_keywords.txt) и действия по фразам (ставки/статус)». Можно добавить новый кейс на «минусуй поисковые запросы / что отключить по фразам». Валидный JSON.
- [ ] **Step 2: Проверить** `python -c "import json;json.load(open('evals/evals.json',encoding='utf-8'));print('ok')"` + Grep новых формулировок.
- [ ] **Step 3: Commit** `test(audit): evals под движок phrase-minus`.

---

### Task 7: Сквозная проверка

- [ ] **Step 1:** Имитировать выход Шага 3: прогнать `run_analysis.py` в `<scratch>/q-demo`, переименовать `queries_candidates.json`→`03_negative_candidates.json`, `phrase_actions.md`→`03_phrase_actions.md`; `ls` → три файла + `minus_keywords.txt`.
- [ ] **Step 2:** `cat minus_keywords.txt` → блоки «Уровень КАМПАНИИ» (скачать/бесплатно) и «Уровень ГРУППЫ».
- [ ] **Step 3:** Структура: `ls scripts/query_analyzer.py scripts/run_analysis.py assets/query_patterns.json references/phrase-minus-rules.md`.
- [ ] **Step 4:** Источник нетронут: `cd E:\AI\yandex-direct-phrase-minus; git status --short` → пусто.
- [ ] **Step 5:** Финальный commit при остатках.

## Self-Review
Покрытие: перенос ядра (T1), ruleset (T2), субагент (T3), оркестратор (T4), README (T5), evals (T6), проверка+источник (T7). Имена артефактов согласованы: `03_negative_candidates.json` сохранён для Шага 7; `minus_keywords.txt`/`03_phrase_actions.md` добавлены. Источник phrase-minus не редактируется.
