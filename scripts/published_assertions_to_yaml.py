#!/usr/bin/env python3
"""Build a schema-shaped YAML dump from published matrix nanopub assertions."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from rdflib import Graph, Literal, Namespace, RDF, URIRef


OWL = Namespace("http://www.w3.org/2002/07/owl#")
PEHTERMS = Namespace("https://w3id.org/peh/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
SCHEMA = Namespace("http://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
MATRIX_NAMESPACE = "https://w3id.org/peh/matrices/"


PREDICATE_SLOTS = {
    RDFS.subClassOf: "parent_matrices",
    SCHEMA.comment: "remark",
    SCHEMA.description: "description",
    SCHEMA.alternateName: "short_name",
    PEHTERMS.hasUiLabel: "ui_label",
    SKOS.exactMatch: "exact_matches",
    PROV.wasAttributedTo: "suggester",
}

LIST_SLOTS = {
    "exact_matches",
    "parent_matrices",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assertion-folder", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def scalar(value: Any) -> Any:
    if isinstance(value, URIRef):
        return str(value)
    if isinstance(value, Literal):
        py_value = value.toPython()
        if isinstance(py_value, Decimal):
            return float(py_value)
        return py_value
    return str(value)


def append(record: dict[str, Any], slot: str, value: Any, active_subjects: set[str]) -> None:
    if slot == "parent_matrices" and isinstance(value, str):
        if value.startswith(MATRIX_NAMESPACE) and value not in active_subjects:
            return

    if slot in LIST_SLOTS:
        record.setdefault(slot, [])
        if value not in record[slot]:
            record[slot].append(value)
    elif slot not in record:
        record[slot] = value


def context_alias(graph: Graph, node: Any) -> dict[str, Any]:
    item: dict[str, Any] = {}
    first_values = {
        "property_name": graph.objects(node, SCHEMA.identifier),
        "context": graph.objects(node, PEHTERMS.hasContext),
        "alias": graph.objects(node, SCHEMA.alternateName),
    }
    for slot, values in first_values.items():
        for value in values:
            item[slot] = scalar(value)
            break
    return item


def main() -> None:
    args = parse_args()
    graph = Graph()
    ttl_files = sorted(args.assertion_folder.glob("*.ttl"))
    if not ttl_files:
        raise SystemExit(f"No .ttl assertion files found in {args.assertion_folder}")

    for ttl_file in ttl_files:
        graph.parse(ttl_file, format="turtle")

    records: list[dict[str, Any]] = []
    active_subjects = {str(subject) for subject in graph.subjects(RDF.type, OWL.Class)}
    for subject in sorted(graph.subjects(RDF.type, OWL.Class), key=str):
        record: dict[str, Any] = {"id": str(subject)}

        for label in graph.objects(subject, RDFS.label):
            if isinstance(label, Literal) and label.language:
                record.setdefault("translations", []).append(
                    {
                        "property_name": "name",
                        "language": label.language,
                        "translated_value": str(label),
                    }
                )
            elif "name" not in record:
                record["name"] = str(label)

        for predicate, slot in PREDICATE_SLOTS.items():
            for value in graph.objects(subject, predicate):
                append(record, slot, scalar(value), active_subjects)

        for node in graph.objects(subject, PEHTERMS.hasContextAlias):
            item = context_alias(graph, node)
            if item:
                record.setdefault("context_aliases", []).append(item)

        for slot in LIST_SLOTS:
            if slot in record:
                record[slot] = sorted(record[slot], key=str)
        records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(
            {"matrix_subclasses": records},
            stream,
            allow_unicode=True,
            sort_keys=False,
        )


if __name__ == "__main__":
    main()
