#!/usr/bin/env python3
"""
MNRE Monthly 'Policy & Regulatory Updates' digest parser  (prototype)
---------------------------------------------------------------------
Turns the raw extracted text of one monthly digest PDF into structured
regulatory-event records:

    jurisdiction | issuing_body | title | issue_date | summary | source_url

This is the Layer-1 parser. Each record's `source_url` is the primary
document, i.e. the Layer-2 fetch target.

Deliberately dependency-light (stdlib only) so it can run anywhere.
On real pipeline input, feed it pdfplumber/pypdf text instead of a fixture.
"""

import re
import json
import sys
from datetime import date

# ---- structural anchors observed in the real PDFs -------------------------

JURISDICTION_MARKERS = {
    "Issued by Central Government": "central",
    "Issued by State Governments": "state",
}

# "I. Ministry of New and Renewable Energy (MNRE)"  ->  roman + org name
ORG_RE = re.compile(r"^\s*([IVXLC]+)\.\s+([A-Z][A-Za-z].+?)\s*$")

# "1. Some title..."  -> item number starts a new entry.
# Constrained to 1-2 digits: a wrapped sentence like "2017. The revised order..."
# is a year, not an item number, and must not start a new record.
ITEM_RE = re.compile(r"^\s*(\d{1,2})\.\s+(.*)$")

# dates like "23rd January 2025", "7th January 2025", "03rd January 2025"
DATE_RE = re.compile(
    r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})",
    re.IGNORECASE,
)

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}

# lines that are pure noise (page chrome / cover art)
NOISE_RE = re.compile(
    r"^\s*$|"
    r"^\s*\d+\s*$|"                                  # bare page numbers
    r"^\s*MNRE:\s*Policy.*Updates.*$|"               # running footer
    r"^\s*Policy\s*&\s*Regulatory\s*Updates\s*$|"
    r"^\s*Issued by .*organizations:\s*$|"
    r"^\s*Ministry of New and Renewable Energy\s*$|"
    r"^\s*(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s*$|"      # cover-box month
    r"^\s*\d{4}\s*$|"                                # cover-box year
    r"^\s*\*+\s*$|"                                   # ***** end marker
    r"^[^\x00-\x7F]+$",                              # non-ASCII (Hindi) lines
)

DOWNLOAD_TAG = re.compile(r"Download link\s*:", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")


def clean_url(raw: str) -> str:
    """Rejoin URLs that the PDF wrapped across lines (no spaces inside a URL)."""
    return re.sub(r"\s+", "", raw).strip().rstrip(".")


def iso_date(day: str, month: str, year: str) -> str:
    return date(int(year), MONTHS[month.lower()], int(day)).isoformat()


def parse_digest(text: str, digest_month: str) -> list[dict]:
    lines = text.splitlines()
    records, jurisdiction, org = [], None, None
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # jurisdiction switch
        for marker, val in JURISDICTION_MARKERS.items():
            if marker in line:
                jurisdiction = val
                break

        # organisation header (must NOT also look like a numbered item)
        m_org = ORG_RE.match(line)
        if m_org and not ITEM_RE.match(line):
            org = m_org.group(2).strip()
            i += 1
            continue

        # item start -> gather this entry's block until the next anchor
        m_item = ITEM_RE.match(line)
        if m_item:
            block = [m_item.group(2)]
            j = i + 1
            while j < n:
                nxt = lines[j]
                if ITEM_RE.match(nxt) or ORG_RE.match(nxt) \
                        or any(k in nxt for k in JURISDICTION_MARKERS):
                    break
                block.append(nxt)
                j += 1

            rec = build_record(
                [ln for ln in block if not NOISE_RE.match(ln)],
                jurisdiction, org, digest_month)
            if rec:
                records.append(rec)
            i = j
            continue

        i += 1

    return records


def build_record(block_lines, jurisdiction, org, digest_month):
    # find the date line (ends the title)
    date_idx, issue_date = None, None
    for idx, ln in enumerate(block_lines):
        m = DATE_RE.search(ln)
        if m:
            date_idx, issue_date = idx, iso_date(*m.groups())
            break

    # find the download tag (starts the URL)
    dl_idx = next((idx for idx, ln in enumerate(block_lines)
                   if DOWNLOAD_TAG.search(ln)), None)

    # title = everything up to & including the date line, minus the date text
    title_end = date_idx if date_idx is not None else (dl_idx or len(block_lines))
    title_parts = block_lines[: title_end + 1] if date_idx is not None \
        else block_lines[:title_end]
    title = " ".join(title_parts)
    title = DATE_RE.sub("", title)
    title = re.sub(r"\s+", " ", title).strip()

    # summary = between date line and download tag (often empty for states)
    summary = ""
    if date_idx is not None and dl_idx is not None and dl_idx > date_idx + 1:
        summary = " ".join(block_lines[date_idx + 1: dl_idx])
        summary = re.sub(r"\s+", " ", summary).strip()

    # url = fragments after the download tag, rejoined.
    # URLs wrap mid-string across lines (no internal spaces), so we concatenate
    # consecutive whitespace-free fragments and stop at the first line that
    # isn't a URL continuation (blank, footer, prose).
    source_url = None
    if dl_idx is not None:
        parts, started = [], False
        for k in range(dl_idx, len(block_lines)):
            seg = block_lines[k]
            if k == dl_idx:
                seg = DOWNLOAD_TAG.split(seg, 1)[-1]
            seg = seg.strip()
            if not seg:
                if started:
                    break
                continue
            if re.search(r"\s", seg):                    # prose / footer -> stop
                if not started and seg.lower().startswith("http"):
                    parts.append(seg.split()[0])
                break
            if seg.lower().startswith("http") or started:  # url fragment
                parts.append(seg)
                started = True
            elif started:
                break
        if parts:
            source_url = clean_url("".join(parts))

    if not title:
        return None

    return {
        "jurisdiction": jurisdiction,
        "issuing_body": org,
        "title": title,
        "issue_date": issue_date,
        "summary": summary or None,
        "source_url": source_url,
        "digest_month": digest_month,
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "jan2025_digest.txt"
    with open(path, encoding="utf-8") as f:
        text = f.read()

    recs = parse_digest(text, digest_month="2025-01")
    print(f"Parsed {len(recs)} regulatory events\n" + "=" * 60)
    print(json.dumps(recs, indent=2, ensure_ascii=False))

    # quick quality signals
    with_date = sum(1 for r in recs if r["issue_date"])
    with_url = sum(1 for r in recs if r["source_url"])
    print("\n" + "=" * 60)
    print(f"date captured : {with_date}/{len(recs)}")
    print(f"url  captured : {with_url}/{len(recs)}")
    print(f"bodies        : {sorted({r['issuing_body'] for r in recs})}")
