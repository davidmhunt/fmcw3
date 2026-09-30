"""Check DigiKey stock/lifecycle for the fmcw3 BOM (parts.csv).

Credentials are read from ../.digikey.env (the fmcw3 repo root; gitignored).
Usage: python parts/check_digikey.py [--boards N]   (run from the fmcw3 repo root)
"""
import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = HERE.parent / ".digikey.env"
BASE = "https://api.digikey.com"


def load_env(path):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from {url}: {e.read().decode()[:300]}")


def get_token(cid, secret):
    body = urllib.parse.urlencode(
        {"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}
    ).encode()
    tok = post(f"{BASE}/v1/oauth2/token", body,
               {"Content-Type": "application/x-www-form-urlencoded"})
    return tok["access_token"]


def search(term, cid, token):
    body = json.dumps({"Keywords": term, "Limit": 5}).encode()
    return post(f"{BASE}/products/v4/search/keyword", body, {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": cid,
        "X-DIGIKEY-Locale-Site": "US",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "USD",
    }).get("Products", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=5)
    args = ap.parse_args()
    env = load_env(ENV)
    cid, secret = env["DIGIKEY_CLIENT_ID"], env["DIGIKEY_CLIENT_SECRET"]
    token = get_token(cid, secret)

    rows = list(csv.DictReader((HERE / "parts.csv").open()))
    out = []
    for r in rows:
        need = int(r["qty"]) * args.boards
        prods = search(r["search_term"], cid, token)
        # Prefer an exact MPN match, else the first hit.
        exact = [p for p in prods if p.get("ManufacturerProductNumber", "").upper()
                 == r["search_term"].upper()]
        p = (exact or prods or [None])[0]
        if p is None:
            out.append({**r, "need": need, "match": "NO RESULT", "mpn": "", "mfr": "",
                        "status": "", "stock": 0, "ok": "NO", "dk_url": ""})
        else:
            stock = p.get("QuantityAvailable", 0) or 0
            status = (p.get("ProductStatus") or {}).get("Status", "?")
            out.append({**r, "need": need,
                        "match": "exact" if exact else "fuzzy",
                        "mpn": p.get("ManufacturerProductNumber", ""),
                        "mfr": (p.get("Manufacturer") or {}).get("Name", ""),
                        "status": status, "stock": stock,
                        "ok": "yes" if stock >= need and status == "Active" else "CHECK",
                        "dk_url": p.get("ProductUrl", "")})
        time.sleep(0.5)  # stay well under the rate limit

    cols = ["refs", "qty", "need", "value", "search_term", "match", "mpn", "mfr",
            "status", "stock", "ok", "dk_url", "notes"]
    with (HERE / "availability.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({c: o.get(c, "") for c in cols} for o in out)

    print(f"{'value':26} {'match':9} {'status':14} {'stock':>8} {'need':>5} ok")
    for o in out:
        print(f"{o['value'][:26]:26} {o['match']:9} {str(o['status'])[:14]:14} "
              f"{o['stock']:>8} {o['need']:>5} {o['ok']}")
    print(f"\nWrote {HERE / 'availability.csv'} (boards={args.boards})")


if __name__ == "__main__":
    main()
