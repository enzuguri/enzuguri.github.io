# Digital Garden

This repository builds the Markdown notes in `content/` into static HTML in `dist/`.

## Setup

```sh
uv sync
```

Build the site with `uv run garden`, or start a live-reloading preview with `uv run garden dev`.

Set `VAULT_DIR` to build a different Obsidian vault:

```sh
VAULT_DIR=/path/to/vault uv run garden
```

Notes with `published: false` in their frontmatter are skipped. Nested note directories and non-Markdown attachments are preserved in `dist/`.