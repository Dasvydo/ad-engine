#!/usr/bin/env python3
"""Pull the real click destination - and what the ad shows - out of a Meta preview.

    python preview_destination.py "<preview_url>" [--expect "<intended url>"]

`ads_get_creatives` doesn't return `link_url` for link ads (they're stored as
Page posts), so the rendered preview is the only first-hand record of where the
click goes. The preview page embeds the ad as JSON: the button's `link_url` is
Meta's link-shim (l.facebook.com/l.php?u=<destination>), double-escaped. This
reads those structured fields; it does not scrape every URL on the page, because
the page's own scripts are full of unrelated links.

Prints: destination, CTA, the caption (display link), headline and description.
With --expect, exits 1 unless host, path and every utm_ parameter match.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import urllib.request
from urllib.parse import parse_qs, urlparse


def ctx() -> ssl.SSLContext:
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not ca and os.path.exists("/root/.ccr/ca-bundle.crt"):  # Claude cloud proxy
        ca = "/root/.ccr/ca-bundle.crt"
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


def js_str(raw: str) -> str:
    """Decode one JSON string body (handles \\/ and \\u0025 escapes)."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace("\\/", "/")


def unshim(url: str) -> str:
    p = urlparse(url)
    if p.netloc.endswith("facebook.com") and p.path.startswith("/l.php"):
        u = parse_qs(p.query).get("u")
        if u:
            return u[0]
    return url


def field(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return js_str(m.group(1)) if m else None


def utm_key(u: str) -> tuple:
    p = urlparse(u)
    utm = {k: v for k, v in parse_qs(p.query).items() if k.startswith("utm_")}
    return p.netloc, p.path or "/", tuple(sorted((k, tuple(v)) for k, v in utm.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("preview_url")
    ap.add_argument("--expect")
    a = ap.parse_args()

    # ads_get_ad_preview hands the URL back HTML-escaped (&amp;t=...); undo that
    url = html.unescape(a.preview_url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx()))
    text = opener.open(req, timeout=30).read().decode("utf-8", "replace")

    dests: list[str] = []
    for raw in re.findall(r'"link_url":"((?:[^"\\]|\\.)*)"', text):
        d = unshim(js_str(raw))
        if d and d not in dests and not urlparse(d).netloc.endswith("facebook.com"):
            dests.append(d)

    cta = field(text, r'"link_type":"([A-Z_]+)"')
    caption = field(text, r'"linkDisplay":\{"text":"((?:[^"\\]|\\.)*)"')
    headline = field(text, r'"linkTitleWithMaxLine":\{"text":"((?:[^"\\]|\\.)*)"')
    desc = field(text, r'"linkDescription":"((?:[^"\\]|\\.)*)"')

    if not dests:
        print("Destination: NOT FOUND in the preview.")
        print("  The preview link may have expired - request a fresh one with ads_get_ad_preview.")
        print("RESULT: FAIL - destination could not be proven")
        return 1

    print("Destination Meta sends the click to:")
    for d in dests:
        print(f"  {d}")
    print(f"Button     : {cta or '(not found)'}")
    print(f"Caption    : {caption or '(not found)'}")
    print(f"Headline   : {headline or '(not found)'}")
    print(f"Description: {desc or '(none)'}")
    if caption and "utm_" in caption:
        print("⚠️  the caption prints the tracking string - set display_link on the next creative")
    if len(dests) > 1:
        print("⚠️  more than one destination in one preview - check which one the button uses")

    if a.expect:
        ok = any(utm_key(d) == utm_key(a.expect) for d in dests)
        print("RESULT:", "PASS - destination matches" if ok else f"FAIL - expected {a.expect}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
