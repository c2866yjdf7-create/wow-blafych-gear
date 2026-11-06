#!/usr/bin/env python3
"""Conservative, explainable gear triage for Blafych, not a DPS simulator.

Source gear: gear.json from Raider.IO.
Meta suggestions: human-curated from Enhancement Shaman 12.1.5 guides.
The rules never claim a precise DPS gain or automatically calculate stat weights.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "gear.json"

SLOT_NAMES = {
    "head": "Голова", "neck": "Шея", "shoulder": "Плечи",
    "back": "Плащ", "chest": "Грудь", "waist": "Пояс",
    "wrist": "Наручи", "hands": "Перчатки", "legs": "Штаны",
    "feet": "Ботинки", "finger1": "Кольцо 1", "finger2": "Кольцо 2",
    "trinket1": "Аксессуар 1", "trinket2": "Аксессуар 2",
    "mainhand": "Основная рука", "offhand": "Вторая рука",
}
SOURCES = [
    {
        "title": "Icy Veins — Enhancement gear & trinkets, 12.1.5",
        "url": "https://www.icy-veins.com/wow/enhancement-shaman-pve-dps-gear-best-in-slot",
    },
    {
        "title": "Wowhead — Enhancement Shaman BiS, 12.1.5",
        "url": "https://www.wowhead.com/guide/classes/shaman/enhancement/bis-gear",
    },
    {
        "title": "Method — Enhancement gearing, Midnight",
        "url": "https://www.method.gg/guides/enhancement-shaman/gearing",
    },
]
# Curated targets, independent of current inventory levels. Update on patch changes.
TARGETS = {
    "trinket2": {
        "rank": 1, "action": "Искать более сильную пассивную триньку",
        "target": "«Гильотинная атака Зул'джина» (Извилистый алтарь) или «Щупальце искорёженного ужаса» (Кит'икс)",
        "why": "Аксессуары сравнивают по эффектам и уровню. Текущая тринька — временная альтернатива; высокий ilvl сам по себе не делает её лучшей.",
        "method": "Рейд «Отравленная бездна»; оценить конкретный дроп по гайду и симуляции.",
        "confidence": "средняя",
    },
    "neck": {
        "rank": 2, "action": "Искать сильную шею",
        "target": "«Реликварий против акиров» (Aqirbane Reliquary), босс Ула'тек, либо качественная шея более высокой дорожки",
        "why": "Низкий уровень предмета относительно остального шмота. Особые свойства и вторичные характеристики могут менять итог.",
        "method": "Героический рейд или высокий ключ/хранилище; сверить предмет перед заменой.",
        "confidence": "средняя",
    },
    "back": {
        "rank": 3, "action": "Заменить плащ при хорошем дропе",
        "target": "Плащ более высокого уровня с подходящими характеристиками; рейд/ключи/хранилище",
        "why": "Слот отстаёт по ilvl, при этом не является сетовым или крафтовым украшением.",
        "method": "M+, героический рейд, Великое хранилище.",
        "confidence": "высокая для приоритета слота",
    },
    "legs": {
        "rank": 4, "action": "Искать штаны выше уровнем",
        "target": "«Набедренники пробуждённого выводка» (Temple of Sethraliss) или сильные рейдовые штаны",
        "why": "302 ilvl. Не снимай текущую вещь автоматически ради меньшей прибавки с плохими характеристиками.",
        "method": "Храм Сетралисс в M+, рейд, Великое хранилище.",
        "confidence": "средняя",
    },
    "waist": {
        "rank": 5, "action": "Заменить пояс при хорошем дропе",
        "target": "Более высокий ilvl и подходящие вторичные характеристики",
        "why": "Один из обычных слотов 302 ilvl без риска потерять сетовый бонус.",
        "method": "M+, рейд или хранилище.",
        "confidence": "высокая для приоритета слота",
    },
    "trinket1": {
        "rank": 6, "action": "Заменять только на действительно сильную триньку",
        "target": "«Ненасытное сердце Ула'тек» (Voracious Heart of Ula'tek), Ула'тек",
        "why": "«Омерзительная обманчивая отрава» — полезная on-use альтернатива. Менять её на случайный предмет 308–311 нельзя без сравнения эффекта.",
        "method": "Героический рейд «Отравленная бездна», прежде всего Ула'тек.",
        "confidence": "высокая для цели, но не для точного DPS",
    },
    "shoulder": {
        "rank": 7, "action": "Повысить уровень сетовых плеч",
        "target": "Та же сетовая вещь выше дорожкой, либо подходящая вещь для Катализатора",
        "why": "Сетовый слот. Замена без сохранения четырёх частей может снизить DPS даже при росте ilvl.",
        "method": "Гербы, Катализатор после проверки дорожки и бонуса комплекта.",
        "confidence": "высокая",
    },
    "finger1": {
        "rank": 8, "action": "Усилить первое кольцо при выгодной замене",
        "target": "Кольцо более высокого уровня с подходящими вторичными характеристиками",
        "why": "Второе кольцо уже сильное. У колец нет ловкости — сравнивай реальные статы, камни и эффекты, не только ilvl.",
        "method": "M+, рейд, Великое хранилище.",
        "confidence": "средняя",
    },
}

PRESERVE = {
    "mainhand": {
        "status": "Улучшать, не спешить менять",
        "reason": "Оружие 321 в основной руке. Урон основной руки очень важен для энха; повышение уровня этого предмета часто выгодно.",
        "next": "Проверить текущую дорожку улучшения у NPC. Специальное оружие «Аман'мусо, месть вождя» — долгосрочная рейдовая цель.",
    },
    "offhand": {
        "status": "Сохранить крафтовый топор",
        "reason": "Крафтовое оружие 318 и возможное украшение: оценивать с учётом эффекта и сохранения комплекта украшений.",
        "next": "Проверить возможность перекрафтовки; не менять ради пары ilvl вслепую.",
    },
    "wrist": {
        "status": "Беречь крафтовые наручи",
        "reason": "Крафтовый слот может содержать сильное украшение, не отражаемое полностью в Raider.IO.",
        "next": "Проверять эффект украшения и дорожку перекрафтовки перед заменой.",
    },
    "finger2": {
        "status": "Оставить кольцо 321",
        "reason": "Слот уже заметно выше среднего уровня; вложения в более слабые слоты обычно логичнее.",
        "next": "Пересматривать при особых эффектах или персональном симе.",
    },
    "head": {
        "status": "Оставить сетовую голову",
        "reason": "Часть набора 4/4, уже 308 ilvl.",
        "next": "Улучшать или заменять на более высокую сетовую версию, сохраняя 4 части.",
    },
    "chest": {
        "status": "Сохранить сетовую грудь",
        "reason": "Часть набора, 305 ilvl; проверь специальное свойство до замены.",
        "next": "Выбирать улучшение с учётом Катализатора и особого эффекта.",
    },
    "hands": {
        "status": "Сохранить сетовые перчатки",
        "reason": "Часть набора, уже 308 ilvl.",
        "next": "Позже искать более высокую дорожку, не теряя сет.",
    },
    "feet": {
        "status": "Без срочной замены",
        "reason": "Ботинки 308 — не главный отстающий слот.",
        "next": "Менять при большом выигрыше уровня или личном симе.",
    },
}


def write_json(path, value):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    gear = source.get("gear", {})
    items = gear.get("items") or {}
    if not isinstance(items, dict) or len(items) < 12:
        raise ValueError("Insufficient equipment data: no analysis will be written")
    spec = (source.get("character") or {}).get("active_spec_name")
    if spec != "Enhancement":
        write_json(ROOT / "gear-analysis.json", {
            "status": "unsupported_spec",
            "source_last_crawled_at": source.get("source_last_crawled_at"),
            "spec": spec,
            "message": "Правила анализа рассчитаны на энха. При другом спеке советы по DPS отключены.",
            "recommendations": [],
            "preserve": [],
        })
        (ROOT / "gear-advice.md").write_text(
            "# Анализ экипировки\n\nБилд не Enhancement. Советы по энху отключены.\n", encoding="utf-8")
        return

    now = datetime.now(timezone.utc)
    crawl = source.get("source_last_crawled_at")
    stale_hours = None
    if crawl:
        try:
            stamp = datetime.fromisoformat(crawl.replace("Z", "+00:00"))
            stale_hours = round((now - stamp).total_seconds() / 3600, 1)
        except ValueError:
            pass
    tier_slots = [k for k, v in items.items() if v.get("tier") is not None]
    has_four_piece = len(tier_slots) >= 4

    recs = []
    for slot, rule in TARGETS.items():
        if slot not in items:
            continue
        item = items[slot]
        ilvl = item.get("item_level")
        reason = rule["why"]
        if slot == "shoulder" and has_four_piece:
            reason = "У тебя 4/4 сет; обычная замена плеч ломает бонус. " + reason
        recs.append({
            "slot": slot,
            "slot_name": SLOT_NAMES[slot],
            "item_name": item.get("name"),
            "item_id": item.get("item_id"),
            "item_level": ilvl,
            "rank": rule["rank"],
            "action": rule["action"],
            "target": rule["target"],
            "why": reason,
            "where": rule["method"],
            "confidence": rule["confidence"],
            "category": "search",
        })
    # Do not insist on replacing a slot that's already high: downrank but keep in view.
    recs.sort(key=lambda r: (r["rank"], r["slot_name"]))

    keep = []
    for slot, rule in PRESERVE.items():
        if slot not in items:
            continue
        item = items[slot]
        keep.append({
            "slot": slot,
            "slot_name": SLOT_NAMES[slot],
            "item_name": item.get("name"),
            "item_level": item.get("item_level"),
            "action": rule["status"],
            "why": rule["reason"],
            "next": rule["next"],
            "category": "keep",
        })
    keep.sort(key=lambda r: list(PRESERVE).index(r["slot"]))

    result = {
        "status": "ok",
        "generated_at_utc": now.isoformat(timespec="seconds"),
        "fetched_at_utc": source.get("fetched_at_utc"),
        "source_last_crawled_at": crawl,
        "data_age_hours": stale_hours,
        "stale": stale_hours is None or stale_hours > 24,
        "meta_checked_on": "2026-11-06",
        "meta_review_note": (
            "Приоритеты и цели подобраны по руководствам 12.1.5 вручную. "
            "Мета НЕ обновляется автоматически, и рекомендации нужно сверять после патчей."
        ),
        "spec": spec,
        "equipped_ilvl": gear.get("item_level_equipped"),
        "tier_slots": tier_slots,
        "tier_count": len(tier_slots),
        "four_piece_active_inferred": has_four_piece,
        "recommendations": recs,
        "preserve": keep,
        "sources": SOURCES,
        "limitations": [
            "Это приоритеты поиска и улучшения, а НЕ математическая оценка DPS.",
            "Raider.IO не отдаёт полный набор вторичных характеристик, эффектов украшений, дорожек улучшения и содержимого сумок.",
            "Сет определён по меткам Raider.IO, а не по проверке внутриигрового эффекта.",
            "Даже предмет с более высоким ilvl может оказаться слабее из-за эффекта, вторичных статов или потери 4/4.",
            "Для точного сравнения нового предмета нужен Raidbots Top Gear/SimulationCraft или подробные данные обеих вещей.",
        ],
    }
    write_json(ROOT / "gear-analysis.json", result)

    lines = [
        "# Блафыч — приоритеты экипировки",
        "",
        f"**Спек:** {spec} · **Надето:** {gear.get('item_level_equipped')} ilvl · **Сет:** {len(tier_slots)} предмета",
        f"**Снимок Raider.IO:** {crawl or 'неизвестно'} · **Возраст:** {stale_hours if stale_hours is not None else 'неизвестно'} ч.",
        "",
        "**Важно:** советы не являются симуляцией DPS; мета по гайдам 12.1.5 проверялась 06.11.2026.",
        "",
        "## Искать улучшения",
        "",
        "| Приоритет | Слот | Сейчас | Что делать |",
        "|---:|---|---:|---|",
    ]
    for r in recs:
        lines.append(f"| {r['rank']} | {r['slot_name']} | {r['item_level']} | {r['action']} |")
    lines += ["", "## Подробности", ""]
    for r in recs:
        lines += [
            f"### {r['rank']}. {r['slot_name']} — {r['item_level']} ilvl",
            f"**Цель:** {r['target']}",
            f"**Почему:** {r['why']}",
            f"**Где:** {r['where']}",
            "",
        ]
    lines += ["## Что сохранить и улучшать", ""]
    for r in keep:
        lines += [f"- **{r['slot_name']} {r['item_level']}:** {r['action']}. {r['why']} {r['next']}"]
    lines += ["", "## Ограничения", ""]
    for limitation in result["limitations"]:
        lines.append(f"- {limitation}")
    lines += ["", "## Источники (проверены 06.11.2026)", ""]
    for src in SOURCES:
        lines.append(f"- [{src['title']}]({src['url']})")
    (ROOT / "gear-advice.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(
        f"Gear analysis written: {len(recs)} possible upgrades, "
        f"{len(keep)} protected slots, 4p={has_four_piece}, source age={stale_hours}h"
    )


if __name__ == "__main__":
    main()
