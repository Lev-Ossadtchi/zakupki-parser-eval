"""Сверка разобранных полей с карточкой извещения.

Список и карточка — разные страницы с разной вёрсткой, поэтому карточка здесь
работает независимым эталоном: если парсер списка сдвинул поле или подобрал
не ту подпись, совпадения не будет.

Выборка случайная, но с фиксированным зерном — цифры в README воспроизводятся.
"""
import json, random, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch import fetch_cards                      # noqa: E402
from parse import clean, money                     # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "out"
CARDS = ROOT / "raw" / "cards"
SAMPLE = 60
SEED = 20260922

SECTION = re.compile(r'section__title[^>]*>\s*(.*?)\s*</span>\s*'
                     r'<span class="section__info"[^>]*>\s*(.*?)\s*</span>', re.S)
MAIN = re.compile(r'cardMainInfo__title[^>]*>\s*(.*?)\s*</span>\s*'
                  r'<span class="cardMainInfo__content[^"]*"[^>]*>\s*(.*?)\s*</span>', re.S)

CARD_SUBJECT = ("Наименование объекта закупки", "Предмет контракта")
CARD_METHOD = ("Способ определения поставщика (подрядчика, исполнителя)",
               "Способ определения поставщика")
CARD_DEADLINE = ("Дата и время окончания срока подачи заявок",
                 "Дата и время окончания подачи заявок")
CARD_PRICE = ("Начальная (максимальная) цена контракта",
              "Начальная (максимальная) цена контрактов")


def card_fields(html_text):
    s = {clean(k): clean(v) for k, v in SECTION.findall(html_text)}
    m = {clean(k): clean(v) for k, v in MAIN.findall(html_text)}
    org = re.search(r'Размещение осуществляет.*?organizationCode=(\d+)', html_text, re.S)

    def pick(d, keys):
        for k in keys:
            if d.get(k):
                return d[k]
        return ""

    deadline = pick(s, CARD_DEADLINE) or m.get("Окончание подачи заявок", "")
    return {
        "subject": pick(s, CARD_SUBJECT),
        "method": pick(s, CARD_METHOD),
        "price_rub": money(pick(s, CARD_PRICE) or m.get("Начальная цена", "")),
        "deadline": (re.match(r"\d{2}\.\d{2}\.\d{4}", deadline) or [""])[0]
                    if re.match(r"\d{2}\.\d{2}\.\d{4}", deadline) else deadline,
        "published": m.get("Размещено", ""),
        "customer_code": org.group(1) if org else "",
    }


def same(field, a, b):
    if field == "price_rub":
        return a is not None and b is not None and abs(a - b) < 0.01
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    return a == b


def main():
    rows = json.loads((OUT / "notices.json").read_text(encoding="utf-8"))
    rnd = random.Random(SEED)
    sample = rnd.sample(rows, min(SAMPLE, len(rows)))
    fetch_cards([(r["reg_number"], r["url"]) for r in sample])

    fields = ["subject", "method", "price_rub", "deadline", "published", "customer_code"]
    stat = {f: {"ok": 0, "diff": 0, "no_ref": 0} for f in fields}
    diffs, checked = [], 0

    for r in sample:
        p = CARDS / f"{r['reg_number']}.html"
        if not p.exists():
            continue
        checked += 1
        ref = card_fields(p.read_text(encoding="utf-8"))
        for f in fields:
            want, got = ref[f], r[f]
            if want in ("", None):
                stat[f]["no_ref"] += 1        # поля нет в карточке — сверять не с чем
            elif same(f, want, got):
                stat[f]["ok"] += 1
            else:
                stat[f]["diff"] += 1
                diffs.append({"reg": r["reg_number"], "field": f,
                              "из_списка": got, "из_карточки": want})

    (OUT / "verification.json").write_text(json.dumps(
        {"sample": checked, "seed": SEED, "stat": stat, "diffs": diffs},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"сверено извещений: {checked} (случайная выборка, зерно {SEED})\n")
    print(f"{'поле':<16}{'совпало':>9}{'разошлось':>11}{'нет в карточке':>16}{'точность':>10}")
    print("-" * 62)
    for f in fields:
        s = stat[f]
        base = s["ok"] + s["diff"]
        acc = f"{100 * s['ok'] / base:.1f}%" if base else "—"
        print(f"{f:<16}{s['ok']:>9}{s['diff']:>11}{s['no_ref']:>16}{acc:>10}")
    total_ok = sum(stat[f]["ok"] for f in fields)
    total = sum(stat[f]["ok"] + stat[f]["diff"] for f in fields)
    print("-" * 62)
    print(f"всего сверок: {total}, совпало {total_ok} ({100 * total_ok / total:.1f}%)")
    if diffs:
        print(f"\nрасхождения ({len(diffs)}) выписаны в out/verification.json:")
        for d in diffs[:10]:
            print(f"  {d['reg']} {d['field']}: список «{str(d['из_списка'])[:60]}» "
                  f"/ карточка «{str(d['из_карточки'])[:60]}»")


if __name__ == "__main__":
    main()
