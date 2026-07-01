## Matrix Vocabulary Dropbox to Nanopublication Template

This repository implements a staged vocabulary workflow for matrices using
pubmate defining nanopublications.

## Proposing a new matrix

All new matrix info can be added to one or more `*.yaml` files following this
structure. This is a minimal example for such a file. The full contract is the
JSON schema in [schema/dropbox-matrix.schema.json](schema/dropbox-matrix.schema.json),
with a worked example in [schema/dropbox-matrix.example.yaml](schema/dropbox-matrix.example.yaml).

```yaml
# Optional file-level default suggester (ORCID); applied to entries without their own.
suggester: https://orcid.org/0000-0002-1825-0097

matrix_subclasses:
- name: "environmental matrix"
  description: All abiotic environmental compartments in which chemicals can be measured
  parent_matrices:
    - https://w3id.org/peh/terms/Matrix
- id: bioticmatrix
  name: "biotic matrix"
  description: All biological organisms and their tissues
  parent_matrices:
    - https://w3id.org/peh/terms/Matrix
```

The `id` field does not need to be provided; identifiers are minted on the fly.

The optional `suggester` field (an ORCID) records who proposed the term; it
becomes the `prov:wasAttributedTo` provenance of the resulting nanopublication.
Set it once at the top of the file as a default, or per entry to override.

Open a PR with these `*.yaml` files added to `dropbox/`.

## Under the hood

1. New YAML vocab files are dropped into `dropbox/`.
2. Processing converts them into RDF assertions in `unpublished/`.
3. The minted combined YAML file is copied to `archive/` with a ULID suffix to
   avoid overwriting earlier submissions, and processed source YAML files are
   removed from `dropbox/`.
4. Publishing creates defining nanopublications from `unpublished/`.
5. Publishing writes/updates `redirect/id-map.tsv` with old identifier, new
   matrix thing URI, and nanopub URI.
6. Published nanopublications are written to `published/` as `.trig`.

## Folder Semantics

- `dropbox/`: incoming YAML vocabulary files
- `archive/`: processed combined YAML files with minted identifiers and ULID-labeled filenames
- `unpublished/`: generated RDF term assertions waiting for publish
- `redirect/`: old identifier to nanopub identifier mappings
- `published/`: signed defining nanopublications
- `build/`: transient build artifacts

## Local Usage

Install dependencies:

```bash
uv sync
```

Download a tagged `peh.yaml` snapshot into `schema/`:

```bash
make fetch-peh-schema
```

Override the upstream tag when you want a different schema release:

```bash
make fetch-peh-schema PEH_SCHEMA_TAG=v0.6.1
```

Process incoming YAML from `dropbox/`:

```bash
make pipeline
```

Validate proposed defining nanopubs:

```bash
make validate-pr
```

Dry-run minting from generated assertions:

```bash
make publish-defining PUBLISH_KEY_ARGS= DRY=--dry-run
```

Live publishing uses the matrix bot identity; see
[docs/bot-identity-setup.md](docs/bot-identity-setup.md).

End-to-end local smoke test:

```bash
make test-flow
```

## Publishing Details

- Matrix term namespace: `https://w3id.org/peh/matrices/`
- Matrix vocabulary space: `https://w3id.org/spaces/matrix/r/vocabulary`
- Nanopub type: `https://w3id.org/peh/terms/Matrix`
- Bot: `Matrix bot` (`matrix-bot`)
- Nanodash template: set `NANOPUB_TEMPLATE` once the "Defining a matrix"
  template is published.

## GitHub Workflows

- `publish.yaml`: validates PRs, processes accepted dropbox files on `main`, and
  mints/publishes defining nanopublications when the matrix bot secret is
  configured.
- `pages.yaml`: extracts assertion TTL from `published/*.trig` and builds the
  vocabulary browser.
