#!/usr/bin/env python3
"""Check an ad's destination URL the way a paid click will hit it.

    python verify_destination.py "<url with utm params>" [--pixel <id>]

Walks the redirect chain hop by hop (a checker that follows redirects silently is
how a 301 to the wrong site passed before), then on the final page reports the
status, the <title>, whether the UTM parameters survived the trip, and whether
the Meta pixel loads - from the HTML and from same-origin JS bundles, because
SPAs inject it from script.

Exit 0 = safe to put in an ad. Exit 1 = don't.
"""
from __future__ import annotations

import argparse
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urljoin, urlparse

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"


def ctx() -> ssl.SSLContext:
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not ca and os.path.exists("/root/.ccr/ca-bundle.crt"):  # Claude cloud proxy
        ca = "/root/.ccr/ca-bundle.crt"
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


class NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # surface every hop instead of following it
        return None


def fetch(url: str, follow: bool = False) -> tuple[int, dict, str]:
    handlers = [urllib.request.HTTPSHandler(context=ctx())]
    if not follow:
        handlers.append(NoFollow())
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=25) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--pixel", help="Meta pixel id that should load on the page")
    a = ap.parse_args()

    fails, warns = [], []
    url, hops = a.url, []
    for _ in range(6):
        status, headers, body = fetch(url)
        if status in (301, 302, 303, 307, 308):
            nxt = urljoin(url, headers.get("Location", ""))
            hops.append(f"{status} {url} → {nxt}")
            url = nxt
            continue
        break
    else:
        fails.append("more than 5 redirects")

    print(f"Requested : {a.url}")
    for h in hops:
        print(f"  hop     : {h}")
    print(f"Final     : {status} {url}")

    if status != 200:
        fails.append(f"final status {status}")
    if hops:
        warns.append(f"{len(hops)} redirect hop(s) - put the final URL in the ad instead")
        if urlparse(url).netloc != urlparse(a.url).netloc:
            warns.append(f"lands on a different host: {urlparse(url).netloc}")
        if any(h.split()[1].startswith("http://") or h.split()[-1].startswith("http://") for h in hops):
            fails.append("a hop goes through plain http")

    title = re.search(r"<title>([^<]*)</title>", body or "", re.I)
    print(f"Title     : {title.group(1).strip() if title else '(none)'}")

    want = {k: v for k, v in parse_qs(urlparse(a.url).query).items() if k.startswith("utm_")}
    got = {k: v for k, v in parse_qs(urlparse(url).query).items() if k.startswith("utm_")}
    if want:
        lost = sorted(set(want) - set(got))
        if lost:
            fails.append(f"UTM parameters lost on the way: {', '.join(lost)}")
        else:
            print(f"UTMs      : all {len(want)} survived ✓")
    else:
        warns.append("no utm_ parameters in the URL - spend won't join back to a creative")

    if a.pixel and status == 200:
        haystack = body
        for src in sorted(set(re.findall(r'<script[^>]+src="([^"]+\.js)"', body)))[:8]:
            full = urljoin(url, src)
            if urlparse(full).netloc == urlparse(url).netloc:
                try:
                    haystack += fetch(full, follow=True)[2]
                except Exception:
                    pass
        has_id = a.pixel in haystack
        has_loader = "fbevents.js" in haystack
        if has_id and has_loader:
            print(f"Pixel     : {a.pixel} loads ✓")
        else:
            warns.append(
                f"pixel {a.pixel} does NOT load here - Ads Manager will show clicks but no "
                "landing page views or leads. Report those as 'not measured', never 0."
            )

    for w in warns:
        print(f"⚠️  {w}")
    for f in fails:
        print(f"⛔ {f}")
    print("RESULT    :", "FAIL - don't put this in an ad" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
