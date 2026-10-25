#!/usr/bin/env python3
"""Download an official Samsung monitor firmware image and verify it.

The script reads the public support page for a model, finds the firmware
entries in the embedded catalogue, picks the newest version, downloads the
archive from the Samsung download centre, extracts the image and checks the
[XXXX] tag in the file name against the checksum.

Nothing is redistributed: the file comes from Samsung's own CDN.

Usage:
  fetch_fw.py --page https://www.samsung.com/hk_en/support/model/LS32A700NWCXXK/ -o fw/
  fetch_fw.py --page <url> --list            # only show what is available
  fetch_fw.py --url <direct zip url> -o fw/  # skip the catalogue
"""
import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

UA = "Mozilla/5.0 (compatible; samsung-monitor-fw/1.0)"
TAG_RE = re.compile(r"\[([0-9A-Fa-f]{4})\]")
VER_RE = re.compile(r"-(\d+)\.(\d+)")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def extract_catalogue(html: str):
    """Return the embedded {"softwares": [...]} object, or None."""
    start = html.find('{"softwares"')
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def firmware_entries(catalogue: dict):
    out = []
    for item in catalogue.get("softwares", []):
        name = item.get("fileName", "")
        if item.get("contentsTypeCode") != "FM":
            continue
        m = VER_RE.search(name)
        if not m:
            continue
        out.append({
            "version": (int(m.group(1)), int(m.group(2))),
            "file": name,
            "url": item.get("downloadUrl", ""),
            "date": item.get("fileModifiedDate", ""),
        })
    out.sort(key=lambda e: e["version"], reverse=True)
    return out


def pick_image(zip_bytes: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".bin")]
        if not names:
            raise SystemExit("archive has no .Bin file")
        name = names[0]
        return name, z.read(name)


def verify(name: str, data: bytes) -> bool:
    computed = sum(data) & 0xFFFF
    m = TAG_RE.search(name)
    if not m:
        print(f"  no [TAG] in name; computed [{computed:04X}]", file=sys.stderr)
        return False
    ok = int(m.group(1), 16) == computed
    print(f"  {name}: tag {m.group(1).upper()} vs computed {computed:04X} "
          f"-> {'OK' if ok else 'MISMATCH'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", help="Samsung support page for the model")
    ap.add_argument("--url", help="direct archive URL")
    ap.add_argument("-o", "--out", default="fw", help="output directory (default: fw)")
    ap.add_argument("--list", action="store_true", help="list entries and exit")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.url:
        name, data = pick_image(fetch(args.url))
        target = outdir / name
        target.write_bytes(data)
        print(f"saved {target}")
        return 0 if verify(name, data) else 1

    if not args.page:
        ap.error("need --page or --url")

    html = fetch(args.page).decode("utf-8", "replace")
    cat = extract_catalogue(html)
    if not cat:
        print("catalogue not found on the page", file=sys.stderr)
        return 1

    entries = firmware_entries(cat)
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
    target = outdir / name
    target.write_bytes(data)
    print(f"saved {target}  ({len(data)} bytes)")
    print(f"version in image: ", end="")
    m = re.search(rb"M-A[0-9A-Z]{6,}-\d+\.\d+", data)
    print(m.group().decode() if m else "<not found>")
    return 0 if verify(name, data) else 1


if __name__ == "__main__":
    sys.exit(main())
