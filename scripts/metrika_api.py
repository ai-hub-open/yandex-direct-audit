#!/usr/bin/env python3
"""
metrika_api.py — read-only доступ к Yandex Metrika API для аудита Директа.

Зачем: Direct-only MCP не даёт поведенческой глубины (отказы/глубина по площадке,
поведение поисковых запросов и сегментов, реальные конверсии по моделям атрибуции).
Этот скрипт тянет данные Метрики и кладёт их РОВНО на сущности Директа через
Direct-срезы (ym:s:<attr>DirectClickOrder = кампания, ...DirectPlatform = площадка
и т.д.), чтобы выводы аудита были точными.

Только чтение: бьёт в Reporting API (stat/v1/data) и Management (список целей).
Ничего не меняет.

Авторизация: OAuth-токен в переменной окружения. Скрипт ищет по очереди
YANDEX_METRIKA_TOKEN, затем YANDEX_DIRECT_TOKEN (если токен один на оба сервиса).
Скоуп токена должен включать metrika:read.

Использование:
  # список целей счётчика
  python -m scripts.metrika_api --counter 12345678 --preset goals

  # поведение по площадкам РСЯ Директа (отказы/глубина/время)
  python -m scripts.metrika_api --counter 12345678 --preset placements \
      --date1 2025-05-01 --date2 2025-05-31 --attribution lastsign

  # поведение поисковых запросов/условий Директа
  python -m scripts.metrika_api --counter 12345678 --preset queries

  # сравнение конверсий по моделям атрибуции на уровне кампаний
  python -m scripts.metrika_api --counter 12345678 --preset attribution \
      --goal 9876543

  # поведение по сегментам (устройство/гео/пол-возраст) только по Direct-трафику
  python -m scripts.metrika_api --counter 12345678 --preset segments --segment device

  # произвольный запрос
  python -m scripts.metrika_api --counter 12345678 \
      --metrics "ym:s:visits,ym:s:bounceRate,ym:s:pageDepth" \
      --dimensions "ym:s:lastsignDirectClickOrderName" \
      --filters "ym:s:lastsignTrafficSource=='ad'"

  # посмотреть, какой запрос уйдёт, без вызова API
  python -m scripts.metrika_api --counter 12345678 --preset placements --dry-run

Важно про атрибуцию: модель берётся ОТДЕЛЬНО для каждой кампании Директа; если
в кампании не задана (или API её не отдаёт) — используется LSCCD ('cross_device_
last_significant', последний значимый переход с кросс-девайсом).
Direct и Метрика называют одни и те же модели по-разному — соответствие зашито
в ATTRIBUTION_MODELS (это единый источник правды), поэтому --attribution принимает
И Direct-коды (FC/LC/LSC/LYDC/FCCD/LCCD/LSCCD/LYDCCD/AUTO), И имена Метрики
(first/last/lastsign/...). Фиксируй одну модель на весь срез и указывай её рядом
с числами. Вывести карту моделей: python -m scripts.metrika_api --show-attribution-map.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"
GOALS_URL = "https://api-metrika.yandex.net/management/v1/counter/{counter}/goals"

# Прокси для регионов с сетевыми ограничениями (опционально).
# Если задана переменная HTTPS_PROXY/HTTP_PROXY — urllib подхватит сам.

# ─────────────────────────────────────────────────────────────────────────────
# ЕДИНЫЙ СЛОВАРЬ АТРИБУЦИИ — источник правды для сопоставления Direct ↔ Метрика.
# Одна и та же модель называется по-разному в двух системах; здесь она сведена.
#   ключ      — код модели в Direct (Reports API, параметр AttributionModels)
#   "metrika" — имя модели в Метрике (параметр attribution И префикс среза ym:s:)
#   "ru"      — человекочитаемое имя
# Правило выбора: бери модель ОТДЕЛЬНО для каждой кампании Директа;
# если в кампании не задана — LSCCD (последний значимый переход, кросс-девайс).
ATTRIBUTION_MODELS = {
    "FC":     {"metrika": "first",                                 "ru": "Первый переход"},
    "LC":     {"metrika": "last",                                  "ru": "Последний переход"},
    "LSC":    {"metrika": "lastsign",                              "ru": "Последний значимый переход"},
    "LYDC":   {"metrika": "last_yandex_direct_click",              "ru": "Последний переход из Яндекс Директа"},
    "FCCD":   {"metrika": "cross_device_first",                    "ru": "Первый переход (кросс-девайс)"},
    "LCCD":   {"metrika": "cross_device_last",                     "ru": "Последний переход (кросс-девайс)"},
    "LSCCD":  {"metrika": "cross_device_last_significant",         "ru": "Последний значимый переход (кросс-девайс)"},
    "LYDCCD": {"metrika": "cross_device_last_yandex_direct_click", "ru": "Последний переход из Директа (кросс-девайс)"},
    "AUTO":   {"metrika": "automatic",                             "ru": "Автоматическая атрибуция"},
}

# Любое написание (Direct-код / имя Метрики / старый алиас CLI) → канонический Direct-код.
_ALIAS_TO_CODE: Dict[str, str] = {}
for _code, _m in ATTRIBUTION_MODELS.items():
    _ALIAS_TO_CODE[_code.lower()] = _code
    _ALIAS_TO_CODE[_m["metrika"].lower()] = _code
_ALIAS_TO_CODE.update({                 # обратная совместимость со старым CLI
    "last_direct": "LYDC",
    "cross_last_sign": "LSCCD",
    "auto": "AUTO",
})


def resolve_code(value: str) -> str:
    """Любое написание модели → канонический Direct-код."""
    code = _ALIAS_TO_CODE.get((value or "").strip().lower())
    if not code:
        sys.exit(f"Неизвестная модель атрибуции: {value!r}. Допустимо: "
                 f"Direct-коды {list(ATTRIBUTION_MODELS)} или имена Метрики "
                 f"{[m['metrika'] for m in ATTRIBUTION_MODELS.values()]}.")
    return code


def attr_metrika(value: str) -> str:
    """Любое написание модели → имя для Метрики (параметр attribution и префикс среза)."""
    return ATTRIBUTION_MODELS[resolve_code(value)]["metrika"]


def attribution_map_json() -> str:
    rows = [{"direct": code, "metrika": m["metrika"], "ru": m["ru"]}
            for code, m in ATTRIBUTION_MODELS.items()]
    return json.dumps({
        "rule": "Бери модель ОТДЕЛЬНО для каждой кампании Директа; "
                "если в кампании не задана — LSCCD (последний значимый переход, кросс-девайс).",
        "default": "LSCCD",
        "attribution_models": rows,
    }, ensure_ascii=False, indent=2)


def get_token() -> str:
    for var in ("YANDEX_METRIKA_TOKEN", "YANDEX_DIRECT_TOKEN"):
        tok = os.environ.get(var)
        if tok:
            return tok
    sys.exit("Не задан OAuth-токен. Установи YANDEX_METRIKA_TOKEN "
             "(или YANDEX_DIRECT_TOKEN, если токен общий) со скоупом metrika:read.")


def build_preset(preset: str, attribution: str, goal: Optional[str],
                 segment: Optional[str]) -> Dict[str, str]:
    """Возвращает {metrics, dimensions, filters} для пресета."""
    a = attr_metrika(attribution)
    behavioral = "ym:s:visits,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds"
    goal_metrics = (f",ym:s:goal{goal}reaches,ym:s:goal{goal}conversionRate"
                    if goal else ",ym:s:sumGoalReachesAny")
    direct_only = f"ym:s:{a}TrafficSource=='ad'"

    if preset == "goals":
        return {"_management": "goals"}

    if preset == "placements":
        # Поведение по площадкам Директа (аналог отчёта «Директ, площадки»).
        return {
            "metrics": behavioral + goal_metrics,
            "dimensions": f"ym:s:{a}DirectPlatform",
            "filters": f"{direct_only} AND ym:s:{a}DirectPlatformType=='context'",
        }

    if preset == "queries":
        # Поведение по условиям показа/фразам Директа.
        return {
            "metrics": behavioral + goal_metrics,
            "dimensions": f"ym:s:{a}DirectPhraseOrCond",
            "filters": direct_only,
        }

    if preset == "attribution":
        # Конверсии по кампаниям Директа (сравнение моделей делается запуском
        # скрипта с разными --attribution и сопоставлением).
        return {
            "metrics": f"ym:s:visits{goal_metrics}",
            "dimensions": f"ym:s:{a}DirectClickOrderName",
            "filters": direct_only,
        }

    if preset == "segments":
        seg_map = {
            "device": "ym:s:deviceCategory",
            "gender": "ym:s:gender",
            "age": "ym:s:ageInterval",
            "geo": "ym:s:regionCity",
        }
        dim = seg_map.get(segment or "device", "ym:s:deviceCategory")
        return {
            "metrics": behavioral + goal_metrics,
            "dimensions": dim,
            "filters": direct_only,
        }

    sys.exit(f"Неизвестный пресет: {preset}")


def http_get(url: str, token: str, timeout: int = 60) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 429 or e.code == 420:
            raise SystemExit(f"Лимит запросов Метрики (HTTP {e.code}). "
                             f"Подожди и повтори. Тело: {body[:300]}")
        raise SystemExit(f"Metrika API HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Сеть недоступна: {e}. "
                         f"Если регион под ограничениями — задай HTTPS_PROXY.")


def fetch_goals(counter: str, token: str) -> Dict[str, Any]:
    url = GOALS_URL.format(counter=counter)
    data = http_get(url, token)
    goals = [{"id": g.get("id"), "name": g.get("name"), "type": g.get("type")}
             for g in data.get("goals", [])]
    return {"counter": counter, "goals": goals}


def fetch_stat(counter: str, token: str, metrics: str, dimensions: str,
               filters: Optional[str], attribution: str, date1: str,
               date2: str, limit: int, dry_run: bool) -> Dict[str, Any]:
    params = {
        "ids": counter,
        "metrics": metrics,
        "dimensions": dimensions,
        "date1": date1,
        "date2": date2,
        "accuracy": "full",
        "limit": str(limit),
        # Метрика принимает в параметре attribution: first|last|lastsign|
        # last_yandex_direct_click|cross_device_last_significant|automatic и т.д.
        # Берём ту же модель, что и в срезе, чтобы метрики целей считались
        # согласованно с измерением. attr_metrika принимает и Direct-коды.
        "attribution": attr_metrika(attribution),
    }
    if filters:
        params["filters"] = filters
    url = STAT_URL + "?" + urllib.parse.urlencode(params)

    if dry_run:
        return {"dry_run": True, "url": url, "params": params}

    raw = http_get(url, token)
    # Нормализуем data → список строк {dimensions:[...], metrics:[...]}.
    rows = []
    for item in raw.get("data", []):
        dims = [d.get("name") for d in item.get("dimensions", [])]
        rows.append({"dimensions": dims, "metrics": item.get("metrics", [])})
    return {
        "query": {
            "metrics": metrics,
            "dimensions": dimensions,
            "filters": filters,
            "attribution_metrika": params["attribution"],
            "attribution_direct": resolve_code(attribution),
            "period": f"{date1}..{date2}",
        },
        "total_rows": raw.get("total_rows"),
        "metric_names": metrics.split(","),
        "dimension_names": dimensions.split(","),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only доступ к Yandex Metrika API")
    ap.add_argument("--counter", help="ID счётчика Метрики (не нужен для --show-attribution-map)")
    ap.add_argument("--preset", choices=["goals", "placements", "queries",
                                         "attribution", "segments"],
                    help="готовый сценарий аудита")
    ap.add_argument("--segment", choices=["device", "gender", "age", "geo"],
                    help="для preset=segments")
    ap.add_argument("--goal", help="goal_id для конверсионных метрик")
    ap.add_argument("--attribution", default="LSCCD",
                    help="модель атрибуции: Direct-код (FC/LC/LSC/LYDC/FCCD/LCCD/"
                         "LSCCD/LYDCCD/AUTO) или имя Метрики (first/last/lastsign/"
                         "automatic/...). Дефолт LSCCD (последний значимый, "
                         "кросс-девайс) — если в кампании модель не задана.")
    ap.add_argument("--show-attribution-map", action="store_true",
                    help="вывести единую карту моделей атрибуции Direct↔Метрика и выйти")
    ap.add_argument("--metrics", help="произвольные метрики ym:s:... через запятую")
    ap.add_argument("--dimensions", help="произвольные измерения ym:s:...")
    ap.add_argument("--filters", help="произвольный фильтр Метрики")
    ap.add_argument("--date1", default="30daysAgo")
    ap.add_argument("--date2", default="yesterday")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true",
                    help="показать запрос, не вызывая API")
    ap.add_argument("--out", help="куда писать JSON (иначе stdout)")
    args = ap.parse_args()

    if args.show_attribution_map:
        sys.stdout.write(attribution_map_json())
        return

    if not args.counter:
        sys.exit("Нужен --counter (или вызови --show-attribution-map).")

    token = "DRY" if args.dry_run else get_token()

    # Management: список целей.
    if args.preset == "goals":
        result = fetch_goals(args.counter, token)
    else:
        if args.preset:
            spec = build_preset(args.preset, args.attribution,
                                args.goal, args.segment)
            metrics = args.metrics or spec.get("metrics")
            dimensions = args.dimensions or spec.get("dimensions")
            filters = args.filters if args.filters is not None else spec.get("filters")
        else:
            if not (args.metrics and args.dimensions):
                sys.exit("Без --preset нужны --metrics и --dimensions.")
            metrics, dimensions, filters = args.metrics, args.dimensions, args.filters

        result = fetch_stat(args.counter, token, metrics, dimensions, filters,
                            args.attribution, args.date1, args.date2,
                            args.limit, args.dry_run)

    out_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_text)
        print(f"OK → {args.out}")
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
