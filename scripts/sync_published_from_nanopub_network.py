#!/usr/bin/env python3
"""Rebuild published nanopublications from the Knowledge Pixels query API."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable


DEFAULT_QUERY_URL = (
    "https://query.knowledgepixels.com/api/"
    "RA-JiaaWDuktmuuf5qNwskzOImXDjUhCMWhBiDwgfuleo/"
    "get-classes-of-ontology-from-space-members"
    "?ontologyNamespace=https%3A%2F%2Fw3id.org%2Fspaces%2Fchemical-exposome-matrix%2Fr%2Fvocabulary"
    "&ontology=https%3A%2F%2Fw3id.org%2Fspaces%2Fchemical-exposome-matrix%2Fr%2Fvocabulary"
)


def fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt == retries:
                break
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def nanopub_uris_from_query(query_url: str, *, timeout: int, retries: int) -> list[str]:
    payload = fetch_url(
        query_url,
        accept="application/sparql-results+json",
        timeout=timeout,
        retries=retries,
    )
    data = json.loads(payload)
    bindings = data.get("results", {}).get("bindings", [])
    uris = {
        row["np"]["value"]
        for row in bindings
        if row.get("np", {}).get("type") == "uri" and row["np"].get("value")
    }
    if not uris:
        raise RuntimeError("The query returned no nanopublication URIs in the 'np' column.")
    return sorted(uris)


def artifact_code(np_uri: str) -> str:
    code = np_uri.rstrip("/").rsplit("/", 1)[-1]
    if not code.startswith("RA"):
        raise ValueError(f"Unexpected nanopublication URI without RA artifact code: {np_uri}")
    return code


def download_nanopubs(
    np_uris: Iterable[str],
    *,
    staging_dir: Path,
    timeout: int,
    retries: int,
) -> list[tuple[str, str]]:
    manifest_rows: list[tuple[str, str]] = []
    for np_uri in np_uris:
        code = artifact_code(np_uri)
        trig_url = f"{np_uri}.trig"
        content = fetch_url(trig_url, accept="application/trig", timeout=timeout, retries=retries)
        if b"np:Nanopublication" not in content:
            raise RuntimeError(f"Downloaded content does not look like a nanopublication: {trig_url}")
        (staging_dir / f"{code}.trig").write_bytes(content)
        manifest_rows.append((code, np_uri))
    return manifest_rows


def write_manifest(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("artifact_code\tnp_uri\n")
        for code, np_uri in rows:
            handle.write(f"{code}\t{np_uri}\n")


def replace_directory(source_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.trig"):
        path.unlink()
    for path in sorted(source_dir.glob("*.trig")):
        shutil.copy2(path, output_dir / path.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-url", default=DEFAULT_QUERY_URL)
    parser.add_argument("--output-dir", default="published", type=Path)
    parser.add_argument("--manifest", default=Path("build/nanopub-network-published.tsv"), type=Path)
    parser.add_argument("--timeout", default=60, type=int)
    parser.add_argument("--retries", default=3, type=int)
    parser.add_argument(
        "--min-count",
        default=1,
        type=int,
        help="Fail if the query returns fewer nanopublications than this.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    np_uris = nanopub_uris_from_query(args.query_url, timeout=args.timeout, retries=args.retries)
    if len(np_uris) < args.min_count:
        raise RuntimeError(f"Expected at least {args.min_count} nanopubs, got {len(np_uris)}.")

    with tempfile.TemporaryDirectory(prefix="matrix-published-sync-") as temp_dir:
        staging_dir = Path(temp_dir)
        rows = download_nanopubs(
            np_uris,
            staging_dir=staging_dir,
            timeout=args.timeout,
            retries=args.retries,
        )
        replace_directory(staging_dir, args.output_dir)

    write_manifest(args.manifest, rows)
    print(f"Rebuilt {args.output_dir} from {len(rows)} nanopublications.")
    print(f"Wrote manifest to {args.manifest}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
