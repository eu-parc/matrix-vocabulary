# Matrix Vocabulary Nanopublication Workflow

This repository follows the pubmate `0.2.1` defining-nanopublication workflow used
by `biochementity-vocabulary`, adapted to matrix terms.

## Current shape

- `dropbox/` receives proposed YAML files.
- `archive/` keeps minted combined YAML snapshots for processed proposals.
- `unpublished/` contains generated plain assertion TTL files waiting to be
  minted into defining nanopublications.
- `published/` contains signed defining nanopublications as `.trig`.
- `redirect/id-map.tsv` maps old/generated assertion identifiers to the new
  nanopub-based thing URI and nanopub URI.
- `build/assertions/` is generated only during Pages builds by extracting the
  assertion graph from `published/*.trig`.

## Identifier model

Canonical matrix term IRIs are minted in:

```text
https://w3id.org/peh/matrices/
```

`pubmate-mint-publish` signs each defining nanopub so the trusty artifact code is
placed on the matrix term URI. The nanopub URI itself stays in the standard
`https://w3id.org/np/` namespace.

## Publishing metadata

- `NANOPUB_TYPE`: `https://w3id.org/peh/terms/Matrix`
- `NANOPUB_PART_OF`: `https://w3id.org/spaces/matrix/r/vocabulary`
- `NANOPUB_TEMPLATE`: currently blank until the "Defining a matrix" Nanodash
  template is published.
- Signing agent: `Matrix bot`, introduced and wired through
  `docs/bot-identity-setup.md`.

## CI flow

- Pull requests build dropbox YAML into isolated `build/pr-assertions`, validate
  the resulting defining nanopublications offline, and publish to the test
  registry when `mode=test-publish`.
- Merges to `main` process accepted dropbox files for real, archive the minted
  YAML, and generate `unpublished/` assertions.
- If the matrix bot secret is configured, production then mints/publishes
  defining nanopublications and commits `published/` plus `redirect/id-map.tsv`.
- Pages extracts assertion TTL from the published nanopubs before building the
  vocabulary browser.

## One-time migration

Existing `unpublished/*.ttl` assertions can be migrated with:

```bash
make migrate DRY=--dry-run PUBLISH_KEY_ARGS=
```

For the live run, configure the matrix bot first and then run `make migrate` with
the bot signing material. The command is resumable through `redirect/id-map.tsv`.
