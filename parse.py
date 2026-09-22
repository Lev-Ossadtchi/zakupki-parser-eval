"""Разбор страниц поиска ЕИС в таблицу закупок.

Только стандартная библиотека: ни bs4, ни lxml. Каждое поле берётся по своему
якорю в разметке, а не по номеру колонки, — вёрстка ЕИС меняется, и привязка
к порядку блоков ломается первой.
"""
import csv, html, json, re
from pathlib import Path

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "out"

ENTRY = re.compile(r'<div class="search-registry-entry-block.*?</div>\s*</div>\s*</div>\s*</div>\s*</div>', re.S)
BLOCK = re.compile(r'<div class="search-registry-entry-block', re.S)

# Внутри тега может лежать атрибут data-tooltip со своей разметкой:
# data-tooltip='<span class="custom-tooltiptext">...</span>'. Наивное [^>]*>
# обрывается на угловой скобке внутри кавычек и уносит в захват половину
# подсказки вместо текста блока, поэтому конец открывающего тега ищется
# с учётом кавычек: сначала доедаем значение class, потом остальные атрибуты.
ATTRS = r'(?:[^>"\']|"[^"]*"|\'[^\']*\')*'
TAG_END = r'[^"]*"' + ATTRS + r'>'

RE_LAW_METHOD = re.compile(r'registry-entry__header-top__title' + TAG_END + r'\s*(.*?)\s*</div>', re.S)
RE_REG = re.compile(r'registry-entry__header-mid__number">\s*<a[^>]*href="([^"]+)"[^>]*>\s*№\s*(\d+)', re.S)
RE_STATUS = re.compile(r'registry-entry__header-mid__title' + TAG_END + r'\s*(.*?)\s*</div>', re.S)
RE_BODY = re.compile(r'registry-entry__body-title' + TAG_END + r'\s*(.*?)\s*</div>\s*'
                     r'<div class="registry-entry__body-(?:value|href)' + TAG_END + r'\s*(.*?)\s*</div>', re.S)
RE_PRICE = re.compile(r'price-block__value' + TAG_END + r'\s*(.*?)\s*</div>', re.S)
RE_DATA = re.compile(r'data-block__title' + TAG_END + r'\s*(.*?)\s*</div>\s*'
                     r'<div class="data-block__value' + TAG_END + r'\s*(.*?)\s*</div>', re.S)

# Одно и то же поле ЕИС подписывает по-разному в зависимости от типа закупки:
# при централизованной закупке «Заказчик» превращается в «Организация,
# осуществляющая размещение». Привязка к одной подписи теряет заказчика
# у каждой пятой строки.
CUSTOMER_LABELS = ("Заказчик", "Организация, осуществляющая размещение",
                   "Организация, осуществляющая закупку", "Уполномоченный орган")
SUBJECT_LABELS = ("Объект закупки", "Наименование объекта закупки", "Предмет контракта")

TAGS = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")


def clean(s):
    return SPACES.sub(" ", html.unescape(TAGS.sub(" ", s))).strip()


def money(s):
    """«32 368,00 ₽» -> 32368.0. Неразрывные пробелы в ЕИС встречаются всех сортов."""
    t = clean(s).replace("\xa0", " ").replace("₽", "")
    t = re.sub(r"[^\d,.\-]", "", t).replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def pick(body, labels):
    for k in labels:
        if body.get(k):
            return body[k]
    return ""


def split_entries(page):
    """Режем страницу по началу карточек: вложенных div слишком много для одной регулярки."""
    starts = [m.start() for m in BLOCK.finditer(page)]
    return [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])]


def parse_entry(e):
    m = RE_REG.search(e)
    if not m:
        return None
    href, reg = m.group(1), m.group(2)

    lm = clean(RE_LAW_METHOD.search(e).group(1)) if RE_LAW_METHOD.search(e) else ""
    law, method = "", lm
    if lm.startswith(("44-ФЗ", "223-ФЗ")):
        law, method = lm.split(" ", 1) if " " in lm else (lm, "")

    body = {clean(k): clean(v) for k, v in RE_BODY.findall(e)}
    dates = {clean(k): clean(v) for k, v in RE_DATA.findall(e)}
    price = RE_PRICE.search(e)
    st = RE_STATUS.search(e)

    org = re.search(r'organizationCode=(\d+)', e)
    return {
        "reg_number": reg,
        "law": law,
        "method": method,
        "status": clean(st.group(1)) if st else "",
        "subject": pick(body, SUBJECT_LABELS),
        "customer": pick(body, CUSTOMER_LABELS),
        "customer_code": org.group(1) if org else "",
        "price_rub": money(price.group(1)) if price else None,
        "published": dates.get("Размещено", ""),
        "updated": dates.get("Обновлено", ""),
        "deadline": dates.get("Окончание подачи заявок", ""),
        "url": href,
    }


def parse_all():
    rows, seen = [], set()
    for f in sorted(RAW.glob("search_*.html")):
        page = f.read_text(encoding="utf-8")
        for e in split_entries(page):
            r = parse_entry(e)
            if r and r["reg_number"] not in seen:
                seen.add(r["reg_number"])
                rows.append(r)
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    rows = parse_all()
    (OUT / "notices.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "notices.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)

    filled = {k: sum(1 for r in rows if r[k] not in ("", None)) for k in rows[0]}
    print(f"извещений разобрано: {len(rows)}")
    print(f"{'поле':<16}{'заполнено':>11}")
    print("-" * 27)
    for k, v in filled.items():
        print(f"{k:<16}{v:>7} / {len(rows)}")
    prices = [r["price_rub"] for r in rows if r["price_rub"]]
    print(f"\nНМЦК: от {min(prices):,.0f} до {max(prices):,.0f} ₽".replace(",", " "))


if __name__ == "__main__":
    main()
