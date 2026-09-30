#!/usr/bin/env python3
"""Fetch the fmcw3 datasheet library described by manifest.csv (stdlib only).

Usage (from anywhere):  python3 hardware/fmcw3/parts/datasheets/fetch.py

For each manifest row it downloads `url` (then each `|`-separated `mirrors`
URL) into this directory as `local_filename`, validates the download (real PDF
magic bytes; for .html rows, not a bot-challenge page), and writes sha256 /
retrieved / status back to manifest.csv.  Files you drop in by hand are picked
up as status `manual`.  Idempotent: re-running changes nothing unless a file
appeared, vanished or was fetched.  Anything still missing is printed as a
"pull by hand" list (URL -> exact filename to save as).  No credentials.
"""
import csv, hashlib, sys, time, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.csv"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
RETRIES, TIMEOUT = 2, 30
CHALLENGE = (b"just a moment", b"cf-chl", b"access denied", b"enable javascript",
             b"attention required", b"captcha")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def valid(data, name):
    """Return (ok, reason)."""
    if name.lower().endswith(".pdf"):
        if data[:5] != b"%PDF-":
            return False, "not a PDF (no %PDF- magic)"
        if len(data) < 5000:
            return False, "PDF suspiciously small"
        return True, ""
    head = data[:20000].lower()
    if len(data) < 2000 or any(m in head for m in CHALLENGE):
        return False, "HTML looks like a challenge/error page"
    return True, ""


def download(url):
    if url.startswith("//"):
        url = "https:" + url
    last = "?"
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read(), ""
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (401, 403, 404, 410):
                break
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__
        time.sleep(1 + attempt)
    return None, last


def process(row):
    """Mutate row in place; return a log string."""
    name = row["local_filename"]
    path = HERE / name
    today = datetime.date.today().isoformat()
    if path.is_file():
        data = path.read_bytes()
        ok, why = valid(data, name)
        if ok:
            digest = hashlib.sha256(data).hexdigest()
            if row["status"] == "fetched" and row["sha256"] == digest:
                return "ok (present)"
            if row["status"] == "fetched":
                row["sha256"] = digest
                return "fetched file changed on disk: sha256 updated"
            if row["status"] != "manual" or row["sha256"] != digest:
                row["status"], row["sha256"] = "manual", digest
                row["retrieved"] = row["retrieved"] or today
            return "manual (present)"
        path.unlink()  # invalid leftover
        print(f"  {name}: removed invalid file ({why})", file=sys.stderr)
    tried = []
    for url in [row["url"]] + [m for m in row["mirrors"].split("|") if m]:
        data, err = download(url)
        if data is None:
            tried.append(f"{url}: {err}")
            continue
        ok, why = valid(data, name)
        if ok:
            path.write_bytes(data)
            row["status"], row["sha256"], row["retrieved"] = "fetched", sha256(path), today
            return f"fetched from {url}"
        tried.append(f"{url}: {why}")
    row["status"], row["sha256"], row["retrieved"] = "unreachable", "", ""
    return "unreachable: " + " | ".join(tried)


def main():
    with open(MANIFEST, newline="") as f:
        rd = csv.DictReader(f)
        cols, rows = rd.fieldnames, list(rd)
    with ThreadPoolExecutor(8) as ex:
        logs = list(ex.map(process, rows))
    for r, log in zip(rows, logs):
        print(f"[{r['status']:>11}] {r['local_filename']}  {log}")
    with open(MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    n = {s: sum(r["status"] == s for r in rows) for s in ("fetched", "manual", "unreachable")}
    print(f"\nfetched={n['fetched']} manual={n['manual']} unreachable={n['unreachable']} "
          f"total={len(rows)}")
    todo = [r for r in rows if r["status"] == "unreachable"]
    if todo:
        print(f"\nPULL BY HAND: save each file into {HERE} with exactly this name, "
              "then re-run fetch.py:")
        for r in todo:
            print(f"  {r['url']}\n      -> {r['local_filename']}")


if __name__ == "__main__":
    main()
