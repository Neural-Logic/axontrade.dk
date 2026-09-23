#!/usr/bin/env python3
"""Build axontrade.dk from one template and one strings file per language (same method as neurallogic.dk).

    python3 build/front.py --check     render English and compare with build/front/baseline.html
    python3 build/front.py             write index.html (and the translated front pages)

Why it works this way: the front page was hand-written HTML with its text baked into the
markup. Three languages of that would be three files drifting apart — the fault the estate
audit of 5 September found in the commitments. So the markup lives once, in
build/front/template.html, and every reader-visible string lives in build/front/strings.<lang>.json.

The gate: rendering English must reproduce baseline.html byte for byte, until the day a
deliberate change to the front page is made — then refresh the baseline in the same commit
that makes the change, so the check keeps its meaning.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONT = ROOT / "build" / "front"
LANGS = ["en", "de", "da"]
# Where each language's front page lives, and what the chooser calls it.
HOME = {"en": "https://axontrade.dk/", "de": "https://axontrade.dk/de/", "da": "https://axontrade.dk/da/"}
LABEL = {"en": "EN", "de": "DE", "da": "DA"}
OUTPUT = {"en": ROOT / "index.html", "de": ROOT / "de" / "index.html", "da": ROOT / "da" / "index.html"}
TOKEN = re.compile(r"\{\{t\.([A-Za-z0-9_]+)\}\}")


def published() -> list:
    """The languages Lead has released, from build/published.json."""
    return json.loads((ROOT / "build" / "published.json").read_text(encoding="utf-8"))["languages"]


def available() -> list:
    """The languages that have a front page AND are released. Never offer a page that is not
    there: on 20 September the chooser shipped ahead of the translations and pointed at two
    404s for six minutes. The build derives the list instead of trusting a constant."""
    return [code for code in LANGS
            if (FRONT / f"strings.{code}.json").exists() and code in published()]


def langswitch(lang: str) -> str:
    """The chooser. It switches, it never redirects. With one language there is nothing
    to choose, so it is not rendered at all."""
    codes = available()
    if len(codes) < 2:
        return ""
    links = "".join(
        '<a href="{}" hreflang="{}" lang="{}"{}>{}</a>'.format(
            HOME[code], code, code, ' aria-current="page"' if code == lang else "", LABEL[code])
        for code in codes)
    return f'<nav class="langs" aria-label="Language">{links}</nav>'


def head_links(lang: str) -> str:
    codes = available()
    rows = [f'<link rel="canonical" href="{HOME[lang]}">']
    if len(codes) > 1:
        rows += [f'<link rel="alternate" hreflang="{code}" href="{HOME[code]}">' for code in codes]
        rows.append(f'<link rel="alternate" hreflang="x-default" href="{HOME["en"]}">')
    return "\n".join(rows)


def render(lang: str) -> str:
    template = (FRONT / "template.html").read_text(encoding="utf-8")
    strings = json.loads((FRONT / f"strings.{lang}.json").read_text(encoding="utf-8"))

    missing = sorted({m.group(1) for m in TOKEN.finditer(template)} - set(strings))
    if missing:
        sys.exit(f"ERROR: {lang}: {len(missing)} string(s) missing, first: {missing[:5]}")

    out = TOKEN.sub(lambda m: strings[m.group(1)], template)
    out = TOKEN.sub(lambda m: strings[m.group(1)], out)   # a string may hold a token (the search-field prompt)
    out = out.replace("{{langswitch}}", langswitch(lang))
    out = out.replace("{{canonical}}", head_links(lang))
    out = out.replace("{{ogurl}}", HOME[lang])
    out = out.replace('<html lang="en">', f'<html lang="{lang}">')
    if "{{" in out:
        leftover = re.findall(r"\{\{[^}]{0,40}\}\}", out)
        sys.exit(f"ERROR: {lang}: unfilled placeholder(s): {leftover[:5]}")
    return out


def main() -> None:
    check = "--check" in sys.argv
    baseline = (FRONT / "baseline.html").read_text(encoding="utf-8")
    english = render("en")
    if english == baseline:
        print("English page reproduces the baseline byte for byte.")
    else:
        print("DIFFERENT from baseline. If that is deliberate, refresh baseline.html in the same "
              "commit; if not, the extraction lost something.")
        import difflib
        for line in list(difflib.unified_diff(
                baseline.splitlines(), english.splitlines(), "baseline", "rendered",
                lineterm="", n=1))[:24]:
            print("  " + line[:150])
        if check:
            sys.exit(1)
    if check:
        return

    # --preview <dir>: render every written language into <dir> for a review round, released or not.
    preview = pathlib.Path(sys.argv[sys.argv.index("--preview") + 1]) if "--preview" in sys.argv else None
    for lang in LANGS:
        if not (FRONT / f"strings.{lang}.json").exists():
            print(f"skipped {lang}: no strings file yet")
            continue
        if preview is not None:
            target = preview / lang / "index.html" if lang != "en" else preview / "index.html"
        elif lang not in published():
            print(f"skipped {lang}: written but not released (build/published.json)")
            continue
        else:
            target = OUTPUT[lang]
        target.parent.mkdir(parents=True, exist_ok=True)
        html = render(lang)
        check_links(html, lang, fatal=preview is None)
        target.write_text(html, encoding="utf-8")
        print("wrote", target)


def check_links(html: str, lang: str, fatal: bool = True) -> None:
    """Every link into our own two sites must answer: on 20 September a chooser shipped pointing
    at two pages that did not exist. Checked live, before the file is written."""
    import re
    import urllib.request
    own = set(HOME.values())   # this site's own language homes: their existence is governed by published.json
    for url in sorted(set(re.findall(r'href="(https://(?:neurallogic|axontrade)\.dk/[^"]*)"', html)) - own):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "axontrade-build"})
            code = urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:  # noqa: BLE001
            sys.exit(f"ERROR: {lang}: could not check {url}: {e}")
        if code != 200:
            if fatal:
                sys.exit(f"ERROR: {lang}: the page links to {url}, which answers {code}. Not written.")
            print(f"WARNING (preview only): {lang} links to {url}, which answers {code}")


if __name__ == "__main__":
    main()
