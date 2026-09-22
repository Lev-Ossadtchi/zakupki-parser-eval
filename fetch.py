"""Скачивает страницы поиска ЕИС и карточки извещений в raw/.

Сеть нужна только здесь. Всё скачанное лежит на диске, поэтому разбор и
проверка воспроизводятся офлайн и не зависят от того, что сегодня показывает
сайт.

Про сертификаты: zakupki.gov.ru выдан НУЦ Минцифры, которого нет в доверенных
хранилищах macOS и Python, поэтому обычный запрос падает с
CERTIFICATE_VERIFY_FAILED. Проверка отключается явно и только для этого
источника — данные здесь открытые и не приватные.
"""
import ssl, sys, time, urllib.request
from pathlib import Path

RAW = Path(__file__).parent / "raw"
BASE = "https://zakupki.gov.ru"
SEARCH = (BASE + "/epz/order/extendedsearch/results.html"
          "?fz44=on&pageNumber={page}&recordsPerPage=_50&sortDirection=false")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "ru-RU,ru;q=0.9"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return r.read().decode("utf-8", "replace")


def fetch_pages(n):
    RAW.mkdir(exist_ok=True)
    for p in range(1, n + 1):
        dst = RAW / f"search_{p:02d}.html"
        if dst.exists():
            print(f"страница {p}: уже есть")
            continue
        dst.write_text(get(SEARCH.format(page=p)), encoding="utf-8")
        print(f"страница {p}: {dst.stat().st_size // 1024} КБ")
        time.sleep(1.2)


def fetch_cards(urls):
    (RAW / "cards").mkdir(parents=True, exist_ok=True)
    for i, (reg, url) in enumerate(urls, 1):
        dst = RAW / "cards" / f"{reg}.html"
        if dst.exists():
            continue
        try:
            dst.write_text(get(BASE + url if url.startswith("/") else url), encoding="utf-8")
        except Exception as e:
            print(f"{reg}: {e}")
            continue
        print(f"{i}/{len(urls)} {reg}: {dst.stat().st_size // 1024} КБ")
        time.sleep(1.2)


if __name__ == "__main__":
    fetch_pages(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
