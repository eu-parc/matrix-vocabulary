#!/usr/bin/env python3
"""Check the vocabulary for problems, as Nanodash and published/ show it.

The check fails (exit code 1) on errors:

- two current terms have the same label (ignoring case);
- a current term links to a term that isn't current: withdrawn, never approved,
  or unknown. Parents count, and so does any other link into the vocabulary's
  namespace (e.g. "metabolite of", "isomer of").

It reports warnings, but passes, when:

- published/ is out of date with the vocabulary query (the next sync fixes it);
- a current term links to a deprecated term;
- current terms share an external identifier (InChIKey or CAS number).

A term is current when the vocabulary query lists it and it isn't deprecated.
Both the "approved classes" and the "approved terms" queries work (columns
class/class_label or term/term_label); the latter also covers I-ADOPT variables.
That is what Nanodash shows as the vocabulary; the query already applies
approval, retraction and supersession. Links and identifiers are read from the
terms' nanopubs in published/, so they cover terms that are already synced.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

from pubmate.download import fetch_url
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import SKOS

NP_HAS_ASSERTION = URIRef("http://www.nanopub.org/nschema#hasAssertion")
NOT_CURRENT_STATUSES = {"deprecated", "withdrawn", "example"}
IDENTIFIER = re.compile(r"^https?://identifiers\.org/(inchikey|cas):(\S+)$", re.IGNORECASE)
MAX_LISTED = 25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--query-url", required=True, help="vocabulary query (approved classes or terms), SPARQL-JSON API URL"
    )
    parser.add_argument("--namespace", required=True, help="namespace of the vocabulary's terms")
    parser.add_argument("--published-dir", type=Path, default=Path("published"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def val(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row:
            return row[key].get("value", "")
    return ""


def short(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[str, list[str]]] = []
        self.warnings: list[tuple[str, list[str]]] = []

    def error(self, title: str, items: list[str]) -> None:
        if items:
            self.errors.append((title, items))

    def warning(self, title: str, items: list[str]) -> None:
        if items:
            self.warnings.append((title, items))

    def markdown(self, counts: dict[str, int]) -> str:
        lines = ["## Vocabulary consistency check", ""]
        lines += ["| | |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in counts.items()] + [""]
        if not self.errors and not self.warnings:
            lines.append("No problems found.")
        for kind, entries in (("Error", self.errors), ("Warning", self.warnings)):
            for title, items in entries:
                lines += [f"### {kind}: {title} ({len(items)})", ""]
                lines += [f"- {item}" for item in items[:MAX_LISTED]]
                if len(items) > MAX_LISTED:
                    lines.append(f"- … and {len(items) - MAX_LISTED} more")
                lines.append("")
        return "\n".join(lines) + "\n"


def assertion_of(path: Path):
    dataset = Dataset()
    dataset.parse(path, format="trig")
    graph_ids = {o for g in dataset.graphs() for o in g.objects(None, NP_HAS_ASSERTION)}
    if len(graph_ids) != 1:
        raise SystemExit(f"{path}: expected one assertion graph, found {len(graph_ids)}")
    return dataset.graph(next(iter(graph_ids)))


def main() -> None:
    args = parse_args()
    ns = args.namespace
    payload = fetch_url(
        args.query_url, accept="application/sparql-results+json", timeout=args.timeout, retries=args.retries
    )
    rows = json.loads(payload).get("results", {}).get("bindings", [])

    label: dict[str, str] = {}
    np_of: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    statuses: dict[str, set[str]] = {}
    for row in rows:
        term = val(row, "class", "term")
        if not term:
            continue
        label[term] = val(row, "class_label", "term_label").strip()
        np_of[term] = val(row, "np")
        parents[term] = set(val(row, "superclasses_multi_iri").split())
        statuses[term] = {s.strip().lower() for s in val(row, "status_multi").splitlines() if s.strip()}
    current = {t for t in label if not statuses[t] & NOT_CURRENT_STATUSES}
    deprecated = {t for t in label if "deprecated" in statuses[t]}

    def name(term: str) -> str:
        return f"{label[term]} (`{short(term)}`)" if term in label else f"`{term}`"

    report = Report()

    # Duplicate labels among current terms.
    by_label = collections.defaultdict(list)
    for term in current:
        if label[term]:
            by_label[label[term].lower()].append(term)
    report.error(
        "current terms with the same label",
        [" / ".join(name(t) for t in sorted(ts)) for _, ts in sorted(by_label.items()) if len(ts) > 1],
    )

    # published/ against the query (the sync leaves out deprecated and example terms).
    published = {p.stem: p for p in sorted(args.published_dir.glob("*.trig"))}
    expected = {short(np_of[t]): t for t in current if np_of[t]}
    report.warning(
        "current definitions missing from published/ (run the sync)",
        [f"{name(t)}: `{code}`" for code, t in sorted(expected.items()) if code not in published],
    )
    report.warning(
        "files in published/ that aren't a current definition (run the sync)",
        [f"`{code}.trig`" for code in sorted(set(published) - set(expected))],
    )

    # Links and external identifiers, from the current terms' nanopubs.
    links: dict[str, set[str]] = {t: {p for p in parents[t] if p.startswith(ns)} for t in current}
    identifiers = collections.defaultdict(set)
    for code, term in expected.items():
        if code not in published:
            continue
        assertion = assertion_of(published[code])
        subject = URIRef(term)
        for obj in assertion.objects(subject, None):
            if isinstance(obj, URIRef) and str(obj).startswith(ns) and str(obj) != term:
                links[term].add(str(obj))
        for obj in assertion.objects(subject, SKOS.exactMatch):
            if isinstance(obj, (URIRef, Literal)) and (m := IDENTIFIER.match(str(obj))):
                identifiers[(m.group(1).lower(), m.group(2).upper())].add(term)

    broken, to_deprecated = [], []
    for term in sorted(current, key=lambda t: label[t].lower()):
        for target in sorted(links[term]):
            if target in current:
                continue
            entry = f"{name(term)} → {name(target)}"
            (to_deprecated if target in deprecated else broken).append(entry)
    report.error("links to terms that aren't current (withdrawn, not approved or unknown)", broken)
    report.warning("links to deprecated terms", to_deprecated)
    report.warning(
        "current terms that share an InChIKey or CAS number",
        [
            f"{kind}:{value}: " + " / ".join(name(t) for t in sorted(terms, key=lambda t: label[t].lower()))
            for (kind, value), terms in sorted(identifiers.items())
            if len(terms) > 1
        ],
    )

    counts = {
        "Terms listed by the vocabulary query": len(label),
        "…current (not deprecated)": len(current),
        "…deprecated": len(deprecated),
        "Files in published/": len(published),
    }
    summary = report.markdown(counts)
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(summary)
    for kind, entries in (("error", report.errors), ("warning", report.warnings)):
        for title, items in entries:
            print(f"::{kind}::{len(items)} {title}", file=sys.stderr)
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
