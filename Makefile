DROPBOX_FOLDER ?= dropbox
UNPUBLISHED_FOLDER ?= unpublished
PUBLISHED_FOLDER ?= published
ARCHIVE_FOLDER ?= archive
REDIRECT_FOLDER ?= redirect
SCHEMA ?= schema/peh.yaml
PEH_SCHEMA_REPO ?= eu-parc/parco-hbm
PEH_SCHEMA_TAG ?= v0.6.0
PEH_SCHEMA_SOURCE_PATH ?= linkml/schema/peh.yaml
PEH_SCHEMA_DEST ?= schema/peh.yaml
PEH_SCHEMA_URL ?= https://raw.githubusercontent.com/$(PEH_SCHEMA_REPO)/$(PEH_SCHEMA_TAG)/$(PEH_SCHEMA_SOURCE_PATH)
OUT_FOLDER ?= build
ONTOLOGY_LABEL ?= matrices.ttl
TARGET_CLASS ?= matrix_subclasses
BASE_NAMESPACE ?= https://w3id.org/peh/terms/
TERM_PARENT_CLASS ?= https://w3id.org/peh/terms/Matrix
MINT_NAMESPACE ?= https://w3id.org/peh/matrices/
COMBINED_DATA ?= $(OUT_FOLDER)/combined.yaml
DRY ?=

DATA_FILES = $(sort $(wildcard $(DROPBOX_FOLDER)/*.yaml))

.PHONY: help print-data prepare fetch-peh-schema aggregate mint build graph2assertions \
	validate-pipeline process-dropbox archive-dropbox publish-nanopubs mark-published \
	publish-pipeline pipeline test-flow clean

help:
	@echo "Targets:"
	@echo "  make fetch-peh-schema          # download schema/peh.yaml from a tagged parco-hbm release"
	@echo "  make pipeline                  # process dropbox -> unpublished + archive"
	@echo "  make validate-pipeline         # process dropbox -> build + unpublished, without archive/publish"
	@echo "  make publish-pipeline          # publish unpublished assertions + move to published"
	@echo "  make publish-pipeline DRY=--dry-run"
	@echo "  make test-flow                 # local end-to-end dry-run test"

print-data:
	@echo "$(DATA_FILES)"

prepare:
	mkdir -p $(OUT_FOLDER) $(UNPUBLISHED_FOLDER) $(PUBLISHED_FOLDER) $(ARCHIVE_FOLDER) $(REDIRECT_FOLDER)

fetch-peh-schema:
	@if [ -z "$(PEH_SCHEMA_TAG)" ]; then \
		echo "PEH_SCHEMA_TAG must be set to a released tag, for example v0.4.0."; \
		exit 1; \
	fi
	mkdir -p $(dir $(PEH_SCHEMA_DEST))
	curl -fsSL "$(PEH_SCHEMA_URL)" -o "$(PEH_SCHEMA_DEST)"
	@echo "Downloaded $(PEH_SCHEMA_DEST) from $(PEH_SCHEMA_REPO) tag $(PEH_SCHEMA_TAG)"

aggregate: prepare
	@set -e; \
	if [ -z "$(DATA_FILES)" ]; then \
		echo "No YAML files found in $(DROPBOX_FOLDER). Skipping aggregation."; \
	else \
		uv run pubmate-yamlconcat \
			--target $(TARGET_CLASS) \
			$(COMBINED_DATA) \
			$(DATA_FILES); \
	fi

mint: aggregate
	@set -e; \
	if [ ! -f "$(COMBINED_DATA)" ]; then \
		echo "No combined YAML available. Skipping mint."; \
	else \
		uv run pubmate-mint \
			--data $(COMBINED_DATA) \
			--target $(TARGET_CLASS) \
			--namespace "$(MINT_NAMESPACE)" \
			--verbose \
			--preflabel name; \
	fi

build: mint
	@set -e; \
	if [ ! -f "$(COMBINED_DATA)" ]; then \
		echo "No combined YAML available. Skipping RDF conversion."; \
	else \
		echo "Building $(ONTOLOGY_LABEL)"; \
		uv run linkml-convert \
			--target-class EntityList \
			-s $(SCHEMA) \
			-o $(OUT_FOLDER)/$(ONTOLOGY_LABEL) \
			$(COMBINED_DATA); \
		echo "Build completed successfully for $(ONTOLOGY_LABEL)"; \
	fi

graph2assertions: build
	@set -e; \
	if [ ! -f "$(OUT_FOLDER)/$(ONTOLOGY_LABEL)" ]; then \
		echo "No ontology file available. Skipping assertion extraction."; \
	else \
		uv run pubmate-cleanrdf \
			--input-ontology-path $(OUT_FOLDER)/$(ONTOLOGY_LABEL) \
			--base-namespace $(BASE_NAMESPACE) \
			--term-output-path $(UNPUBLISHED_FOLDER) \
			--term-parent-class $(TERM_PARENT_CLASS); \
	fi

validate-pipeline: graph2assertions

archive-dropbox: prepare
	@set -e; \
	if [ -n "$(DRY)" ]; then \
		echo "DRY mode enabled. Keeping YAML files in $(DROPBOX_FOLDER)."; \
		exit 0; \
	fi; \
	files="$(DATA_FILES)"; \
	if [ -z "$$files" ]; then \
		echo "No YAML files found in $(DROPBOX_FOLDER). Nothing to archive."; \
		exit 0; \
	fi; \
	for src in $$files; do \
		name=$$(basename "$$src"); \
		stem=$${name%.yaml}; \
		while :; do \
			label=$$(python3 -c 'import os, time; alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"; value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big"); print("".join(alphabet[(value >> shift) & 31] for shift in range(125, -1, -5)))'); \
			dest="$(ARCHIVE_FOLDER)/$${stem}_$${label}.yaml"; \
			[ ! -e "$$dest" ] && break; \
		done; \
		if [ -e "$$dest" ]; then \
			echo "Refusing to overwrite existing archive file $$dest"; \
			exit 1; \
		fi; \
		mv "$$src" "$$dest"; \
		echo "Archived $$src -> $$dest"; \
	done

process-dropbox: graph2assertions archive-dropbox

publish-nanopubs: prepare
	@set -e; \
	files=$$(ls -1 $(UNPUBLISHED_FOLDER)/*.ttl 2>/dev/null || true); \
	if [ -z "$$files" ]; then \
		echo "No assertions found in $(UNPUBLISHED_FOLDER). Skipping nanopub publish."; \
		exit 0; \
	fi; \
	publish_ts=$$(date -u +%Y%m%dT%H%M%SZ); \
	redirect_file="$(REDIRECT_FOLDER)/term-to-nanopub_$${publish_ts}.tsv"; \
	echo "Writing redirect mappings to $$redirect_file"; \
	uv run pubmate-publish \
		--assertion-folder $(UNPUBLISHED_FOLDER) \
		--private-key "$$NANOPUB_PRIVATE_KEY" \
		--public-key "$$NANOPUB_PUBLIC_KEY" \
		--intro-nanopub-uri "$$INTRO_NANOPUB_URI" \
		--redirect-output-file "$$redirect_file" \
		$(DRY)

mark-published: prepare
	@if [ -n "$(DRY)" ]; then \
		echo "DRY mode enabled. Keeping assertions in $(UNPUBLISHED_FOLDER)."; \
		exit 0; \
	fi
	@set -e; \
	files=$$(ls -1 $(UNPUBLISHED_FOLDER)/*.ttl 2>/dev/null || true); \
	if [ -z "$$files" ]; then \
		echo "No assertions found in $(UNPUBLISHED_FOLDER). Nothing to move."; \
		exit 0; \
	fi; \
	for src in $$files; do \
		name=$$(basename "$$src"); \
		dest="$(PUBLISHED_FOLDER)/$$name"; \
		if [ -e "$$dest" ]; then \
			ts=$$(date -u +%Y%m%d%H%M%S); \
			dest="$(PUBLISHED_FOLDER)/$${name%.ttl}_$$ts.ttl"; \
		fi; \
		mv "$$src" "$$dest"; \
		echo "Moved $$src -> $$dest"; \
	done

publish-pipeline: publish-nanopubs mark-published
pipeline: process-dropbox

test-flow:
	$(MAKE) validate-pipeline
	$(MAKE) publish-pipeline DRY=--dry-run

clean:
	rm -f $(OUT_FOLDER)/* $(UNPUBLISHED_FOLDER)/*.ttl
