#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_bundle.py — собирает yandex-direct-audit.zip для загрузки в Claude Desktop
(Settings -> Capabilities -> Skills).

Главное, ради чего скрипт существует: бандл раздаётся дальше, и в него НЕ должны
попасть ни секреты (.env с OAuth-токенами), ни данные клиентов (direct-audits/),
ни запаркованный код, который в Desktop всё равно не работает (parked/).
Поэтому список исключений — белый шум по умолчанию, а не опция.

Использование:
    python scripts/make_bundle.py
    python scripts/make_bundle.py --output путь/к/bundle.zip
"""

import argparse
import fnmatch
import os
import sys
import zipfile

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Каталоги, которые не едут в бандл целиком.
EXCLUDE_DIRS = {
    ".git",            # история
    "__pycache__",     # мусор
    ".pytest_cache",   # мусор: раньше уезжал в бандл
    "direct-audits",   # данные клиентов
    "docs",            # внутренние планы и спеки
    "parked",          # Метрика: в Desktop не работает (нет сети)
    ".claude",
    ".github",
    ".claude-plugin",  # манифест плагина Claude Code — в бандле не нужен
}

# Файлы по маскам.
EXCLUDE_FILES = [
    ".env", ".env.*",          # секреты
    "*.pyc", "*.pyo",
    "*.zip",
    ".gitignore",
    ".DS_Store",
]

# Без этих файлов скилл нерабочий — проверяем перед упаковкой.
REQUIRED = [
    "SKILL.md",
    "references/mcp-tools-map.md",
    "references/metrika-tools-map.md",
    "references/attribution.md",
    "references/custom-report-recipes.md",
    "subagents/search-queries.md",
    "subagents/rsya-placements.md",
    "subagents/bid-segments.md",
    "scripts/run_analysis.py",
    "scripts/analyze_placements.py",
    "scripts/render_report.py",
]


def excluded_file(name):
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILES)


def collect():
    """Пути файлов бандла относительно корня скилла, в стабильном порядке."""
    found = []
    for root, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if excluded_file(name):
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, SKILL_DIR).replace("\\", "/")
            found.append(rel)
    return found


def main():
    ap = argparse.ArgumentParser(description="Сборка zip-бандла скилла для Claude Desktop")
    ap.add_argument("--output", default=os.path.join(SKILL_DIR, "yandex-direct-audit.zip"),
                    help="путь к zip (по умолчанию yandex-direct-audit.zip в корне скилла)")
    args = ap.parse_args()

    rels = collect()

    missing = [r for r in REQUIRED if r not in rels]
    if missing:
        print("Не хватает обязательных файлов — бандл не собран:", file=sys.stderr)
        for m in missing:
            print("  - {}".format(m), file=sys.stderr)
        sys.exit(1)

    # Claude Desktop принимает ровно один SKILL.md на бандл. Брифы субагентов поэтому
    # называются subagents/<имя>.md — если кто-то переименует их обратно, ловим здесь,
    # а не в диалоге загрузки.
    skills = [r for r in rels if os.path.basename(r) == "SKILL.md"]
    if len(skills) != 1:
        print("В бандле должен быть ровно один SKILL.md, найдено {}:".format(len(skills)),
              file=sys.stderr)
        for r in skills:
            print("  - {}".format(r), file=sys.stderr)
        print("Брифы субагентов должны называться subagents/<имя>.md, а не SKILL.md.",
              file=sys.stderr)
        sys.exit(1)

    # Страховка от собственной ошибки в масках: секрет в бандле хуже, чем несобранный бандл.
    leaked = [r for r in rels
              if os.path.basename(r).startswith(".env")
              or r.startswith(("direct-audits/", "parked/", "docs/"))]
    if leaked:
        print("В список попало то, чего там быть не должно:", file=sys.stderr)
        for r in leaked:
            print("  - {}".format(r), file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rels:
            zf.write(os.path.join(SKILL_DIR, rel), arcname=rel)

    size_kb = os.path.getsize(args.output) / 1024.0
    print("Бандл готов: {} ({:.0f} КБ, файлов: {})".format(args.output, size_kb, len(rels)))
    print()
    for rel in rels:
        print("  {}".format(rel))
    print()
    print("Загрузи zip в Claude Desktop: Settings -> Capabilities -> Skills.")


if __name__ == "__main__":
    main()
