#!/usr/bin/env python3
"""Download an official Samsung monitor firmware image and verify it.

The script reads the public support page for a model, decodes the embedded
catalogue with json.JSONDecoder, takes the newest firmware version, downloads
the archive from the Samsung download centre, extracts the image, and checks
the [XXXX] tag against the checksum.

Nothing is redistributed: the file comes from Samsung's own server.

Usage:
  fetch_fw.py --model LS32A700NWIXCI -o fw/   find the region page automatically
  fetch_fw.py --model LS32A700NWIXCI --list   show what is available
  fetch_fw.py --page <url> -o fw/             use a known support page
  fetch_fw.py --url <direct zip url> -o fw/   skip the catalogue
"""
import argparse
import concurrent.futures
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from fwtool import parse_tag, read_version, tag

UA = "Mozilla/5.0 (compatible; samsung-monitor-fw/1.0)"

# Region pages are checked in this order. Not every region publishes the
# catalogue, and some answer 200 with a "model not found" body.
REGIONS = [
    "ru", "ua", "hk_en", "us", "uk", "de", "fr", "it", "es", "pl",
    "nl", "se", "in", "br", "mx", "cl", "co", "pe", "ar", "ae",
    "sa", "za", "tr", "th", "sg", "my", "id", "ph", "vn", "au",
    "nz", "cn", "tw", "jp", "kz", "by",
]
MODEL_URL = "https://www.samsung.com/{region}/support/model/{model}/"
CATALOGUE_KEY = '{"softwares"'


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def probe_model(model: str, regions=None):
    """Return (region, html) for the first region that publishes the catalogue."""
    regions = regions or REGIONS

    def get(region):
        url = MODEL_URL.format(region=region, model=model)
        try:
            html = fetch(url).decode("utf-8", "replace")
        except Exception:
            return None
        return html if CATALOGUE_KEY in html else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(zip(regions, pool.map(get, regions)))
    for region in regions:                     # keep the preference order
        if results.get(region):
            return region, results[region]
    return None, None


def extract_catalogue(html: str):
    """Decode the embedded {"softwares": [...]} object, or return None."""
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        pos = html.find(CATALOGUE_KEY, pos)
        if pos < 0:
            return None
        try:
            value, _ = decoder.raw_decode(html, pos)
        except json.JSONDecodeError:
            pos += 1
            continue
        if isinstance(value, dict) and "softwares" in value:
            return value
        pos += 1


def parse_version(text: str):
    """'M-A8000SGZA-1014.0[288E]_USB.zip' -> (1014, 0); None if not a version."""
    head, sep, tail = text.rpartition("-")
    if not sep or not head.startswith("M-"):
        return None
    number = tail.split("[")[0]
    major, sep, minor = number.partition(".")
    if not sep or not major.isdigit() or not minor.isdigit():
        return None
    return int(major), int(minor)


def firmware_entries(catalogue: dict):
    out = []
    for item in catalogue.get("softwares", []):
        name = item.get("fileName", "")
        if item.get("contentsTypeCode") != "FM":
            continue
        version = parse_version(name)
        if not version:
            continue
        out.append({
            "version": version,
            "file": name,
            "url": item.get("downloadUrl", ""),
            "date": item.get("fileModifiedDate", ""),
        })
    out.sort(key=lambda e: e["version"], reverse=True)
    return out


def pick_image(zip_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".bin")]
        if not names:
            raise SystemExit("archive has no .Bin file")
        return names[0], z.read(names[0])


def verify(name: str, data: bytes) -> bool:
    computed = tag(data)
    parsed = parse_tag(name)
    if parsed is None:
        print(f"  no [XXXX] tag in the name; computed [{computed:04X}]", file=sys.stderr)
        return False
    print(f"  {name}: tag {parsed:04X} vs computed {computed:04X} "
          f"-> {'OK' if parsed == computed else 'MISMATCH'}")
    return parsed == computed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="model code, for example LS32A700NWIXCI")
    ap.add_argument("--page", help="Samsung support page for the model")
    ap.add_argument("--url", help="direct archive URL")
    ap.add_argument("-o", "--out", default="fw", help="output directory (default: fw)")
    ap.add_argument("--list", action="store_true", help="list entries and exit")
    args = ap.parse_args()

    outdir = Path(args.out)

    if args.url:
        name, data = pick_image(fetch(args.url))
        outdir.mkdir(parents=True, exist_ok=True)
        target = outdir / name
        target.write_bytes(data)
        print(f"saved {target}")
        return 0 if verify(name, data) else 1

    if args.model:
        print(f"looking for {args.model} across {len(REGIONS)} region pages ...")
        region, html = probe_model(args.model)
        if not html:
            print(f"no region page with a firmware catalogue for {args.model}",
                  file=sys.stderr)
            return 1
        print(f"catalogue found: {region}")
    elif args.page:
        html = fetch(args.page).decode("utf-8", "replace")
    else:
        ap.error("need --model, --page or --url")

    catalogue = extract_catalogue(html)
    if not catalogue:
        print("catalogue not found on the page", file=sys.stderr)
        return 1

    entries = firmware_entries(catalogue)
    if not entries:
        print("no firmware entries for this model", file=sys.stderr)
        return 1

    for e in entries:
        print(f"  {e['version'][0]}.{e['version'][1]:<4} {e['date']:<12} {e['file']}")
    if args.list:
        return 0

    best = entries[0]
    print(f"\ndownloading {best['file']} ...")
    name, data = pick_image(fetch(best["url"]))
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / name
    target.write_bytes(data)
    print(f"saved {target}  ({len(data)} bytes)")
    version, _ = read_version(data)
    print(f"version in image: {version or '<not found>'}")
    return 0 if verify(name, data) else 1


if __name__ == "__main__":
    sys.exit(main())
