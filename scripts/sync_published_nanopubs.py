#!/usr/bin/env python3
"""Sync approved, non-deprecated matrix vocabulary nanopubs into published/.

The vocabulary query decides which nanopub currently defines each term, the
same way Nanodash does: a nanopub retracted or superseded with its own key is
no longer listed, while a retraction signed with another key has no effect.
This script takes the query's answer as it is (minus deprecated and example
terms) and doesn't filter retractions itself, so published/ lists the same
definitions as Nanodash.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pubmate.download import (
    DownloadedNanopub,
    fetch_url,
    sync_nanopubs,
    write_manifest,
)

DEFAULT_QUERY_URL = (
    "https://query.knowledgepixels.com/api/"
    "RA5rQSjX-6t_ccwhgZhxCpWryxuRjMFeCMXelxJYfxtdw/"
    "get-approved-classes-of-an-ontology-from-space-members"
    "?ontology=https%3A%2F%2Fw3id.org%2Fspaces%2Fchemical-exposome-matrix%2Fr%2Fvocabulary"
)
BLOCKED_STATUSES = frozenset({"deprecated", "withdrawn", "example"})


def approved_nanopub_uris(
    query_url: str,
    *,
    timeout: int,
    retries: int,
    blocked_statuses: frozenset[str] = BLOCKED_STATUSES,
) -> tuple[list[str], dict[str, int]]:
    payload = fetch_url(
        query_url,
        accept="application/sparql-results+json",
        timeout=timeout,
        retries=retries,
    )
    data = json.loads(payload)
    bindings = data.get("results", {}).get("bindings", [])

    uris: set[str] = set()
    skipped: dict[str, int] = {status: 0 for status in blocked_statuses}
    for row in bindings:
        statuses = {
            status.strip().lower()
            for status in row.get("status_multi", {}).get("value", "").splitlines()
            if status.strip()
        }
        blocked = statuses & blocked_statuses
        if blocked:
            for status in blocked:
                skipped[status] += 1
            continue

        np_uri = row.get("np", {})
        np_uri_value = np_uri.get("value", "")
        if np_uri.get("type") == "uri" and np_uri_value:
            uris.add(np_uri_value)

    return sorted(uris), skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-url", default=DEFAULT_QUERY_URL)
    parser.add_argument("--output-dir", default=Path("published"), type=Path)
    parser.add_argument("--manifest", default=Path("build/published-nanopubs.tsv"), type=Path)
    parser.add_argument("--timeout", default=120, type=int)
    parser.add_argument("--retries", default=3, type=int)
    parser.add_argument("--min-count", default=1, type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    np_uris, skipped = approved_nanopub_uris(
        args.query_url,
        timeout=args.timeout,
        retries=args.retries,
    )
    if len(np_uris) < args.min_count:
        raise SystemExit(f"Expected at least {args.min_count} nanopub(s), got {len(np_uris)}.")

    downloaded: list[DownloadedNanopub] = sync_nanopubs(
        np_uris,
        output_dir=args.output_dir,
        timeout=args.timeout,
        retries=args.retries,
    )
    write_manifest(args.manifest, downloaded)

    skipped_text = ", ".join(f"{status}={count}" for status, count in sorted(skipped.items()))
    print(f"Synced {len(downloaded)} approved nanopub(s) to {args.output_dir}.")
    print(f"Skipped statuses: {skipped_text}.")
    print(f"Wrote manifest to {args.manifest}.")


if __name__ == "__main__":
    main()
