#!/usr/bin/env python3
"""Create honest, human-readable WoW reports from Raider.IO's saved snapshot."""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUNGEONS = (
    ("Altar of Fangs", "Алтарь Клыков"),
    ("Murder Row", "Закоулок душегубов"),
    ("Den of Nalorakk", "Логово Налоракка"),
    ("The Blinding Vale", "Слепящая долина"),
    ("Voidscar Arena", "Арена Шрама Бездны"),
    ("Kings' Rest", "Гробница королей"),
    ("Temple of Sethraliss", "Храм Сетралисс"),
    ("Ruby Life Pools", "Рубиновые Омуты Жизни"),
)
ENCHANT_CANDIDATE_SLOTS = (
    "head", "shoulder", "chest", "legs", "feet",
    "finger1", "finger2", "mainhand", "offhand",
)


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_json(path, payload):
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


def short_item(item):
    item = as_dict(item)
    return {
        "item_id": item.get("item_id"),
        "name": item.get("name"),
        "item_level": item.get("item_level"),
        "enchants": item.get("enchants", []),
        "gems": item.get("gems", []),
        "bonuses": item.get("bonuses", []),
    }


def item_fingerprint(item):
    item = as_dict(item)
    return (item.get("item_id"), item.get("item_level"),
            tuple(item.get("enchants") or []), tuple(item.get("gems") or []),
            tuple(item.get("bonuses") or []))


def gear_history(snapshot):
    path = ROOT / "gear-history.json"
    current = as_dict(as_dict(snapshot.get("gear")).get("items"))
    previous = read_json(path, {"entries": [], "last_equipped": {}})
    last = as_dict(previous.get("last_equipped"))
    entries = as_list(previous.get("entries"))
    changes = []
    for slot in sorted(set(current) | set(last)):
        before = as_dict(last.get(slot))
        after = short_item(current.get(slot)) if slot in current else {}
        if before and after and item_fingerprint(before) != item_fingerprint(after):
            changes.append({"slot": slot, "before": before, "after": after})
        elif before and not after:
            changes.append({"slot": slot, "before": before, "after": None})
        elif not before and after and last:
            changes.append({"slot": slot, "before": None, "after": after})
    stamp = snapshot.get("source_last_crawled_at") or snapshot.get("fetched_at_utc")
    if not last and current:
        entries.append({"at": stamp, "type": "baseline", "message": "Первый снимок экипировки"})
    elif changes:
        entries.append({"at": stamp, "type": "gear_change", "changes": changes})
    history = {
        "note": "История фиксируется с момента подключения трекера; изменения между двумя проверками могут быть пропущены.",
        "last_checked_at": snapshot.get("fetched_at_utc"),
        "last_source_crawled_at": snapshot.get("source_last_crawled_at"),
        "last_equipped": {slot: short_item(item) for slot, item in current.items()},
        "entries": entries[-120:],
    }
    write_json(path, history)
    return history


def find_best_mplus(runs, name):
    matches = [r for r in as_list(runs) if as_dict(r).get("dungeon", "").casefold() == name.casefold()]
    return max(matches, key=lambda r: (r.get("score") or 0, r.get("mythic_level") or 0), default=None)


def goal_for_level(level):
    if not level: return 4
    if level < 5: return 5
    if level < 7: return 7
    if level < 9: return 9
    if level < 10: return 10
    return level + 1


def generate_mplus(snapshot):
    mp = as_dict(snapshot.get("mythic_plus"))
    seasons = as_list(mp.get("scores_by_season"))
    score = as_dict(seasons[0].get("scores")).get("all") if seasons else None
    raw_best = as_list(mp.get("best_runs"))
    routes = []
    for english, russian in DUNGEONS:
        run = find_best_mplus(raw_best, english)
        level = run.get("mythic_level") if run else None
        routes.append({
            "dungeon_en": english, "dungeon_ru": russian,
            "best_level": level,
            "best_score": run.get("score") if run else None,
            "timed": (run.get("num_keystone_upgrades", 0) > 0) if run else None,
            "url": run.get("url") if run else None,
            "suggested_next_level": goal_for_level(level or 0),
            "priority": 1 if not run else (2 if level < 6 else 3),
        })
    routes.sort(key=lambda x: (x["priority"], x["best_level"] or 0, x["dungeon_ru"]))
    status = {
        "source_last_crawled_at": snapshot.get("source_last_crawled_at"),
        "fetched_at_utc": snapshot.get("fetched_at_utc"),
        "season": seasons[0].get("season") if seasons else None,
        "score": score,
        "routes": routes,
        "best_runs": raw_best,
        "recent_runs": as_list(mp.get("recent_runs")),
        "weekly_highest_level_runs": as_list(mp.get("weekly_highest_level_runs")),
        "previous_weekly_highest_level_runs": as_list(mp.get("previous_weekly_highest_level_runs")),
        "ranks": mp.get("ranks"),
    }
    write_json(ROOT / "mythic-plus.json", status)

    lines = [
        "# Маршрут ключей Блафыча",
        "",
        f"**M+ рейтинг:** {score if score is not None else 'нет данных'} · **Сезон:** {status['season'] or 'неизвестен'}",
        f"**Последний снимок Raider.IO:** {snapshot.get('source_last_crawled_at') or 'нет даты'}",
        "",
        "Порядок рассчитан автоматически **по отсутствующим и слабым результатам** — это НЕ рейтинг простоты данжей и НЕ точный прогноз очков.",
        "",
        "| Очерёдность | Подземелье | Лучший ключ | Рекомендуемая цель |",
        "|---|---|---:|---:|",
    ]
    for i, row in enumerate(routes, start=1):
        have = f"+{row['best_level']}" if row["best_level"] else "не закрыт"
        lines.append(f"| {i} | {row['dungeon_ru']} | {have} | +{row['suggested_next_level']} |")
    lines += [
        "",
        "## Как использовать",
        "",
        "1. Сначала закрывай недостающие подземелья, затем улучшай худшие результаты.",
        "2. Указанный ключ — ориентир, а не гарантированная безопасная сложность; смотри на группу и знакомство с механиками.",
        "3. В первую очередь пробуй запускать свой ключ: это избавляет от конкуренции за место ДД.",
        "4. Показаны только данные, доступные через Raider.IO; новых прохождений может ещё не быть в его базе.",
        "",
        "[Профиль Блафыча на Raider.IO](https://raider.io/ru/characters/eu/gordunni/%D0%91%D0%BB%D0%B0%D1%84%D1%8B%D1%87)",
    ]
    write_text(ROOT / "next-keys.md", "\n".join(lines))
    return status


def generate_audit(snapshot):
    slots = as_dict(as_dict(snapshot.get("gear")).get("items"))
    detected = []
    potential = []
    for name, item in slots.items():
        item = as_dict(item)
        enchants = item.get("enchants") or []
        gems = item.get("gems") or []
        detected.append({
            "slot": name, "item_name": item.get("name"), "item_level": item.get("item_level"),
            "enchants": as_list(item.get("enchants_detail")),
            "gems": as_list(item.get("gems_detail")),
        })
        if name in ENCHANT_CANDIDATE_SLOTS and not enchants:
            potential.append({
                "slot": name, "item_name": item.get("name"),
                "reason": "Не обнаружено зачарование; проверь применимость в игре",
            })
    result = {
        "source_last_crawled_at": snapshot.get("source_last_crawled_at"),
        "limitations": (
            "Отсутствие зачарования в Raider.IO НЕ доказывает, что слот можно или нужно зачаровать. "
            "API не перечисляет доступные пустые гнёзда. Подбор BiS-чар и камней требует актуальных гайдов/симуляции."
        ),
        "observed": detected, "review_missing_enchant": potential,
    }
    write_json(ROOT / "enchant-audit.json", result)
    return result


def read_manual_talents():
    path = ROOT / "talent-import.txt"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("BLIZZARD_TALENT_STRING="):
            value = line.partition("=")[2].strip()
            return value if value else None
    return None


def generate_weekly(snapshot, mplus):
    runs = mplus["weekly_highest_level_runs"]
    output = {
        "fetched_at_utc": snapshot.get("fetched_at_utc"),
        "source_last_crawled_at": snapshot.get("source_last_crawled_at"),
        "weekly_highest_level_runs": runs,
        "previous_weekly_highest_level_runs": mplus["previous_weekly_highest_level_runs"],
        "affixes": snapshot.get("weekly_affixes"),
        "affixes_error": snapshot.get("weekly_affixes_error"),
        "vault_status": "unknown",
        "vault_note": (
            "Raider.IO сообщает лишь ограниченную выборку недельных ключей. "
            "ЭТО НЕ точное число прохождений и не состояние Великого хранилища. "
            "Вылазки, рейдовые ячейки, задания, валюта и личный ключ автоматически не отслеживаются."
        ),
    }
    write_json(ROOT / "weekly.json", output)
    return output


def format_raid_summary(raids):
    if not raids:
        return "Raider.IO пока не вернул прогресс рейдов."

    current_raids = (
        ("the-venomous-abyss", "Отравленная бездна"),
        ("the-unbinding-of-kithix", "Освобождение Кит'икса"),
        ("the-tidebound-grotto", "Приливный грот"),
    )
    lines = [
        "| Рейд | Обычный | Героический | Эпохальный |",
        "|---|---:|---:|---:|",
    ]
    for slug, title in current_raids:
        record = as_dict(raids.get(slug))
        if not record:
            continue
        total = record.get("total_bosses", "?")
        normal = record.get("normal_bosses_killed", 0)
        heroic = record.get("heroic_bosses_killed", 0)
        mythic = record.get("mythic_bosses_killed", 0)
        lines.append(f"| {title} | {normal}/{total} | {heroic}/{total} | {mythic}/{total} |")
    if len(lines) == 2:
        return "Нет данных о рейдах текущего сезона."

    lines += [
        "",
        "Учитываются только убийства боссов, записанные Raider.IO. "
        "Сюжетный режим и поиск рейда в этой таблице не отображаются.",
    ]
    old_raid = as_dict(raids.get("sporefall"))
    if old_raid:
        total = old_raid.get("total_bosses", "?")
        normal = old_raid.get("normal_bosses_killed", 0)
        lines.append(f"Предыдущий сезон: **Споропад** — {normal}/{total} (обычный).")
    return "\n".join(lines)

def generate_dashboard(snapshot, mplus, audit, history, raids, talents, weekly):
    gear = as_dict(snapshot.get("gear"))
    rows = as_dict(gear.get("items"))
    spec = as_dict(snapshot.get("character")).get("active_spec_name") or "неизвестна"
    score = mplus.get("score")
    changes = [entry for entry in history.get("entries", []) if entry.get("type") == "gear_change"]
    lines = [
        "# Блафыч — панель персонажа",
        "",
        f"**Специализация:** {spec} · **Надето:** {gear.get('item_level_equipped', '?')} ilvl "
        f"· **M+ рейтинг:** {score if score is not None else 'неизвестен'}",
        "",
        f"**Последнее обновление Raider.IO:** {snapshot.get('source_last_crawled_at') or 'неизвестно'}",
        f"**GitHub забрал данные:** {snapshot.get('fetched_at_utc')}",
        "",
        "⚠️ Данные не в реальном времени: Raider.IO может отставать от игры.",
        "",
        "## Что делать дальше",
        "",
    ]
    for row in mplus["routes"][:4]:
        lines.append(f"- {row['dungeon_ru']}: "
                     f"{'нет зачтённого ключа' if not row['best_level'] else 'лучший +'+str(row['best_level'])}; "
                     f"цель **+{row['suggested_next_level']}**.")
    lines += [
        "",
        "Полный маршрут: [next-keys.md](next-keys.md).",
        "",
        "## Состояние экипировки",
        "",
        "| Слот | Вещь | ilvl |",
        "|---|---|---:|",
    ]
    labels = {
        "head": "Голова", "neck": "Шея", "shoulder": "Плечи", "back": "Плащ",
        "chest": "Грудь", "waist": "Пояс", "wrist": "Наручи", "hands": "Перчатки",
        "legs": "Ноги", "feet": "Ботинки", "finger1": "Кольцо 1", "finger2": "Кольцо 2",
        "trinket1": "Аксессуар 1", "trinket2": "Аксессуар 2",
        "mainhand": "Основная рука", "offhand": "Вторая рука",
    }
    for slot in labels:
        item = as_dict(rows.get(slot))
        if item:
            lines.append(f"| {labels[slot]} | {item.get('name', '—')} | {item.get('item_level', '—')} |")
    lines += [
        "",
        "## Рейды",
        "",
        format_raid_summary(raids),
        "",
        "## Таланты",
        "",
        ("Данные талантов доступны в [talents.json](talents.json)."
         if talents else "Raider.IO не вернул таланты; актуальный билд **не подтверждён**."),
        "",
        "## Зачарования",
        "",
        (f"Есть {len(audit['review_missing_enchant'])} потенциальных пунктов для проверки "
         "в [enchant-audit.json](enchant-audit.json). Это **не** подтверждённые ошибки."
         if audit["review_missing_enchant"] else "На проверяемых слотах пропусков не обнаружено."),
        "",
        "## Недельный прогресс",
        "",
        f"Raider.IO вернул {len(weekly['weekly_highest_level_runs'])} записей о лучших недельных ключах. "
        "**Это не счётчик Великого хранилища.**",
        "",
        f"**Аффиксы EU:** {as_dict(weekly.get('affixes')).get('title') or 'нет данных'}",
        "",
        "Полные данные: [weekly.json](weekly.json).",
        "",
        "## Последние изменения шмота",
        "",
    ]
    if changes:
        for entry in changes[-5:][::-1]:
            lines.append(f"- **{entry.get('at')}:** " +
                         "; ".join(f"{c['slot']}: "
                                   f"{as_dict(c.get('before')).get('name', 'пусто')} → "
                                   f"{as_dict(c.get('after')).get('name', 'пусто')}"
                                   for c in entry.get("changes", [])[:8]))
    else:
        lines.append("История только запущена, изменений после первого снимка пока не зафиксировано.")
    lines += [
        "",
        "---",
        "",
        "[Raider.IO](https://raider.io/ru/characters/eu/gordunni/%D0%91%D0%BB%D0%B0%D1%84%D1%8B%D1%87) · "
        "[gear.json](gear.json) · [mythic-plus.json](mythic-plus.json) · "
        "[raids.json](raids.json) · [talents.json](talents.json) · "
        "[gear-history.json](gear-history.json)",
    ]
    write_text(ROOT / "DASHBOARD.md", "\n".join(lines))


def main():
    snapshot = read_json(ROOT / "gear.json")
    if not isinstance(snapshot, dict) or not as_dict(as_dict(snapshot.get("gear")).get("items")):
        raise ValueError("gear.json is missing or contains no equipment")
    mplus = generate_mplus(snapshot)
    raids = as_dict(snapshot.get("raid_progression"))
    talents = snapshot.get("talents")
    manual_talents = read_manual_talents()
    talent_source = "raider_io" if talents else ("manual_import" if manual_talents else "unavailable")
    write_json(ROOT / "raids.json", {
        "source_last_crawled_at": snapshot.get("source_last_crawled_at"),
        "available": bool(raids), "raid_progression": raids,
        "note": "Возможна задержка индексации рейдовых результатов Raider.IO.",
    })
    write_json(ROOT / "talents.json", {
        "source_last_crawled_at": snapshot.get("source_last_crawled_at"),
        "active_spec": as_dict(snapshot.get("character")).get("active_spec_name"),
        "available": bool(talents or manual_talents),
        "source": talent_source,
        "talents": talents,
        "manual_export_string": manual_talents if not talents else None,
        "note": ("Данные из Raider.IO могут отставать от игры. "
                 "Если источник manual_import, экспорт введён вручную и может устареть."),
    })
    history = gear_history(snapshot)
    audit = generate_audit(snapshot)
    weekly = generate_weekly(snapshot, mplus)
    generate_dashboard(snapshot, mplus, audit, history, raids, talents or manual_talents, weekly)
    print(f"Reports: {len(mplus['routes'])} dungeons, raid data {bool(raids)}, talent data {bool(talents)}, "
          f"{len(history['entries'])} history entries, talents source {talent_source}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR building reports: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
