# -*- coding: utf-8 -*-
"""
run_analysis.py — обёртка над query_analyzer.

Вход: строки из JSON (выгрузка из MCP, основной путь) или файл-выгрузка TSV/CSV (фолбек).
Выход: queries_candidates.json, minus_keywords.txt, phrase_actions.md.
В Директ ничего не пишет — только рекомендации.
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_analyzer import analyze, to_num, NUMERIC, DEFAULT_PATTERNS

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_patterns(skill_dir):
    path = os.path.join(skill_dir, "assets", "query_patterns.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write(f"warn: не прочитал query_patterns.json ({e}), беру дефолт\n")
    return DEFAULT_PATTERNS


def _norm_row(r):
    return {
        "keyword": str(r.get("keyword", "") or "").strip(),
        "query": str(r.get("query", "") or "").strip(),
        "campaign": (str(r.get("campaign", "") or "").strip() or "—"),
        "campaign_id": str(r.get("campaign_id", "") or "").strip(),
        "ad_group": str(r.get("ad_group", "") or "").strip(),
        "impressions": to_num(r.get("impressions")),
        "clicks": to_num(r.get("clicks")),
        "cost": to_num(r.get("cost")),
        "conversions": to_num(r.get("conversions")),
    }


def load_rows_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return [_norm_row(r) for r in rows]


def load_rows_file(path):
    """Фолбек: TSV/CSV выгрузка из Мастера отчётов (keyword + query)."""
    sep = "\t"
    with open(path, encoding="utf-8") as f:
        raw = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not raw:
        raise SystemExit("Пустой отчёт.")
    if "\t" not in raw[0] and ";" in raw[0]:
        sep = ";"
    elif "\t" not in raw[0] and "," in raw[0]:
        sep = ","
    hidx = 0
    for i, ln in enumerate(raw):
        low = ln.lower()
        if any(k in low for k in ("поисковый запрос", "query", "ключевая фраза", "campaignname")):
            hidx = i
            break
    header = [h.strip().lower() for h in raw[hidx].split(sep)]

    def pick(row, *subs):
        for j, h in enumerate(header):
            if any(s in h for s in subs):
                return row[j] if j < len(row) else ""
        return ""

    out = []
    for ln in raw[hidx + 1:]:
        if ln.lower().startswith(("total", "итог")):
            continue
        cells = ln.split(sep)
        out.append(_norm_row({
            "keyword": pick(cells, "ключевая фраза", "условие показа", "keyword", "criteria"),
            "query": pick(cells, "поисковый запрос", "query"),
            "campaign": pick(cells, "кампания", "campaign"),
            "campaign_id": pick(cells, "id кампании", "№ кампании", "campaignid"),
            "ad_group": pick(cells, "группа", "adgroup"),
            "impressions": pick(cells, "показ", "impr"),
            "clicks": pick(cells, "клик", "click"),
            "cost": pick(cells, "расход", "cost"),
            "conversions": pick(cells, "конверси", "conversion"),
        }))
    return out


def write_candidates_json(outdir, res):
    with open(os.path.join(outdir, "queries_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)


def write_minus_keywords(outdir, res):
    with open(os.path.join(outdir, "minus_keywords.txt"), "w", encoding="utf-8") as f:
        f.write("# Минус-слова и минус-фразы. Заливаешь сам в Яндекс.Директ.\n\n")
        f.write("=== Уровень КАМПАНИИ (общие стоп-слова) ===\n")
        for w in res["minus_words_campaign"]:
            f.write(f"{w['minus']}\t# {w['category_ru']}: {w['queries']} запр., "
                    f"{w['clicks']} кл., {w['cost']:.0f} ₽\n")
        f.write("\n=== Уровень ГРУППЫ (специфичные минус-фразы) ===\n")
        for g in res["minus_phrases_group"]:
            grp = f" [{g['ad_group']}]" if g["ad_group"] else ""
            f.write(f"{g['query']}\t# {g['campaign']}{grp}: {g['clicks']} кл., {g['cost']:.0f} ₽\n")


def write_phrase_actions_md(outdir, res):
    act_ru = {"stop": "🔴 Отключить/удалить", "lower_bid": "🟠 Понизить ставку",
              "raise_bid": "🟢 Поднять ставку + в отд. группу", "hold": "⚪ Мало данных",
              "keep": "✅ Норма"}
    with open(os.path.join(outdir, "phrase_actions.md"), "w", encoding="utf-8") as f:
        f.write("# Действия по ключевым фразам\n\n")
        if not res.get("phrases_enabled", True):
            f.write("> Нет данных по конверсиям (цели Метрики не привязаны) — "
                    "рекомендации по ставкам недоступны. См. скилл `metrika-goals-setup`.\n")
            return
        f.write("| Кампания | Фраза | Действие | Расход ₽ | Клики | Конв. | CPA ₽ | Причина |\n")
        f.write("|---|---|---|--:|--:|--:|--:|---|\n")
        for p in res["phrases"]:
            if p["action"] == "keep":
                continue
            cpa = f"{p['cpa']:.0f}" if p["cpa"] else "—"
            f.write(f"| {p['campaign']} | {p['keyword']} | {act_ru[p['action']]} | "
                    f"{p['cost']:.0f} | {p['clicks']} | {p['conversions']:.0f} | {cpa} | {p['reason']} |\n")


def main(argv=None):
    # На Windows консоль часто в cp1251 — переключаем вывод на UTF-8, иначе print с
    # эмодзи/₽ падает. Файлы и так пишутся в UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Минусация ключевых фраз и поисковых запросов Директа (read-only).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--rows", help="JSON со строками (выгрузка из MCP).")
    src.add_argument("--input", help="Файл-выгрузка TSV/CSV (фолбек).")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--tcpa", type=float, default=None)
    ap.add_argument("--tcpa-map", default=None, help='JSON {"Кампания": tCPA}.')
    ap.add_argument("--target-geo", default="")
    ap.add_argument("--competitors", default="")
    ap.add_argument("--money-in-rub", action="store_true", help="Деньги уже в рублях (не делить на 1e6).")
    ap.add_argument("--no-conversions", action="store_true", help="В отчёте нет конверсий.")
    ap.add_argument("--phrase-min-clicks", type=int, default=30)
    ap.add_argument("--query-min-clicks", type=int, default=25)
    ap.add_argument("--cpa-high", type=float, default=1.5)
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    patterns = load_patterns(SKILL_DIR)
    rows = load_rows_json(args.rows) if args.rows else load_rows_file(args.input)

    tcpa_map = {}
    if args.tcpa_map:
        with open(args.tcpa_map, encoding="utf-8") as f:
            tcpa_map = json.load(f)
    target_geo = [g.strip() for g in args.target_geo.split(",") if g.strip()]
    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
    money_div = 1.0 if args.money_in_rub else 1_000_000.0

    res = analyze(rows, tcpa_global=args.tcpa, tcpa_map=tcpa_map, target_geo=target_geo,
                  competitors=competitors, patterns=patterns,
                  phrase_min_clicks=args.phrase_min_clicks,
                  query_min_clicks=args.query_min_clicks, cpa_high=args.cpa_high,
                  money_div=money_div, has_conversions=not args.no_conversions)

    write_candidates_json(args.outdir, res)
    write_minus_keywords(args.outdir, res)
    write_phrase_actions_md(args.outdir, res)

    ac = Counter(p["action"] for p in res["phrases"])
    print(f"Фразы: 🔴 stop {ac['stop']} · 🟠 lower {ac['lower_bid']} · 🟢 raise {ac['raise_bid']} · "
          f"⚪ hold {ac['hold']} · ✅ keep {ac['keep']}.")
    print(f"Минус-слова (кампания): {len(res['minus_words_campaign'])} · "
          f"минус-фразы (группа): {len(res['minus_phrases_group'])} · "
          f"review: {len(res['review'])} · экономия ≈ {res['saving_estimate']:.0f} ₽.")
    print(f"Файлы: {args.outdir}\\queries_candidates.json, minus_keywords.txt, phrase_actions.md")


if __name__ == "__main__":
    main()
