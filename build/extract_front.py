#!/usr/bin/env python3
"""One-time extraction for axontrade.dk (same method as neurallogic.dk, 20 September 2026):
index.html -> build/front/template.html + strings.en.json.

Run once. It reads build/front/baseline.html (a copy of the hand-written front page),
replaces every run of reader-visible text with a {{t.KEY}} token, and writes the English
text into build/front/strings.en.json. build/front.py then renders the page back.

The gate on this script is in build/front.py --check: rendering the template with the
English strings must reproduce baseline.html byte for byte. If it does not, the extraction
lost something and must not be used.

Rules:
- A "text leaf" is any element that holds text and has no block-level descendant. Its whole
  inner HTML becomes one string, so a sentence with <b>emphasis</b> inside it stays one
  sentence for the translator instead of three fragments.
- <style> is left alone. Inside <script>, only the literals listed in SCRIPT_STRINGS are
  replaced: those are the ones the reader sees (the typed question, the status line).
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONT = ROOT / "build" / "front"

BLOCK = {"div", "section", "ul", "ol", "li", "p", "h1", "h2", "h3", "h4", "header", "footer",
         "nav", "aside", "main", "figure", "table", "tr", "td", "script", "style"}
VOID = {"br", "img", "input", "link", "meta", "source", "hr", "wbr", "area", "base", "col"}
SKIP_RAW = {"script", "style"}

# Literals inside the page's own script that the reader sees on screen.
SCRIPT_STRINGS: list = []   # the Axon page shows nothing from its script

TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>")
COMMENT = re.compile(r"<!--.*?-->", re.S)


def spans(src: str):
    """Yield (tag, inner_start, inner_end, descendant_tags) for every element, innermost first."""
    stack, done, i = [], [], 0
    while i < len(src):
        m = TAG.search(src, i)
        if not m:
            break
        c = COMMENT.match(src, m.start())
        if c:
            i = c.end()
            continue
        closing, tag, _attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if not closing:
            if tag in VOID or selfclose:
                for frame in stack:
                    frame[2].add(tag)
                i = m.end()
                continue
            if tag in SKIP_RAW:
                end = re.search(rf"</{tag}\s*>", src[m.end():], re.I)
                stop = m.end() + (end.end() if end else 0)
                for frame in stack:
                    frame[2].add(tag)
                i = stop
                continue
            for frame in stack:
                frame[2].add(tag)
            stack.append([tag, m.end(), set()])
            i = m.end()
            continue
        # closing tag
        while stack and stack[-1][0] != tag:
            stack.pop()                      # tolerate unclosed inline markup
        if stack:
            name, start, kids = stack.pop()
            done.append((name, start, m.start(), kids))
        i = m.end()
    return done


def main() -> None:
    baseline = (FRONT / "baseline.html").read_text(encoding="utf-8")
    elements = spans(baseline)

    leaves = []
    for tag, start, end, kids in elements:
        inner = baseline[start:end]
        if not re.sub(COMMENT, "", inner).strip():
            continue
        if not re.search(r"[A-Za-zÆØÅæøå0-9]", re.sub(r"<[^>]+>", "", inner)):
            continue
        if kids & BLOCK:
            continue
        leaves.append((start, end, tag, inner))

    # Keep only outermost leaves: an element already inside a chosen leaf is part of its string.
    leaves.sort(key=lambda r: (r[0], -r[1]))
    chosen, covered_to = [], -1
    for start, end, tag, inner in leaves:
        if start < covered_to:
            continue
        chosen.append((start, end, tag, inner))
        covered_to = end

    strings, out, cursor, n = {}, [], 0, 0
    for start, end, tag, inner in chosen:
        n += 1
        key = f"t{n:03d}_{tag}"
        strings[key] = inner
        out.append(baseline[cursor:start])
        out.append("{{t." + key + "}}")
        cursor = end
    out.append(baseline[cursor:])
    template = "".join(out)

    for literal in SCRIPT_STRINGS:
        if literal not in template:
            sys.exit(f"ERROR: script literal not found, extraction would lose it: {literal!r}")
        n += 1
        key = f"t{n:03d}_js"
        strings[key] = literal
        template = template.replace(literal, "{{t." + key + "}}")

    (FRONT / "template.html").write_text(template, encoding="utf-8")
    (FRONT / "strings.en.json").write_text(
        json.dumps(strings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(strings)} strings extracted "
          f"({len(chosen)} from the markup, {len(SCRIPT_STRINGS)} from the script)")


if __name__ == "__main__":
    main()
