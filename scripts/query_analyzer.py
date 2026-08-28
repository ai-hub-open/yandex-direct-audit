# -*- coding: utf-8 -*-
"""
query_analyzer.py — ядро минусации ключевых фраз и поисковых запросов Яндекс.Директа.

Чистые функции, без файлового I/O. Пороговая логика перенесена из analyze_queries.py
без изменений; добавлен режим без конверсий (has_conversions=False) для случая,
когда к кампании не привязан счётчик или не настроены цели и в отчёте нет колонки конверсий.

Скрипт ничего не пишет в аккаунт — только рекомендации.
"""

import re
from collections import defaultdict

DEFAULT_PATTERNS = {
    "markers": [
        {"pattern": "бесплатн", "minus": "бесплатно", "category": "free"},
        {"pattern": "скачать|скачива", "minus": "скачать", "category": "free"},
        {"pattern": "торрент|torrent", "minus": "торрент", "category": "free"},
        {"pattern": "крякнут|кряк |keygen|взлом", "minus": "взлом", "category": "free"},
        {"pattern": "реферат|курсова|диплом", "minus": "реферат", "category": "info"},
        {"pattern": "своими руками", "minus": "своими руками", "category": "info"},
        {"pattern": "как сделать|как выбрать|как сшить|как собрать", "minus": "как", "category": "info"},
        {"pattern": "самостоятельн|самому|сам ", "minus": "самостоятельно", "category": "info"},
        {"pattern": "инструкци|схема|чертеж|чертёж", "minus": "инструкция", "category": "info"},
        {"pattern": "что такое|почему", "minus": "что такое", "category": "info"},
        {"pattern": "мастер-класс|мастер класс", "minus": "мастер-класс", "category": "info"},
        {"pattern": "вакансия|ваканси", "minus": "вакансия", "category": "job"},
        {"pattern": "зарплат|резюме|устроиться|подработ", "minus": "работа", "category": "job"},
        {"pattern": "б/у|\\bбу\\b", "minus": "б/у", "category": "used"},
        {"pattern": "авито|юла", "minus": "авито", "category": "used"},
        {"pattern": "форум", "minus": "форум", "category": "info"},
        {"pattern": "отзыв", "minus": "отзывы", "category": "watch"},
        {"pattern": "вики|wikipedia|википед", "minus": "википедия", "category": "info"}
    ],
    "cities": [
        "казань", "екатеринбург", "новосибирск", "нижний новгород", "самара", "омск",
        "челябинск", "ростов", "уфа", "краснодар", "пермь", "воронеж", "волгоград",
        "саратов", "тюмень", "тольятти", "ижевск", "барнаул", "ульяновск", "иркутск",
        "владивосток", "ярославль", "хабаровск", "махачкала", "томск", "оренбург",
        "кемерово", "новокузнецк", "рязань", "астрахань", "сочи", "киров",
        "калининград", "тула", "липецк", "курск", "сургут", "тверь", "брянск", "минск"
    ],
    "competitors": []
}

NUMERIC = {"impressions", "clicks", "ctr", "cost", "avgcpc", "conversions",
           "conversionrate", "costperconversion", "revenue", "bouncerate"}


def to_num(v):
    if v is None:
        return 0.0
    v = str(v).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if v in ("", "--", "-"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def tokens(q):
    return re.findall(r"[а-яёa-z0-9/]+", (q or "").lower())


def compile_markers(patterns):
    return [(re.compile(m["pattern"], re.I), m["minus"], m["category"])
            for m in patterns.get("markers", [])]


def analyze_phrases(rows, tcpa_for, money_div, phrase_min_clicks, cpa_high_mult):
    agg = {}
    camp_tot = defaultdict(lambda: {"cost": 0.0, "conv": 0.0})
    for r in rows:
        kw = r.get("keyword") or "(без фразы)"
        camp = r.get("campaign") or "—"
        key = (camp, kw)
        a = agg.setdefault(key, {"campaign": camp, "campaign_id": r.get("campaign_id", ""),
                                 "keyword": kw, "clicks": 0.0, "cost": 0.0, "conv": 0.0})
        a["clicks"] += r.get("clicks", 0.0)
        a["cost"] += r.get("cost", 0.0) / money_div
        a["conv"] += r.get("conversions", 0.0)
        camp_tot[camp]["cost"] += r.get("cost", 0.0) / money_div
        camp_tot[camp]["conv"] += r.get("conversions", 0.0)
    camp_avg = {c: (t["cost"] / t["conv"] if t["conv"] else None) for c, t in camp_tot.items()}

    out = []
    for (camp, kw), a in agg.items():
        tcpa = tcpa_for(camp)
        cpa = a["cost"] / a["conv"] if a["conv"] else None
        base = camp_avg.get(camp)
        action, reason = "keep", "Работает в пределах нормы."
        if a["conv"] == 0 and tcpa and a["cost"] >= 2 * tcpa:
            action = "stop"
            reason = f"Расход {a['cost']:.0f} ₽ ≥ 2× CPA ({tcpa:.0f} ₽), 0 конверсий — отключить фразу."
        elif a["clicks"] < phrase_min_clicks and a["conv"] == 0:
            action = "hold"
            reason = f"Кликов {int(a['clicks'])} < {phrase_min_clicks}, 0 конверсий — мало данных, не трогаем."
        elif a["conv"] > 0 and tcpa and cpa and cpa >= cpa_high_mult * tcpa:
            action = "lower_bid"
            reason = f"CPA {cpa:.0f} ₽ ≥ {cpa_high_mult:g}× CPA ({tcpa:.0f} ₽) — понизить ставку."
        elif a["conv"] > 0 and base and cpa and cpa < base:
            action = "raise_bid"
            reason = f"CPA {cpa:.0f} ₽ ниже среднего по кампании ({base:.0f} ₽) — поднять ставку, вынести в отдельную группу."
        out.append({"campaign": camp, "keyword": kw, "action": action, "reason": reason,
                    "clicks": round(a["clicks"]), "cost": round(a["cost"], 2),
                    "conversions": round(a["conv"], 2),
                    "cpa": round(cpa, 2) if cpa else None, "tcpa": tcpa})
    order = {"stop": 0, "lower_bid": 1, "raise_bid": 2, "hold": 3, "keep": 4}
    out.sort(key=lambda x: (order[x["action"]], -x["cost"]))
    return out


def classify_query(q, clicks, conv, markers, cities, competitors, target_geo,
                   query_min_clicks, has_conversions=True):
    ql = (q or "").lower()
    qtoks = tokens(q)
    hits = []  # (minus, category, level)

    for rx, minus, cat in markers:
        if rx.search(ql):
            if cat == "watch":
                hits.append((minus, "watch", "review"))
            else:
                hits.append((minus, cat, "campaign"))

    for city in cities:
        if city in target_geo:
            continue
        if " " in city:
            if city[:-1] in ql:
                hits.append((city, "geo", "campaign"))
        else:
            stem = city[:-1] if len(city) >= 5 else city
            if any(t == city or (len(stem) >= 4 and t.startswith(stem)) for t in qtoks):
                hits.append((city, "geo", "campaign"))

    auto = [(m, c, lvl) for (m, c, lvl) in hits if c != "watch"]
    watch = [(m, c, lvl) for (m, c, lvl) in hits if c == "watch"]

    for br in competitors:
        if br in ql:
            if has_conversions:
                if conv == 0:
                    auto.append((br, "competitor", "campaign"))
                # конвертит — не трогаем (как в исходной логике)
            else:
                watch.append((br, "competitor", "review"))

    if auto:
        return {"verdict": "minus", "hits": auto}
    if watch:
        return {"verdict": "review", "hits": watch,
                "note": "watch-паттерн (напр. «отзывы» или конкурент без данных по конверсиям) — реши вручную."}
    if has_conversions and clicks >= query_min_clicks and conv == 0:
        return {"verdict": "minus_phrase_group", "hits": [(q, "no_pattern", "group")]}
    return {"verdict": "ok", "hits": []}


def analyze_queries_block(rows, money_div, markers, cities, competitors, target_geo,
                          query_min_clicks, has_conversions=True):
    agg = {}
    for r in rows:
        q = r.get("query") or "(пустой запрос)"
        camp = r.get("campaign") or "—"
        key = (camp, q)
        a = agg.setdefault(key, {"campaign": camp, "ad_group": r.get("ad_group", ""),
                                 "query": q, "clicks": 0.0, "cost": 0.0, "conv": 0.0})
        a["clicks"] += r.get("clicks", 0.0)
        a["cost"] += r.get("cost", 0.0) / money_div
        a["conv"] += r.get("conversions", 0.0)

    cat_name = {"free": "нерелевантный (бесплатно/скачать)", "info": "информационный",
                "job": "поиск работы", "used": "б/у / маркетплейс", "geo": "чужое гео",
                "competitor": "конкурент", "no_pattern": "слив без конверсий"}
    words = {}
    group_phrases = []
    review = []
    saving = 0.0

    for a in agg.values():
        c = classify_query(a["query"], a["clicks"], a["conv"], markers, cities,
                           competitors, target_geo, query_min_clicks, has_conversions)
        if c["verdict"] == "minus":
            for minus, cat, lvl in c["hits"]:
                w = words.setdefault(minus, {"minus": minus, "category": cat,
                                             "category_ru": cat_name.get(cat, cat),
                                             "queries": 0, "clicks": 0.0, "cost": 0.0, "examples": []})
                w["queries"] += 1
                w["clicks"] += a["clicks"]
                w["cost"] += a["cost"]
                if len(w["examples"]) < 4:
                    w["examples"].append(a["query"])
            if a["conv"] == 0:
                saving += a["cost"]
        elif c["verdict"] == "minus_phrase_group":
            group_phrases.append({"campaign": a["campaign"], "ad_group": a["ad_group"],
                                  "query": a["query"], "clicks": round(a["clicks"]),
                                  "cost": round(a["cost"], 2),
                                  "reason": f"≥{query_min_clicks} кликов, 0 конверсий, паттерн не распознан — минус-фраза на группу или проверь смысл."})
            if a["conv"] == 0:
                saving += a["cost"]
        elif c["verdict"] == "review":
            review.append({"campaign": a["campaign"], "query": a["query"],
                           "clicks": round(a["clicks"]), "cost": round(a["cost"], 2),
                           "note": c.get("note", "")})

    word_list = sorted(words.values(), key=lambda w: -w["cost"])
    for w in word_list:
        w["clicks"] = round(w["clicks"])
        w["cost"] = round(w["cost"], 2)
    group_phrases.sort(key=lambda g: -g["cost"])
    return word_list, group_phrases, review, round(saving, 2)


def analyze(rows, tcpa_global=None, tcpa_map=None, target_geo=None, competitors=None,
            patterns=None, phrase_min_clicks=30, query_min_clicks=25, cpa_high=1.5,
            money_div=1.0, has_conversions=True):
    """Единая точка входа. rows — список нормализованных dict из MCP/файла."""
    patterns = patterns or DEFAULT_PATTERNS
    markers = compile_markers(patterns)
    cities = [c.lower() for c in patterns.get("cities", [])]
    comp = [c.lower() for c in (competitors or [])] + \
           [c.lower() for c in patterns.get("competitors", [])]
    geo = set(g.lower() for g in (target_geo or []))
    tmap = tcpa_map or {}
    tcpa_for = lambda camp: tmap.get(camp, tcpa_global)

    phrases = (analyze_phrases(rows, tcpa_for, money_div, phrase_min_clicks, cpa_high)
               if has_conversions else [])
    words, group_phrases, review, saving = analyze_queries_block(
        rows, money_div, markers, cities, comp, geo, query_min_clicks, has_conversions)
    return {"phrases": phrases, "minus_words_campaign": words,
            "minus_phrases_group": group_phrases, "review": review,
            "saving_estimate": saving, "phrases_enabled": bool(has_conversions)}
