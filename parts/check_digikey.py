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


def dk_pn(p):
    """DigiKey PN: prefer the cut-tape / single-unit variant, else the first variation."""
    vs = p.get("ProductVariations") or []
    for v in vs:
        if "Cut Tape" in (v.get("PackageType") or {}).get("Name", ""):
            return v.get("DigiKeyProductNumber", "")
    return vs[0].get("DigiKeyProductNumber", "") if vs else ""


def lifecycle(dk_status):
    """Map DigiKey's ProductStatus to the Active / Obsolete / NFND buckets."""
    s = (dk_status or "").lower()
    if s == "active":
        return "Active"
    if "not for new" in s or "last time" in s:
        return "NFND"
    return "Obsolete"  # Obsolete, Discontinued at DigiKey


def lookup(term, cid, token):
    prods = search(term, cid, token)
    exact = [p for p in prods if p.get("ManufacturerProductNumber", "").upper() == term.upper()]
    return exact[0] if exact else None, prods


def pkg_of(p):
    for x in p.get("Parameters", []):
        if x.get("ParameterText") == "Supplier Device Package":
            return x.get("ValueText", "")
    return ""


def write_fields(out):
    """fields_to_apply.csv: one row per schematic ref, for Hardware to write into symbol fields.
    kind=mpn rows with a resolved MPN carry Manufacturer/MPN/DigiKey PN (Status stays blank when
    Active).  Obsolete/NFND/needs-David rows carry a Status pointing at the memo.  Generic rows are
    spec-only (no MPN).  DNP groups and PCB features (vias, test points, holes, coupler) are omitted."""
    cols = ["ref", "kind", "Manufacturer", "MPN", "DigiKey PN", "Status", "Package", "Tolerance",
            "Voltage", "Dielectric", "spec_only", "basis"]
    memo = "see docs/hardware/fmcw3 memo"
    rows = []
    for o in out:
        if o["kind"] in ("dnp", "nopart"):
            continue
        for ref in o["refs"].split(";"):
            r = dict.fromkeys(cols, "")
            r["ref"], r["kind"] = ref, o["kind"]
            if o["kind"] == "mpn":
                r["spec_only"] = "no"
                if o["status"] in ("Active", "Obsolete", "NFND"):
                    r.update(Manufacturer=o["mfr"], MPN=o["mpn"], **{"DigiKey PN": o["dkpn"]})
                    r["basis"] = "exact MPN, DigiKey lookup"
                if o["status"] != "Active":
                    r["Status"] = {"Obsolete": f"Obsolete: {memo}", "NFND": f"NFND: {memo}",
                                   "needs-David": f"needs-David: {memo}",
                                   "No-result": f"No-result: {memo}"}[o["status"]]
            else:
                r.update(spec_only="yes", Package=o["package"], Tolerance=o["tolerance"],
                         Voltage=o["voltage"], Dielectric=o["dielectric"],
                         basis="value+footprint from schematic; voltage inferred from net; tolerance/dielectric unspecified")
                if o["status"] == "needs-David":
                    r["Status"] = f"needs-David: {memo}"
            rows.append(r)
    with (HERE / "fields_to_apply.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=5)
    args = ap.parse_args()
    env = load_env(ENV)
    cid, secret = env["DIGIKEY_CLIENT_ID"], env["DIGIKEY_CLIENT_SECRET"]
    token = get_token(cid, secret)

    rows = list(csv.DictReader((HERE / "parts.csv").open()))
    cols = ["refs", "qty", "need", "value", "footprint", "kind", "status", "dk_status", "mpn", "mfr",
            "dkpn", "stock", "ok", "lead_weeks", "dk_package", "datasheet", "dk_url", "match",
            "candidates", "needs_david", "package", "tolerance", "voltage", "dielectric",
            "tolerance_hint", "dielectric_hint", "notes"]
    out = []
    for r in rows:
        need = int(r["qty"]) * args.boards
        o = {c: r.get(c, "") for c in cols}
        o["need"] = need
        kind = r["kind"]
        if kind != "mpn":
            o.update(status={"generic": "needs-David" if r["needs_david"] else "generic-spec-only",
                             "dnp": "DNP", "nopart": "no-part"}[kind], ok="n/a", match="", stock="")
        elif r["needs_david"]:
            found = []
            for term in filter(None, r["candidates"].split("|")):
                p, _ = lookup(term, cid, token)
                time.sleep(0.5)
                if p is None:
                    found.append(f"{term} [no result]")
                else:
                    st = (p.get("ProductStatus") or {}).get("Status", "?")
                    found.append(f"{term} [{st}, stock {p.get('QuantityAvailable') or 0}, {dk_pn(p)}]")
            o.update(status="needs-David", candidates="; ".join(found), ok="n/a", match="candidates")
        else:
            p, prods = lookup(r["search_term"], cid, token)
            time.sleep(0.5)
            if p is None:
                o.update(status="No-result", match="NO RESULT", ok="NO", stock=0)
            else:
                stock = p.get("QuantityAvailable", 0) or 0
                dk_status = (p.get("ProductStatus") or {}).get("Status", "?")
                st = lifecycle(dk_status)
                o.update(status=st, dk_status=dk_status, match="exact",
                         mpn=p.get("ManufacturerProductNumber", ""),
                         mfr=(p.get("Manufacturer") or {}).get("Name", ""),
                         dkpn=dk_pn(p), stock=stock,
                         ok="yes" if stock >= need and st == "Active" else "CHECK",
                         lead_weeks=p.get("ManufacturerLeadWeeks", ""), dk_package=pkg_of(p),
                         datasheet=p.get("DatasheetUrl", ""), dk_url=p.get("ProductUrl", ""))
        out.append(o)

    with (HERE / "availability.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)

    write_fields(out)

    print(f"{'refs':28} {'value':22} {'status':18} {'stock':>8} {'need':>5} ok")
    for o in out:
        print(f"{o['refs'][:28]:28} {o['value'][:22]:22} {o['status'][:18]:18} "
              f"{str(o['stock']):>8} {o['need']:>5} {o['ok']}")
    from collections import Counter
    print("\n", dict(Counter(o["status"] for o in out)))
    print(f"Wrote {HERE / 'availability.csv'} (boards={args.boards})")


if __name__ == "__main__":
    main()
