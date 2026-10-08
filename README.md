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

## Employment notes

Each employment note has two copies. The note body is the website and LinkedIn text, capped at 2,000 characters. The CV reads `cv_content` from frontmatter and does not use the body.

```yaml
front_page: true
cv_content: |
  Intro paragraph.
  - An important point.
  - Some achievement.
```

`front_page: true` is set only on the four roles that fill page 1: Miro, DAZN, Tesco, and Velo. Every other employment note omits it. `cv_content` is a YAML literal block, so bullets stay markdown.

| Field | Where | Cap |
|---|---|---|
| body | website and LinkedIn | 2,000 characters |
| `cv_content` | `front_page: true` | 600 characters |
| `cv_content` | every other role | 200 characters, optional |

A front-page role must include `cv_content`. An older role with no `cv_content` is listed as company, role, and dates only. CV prose belongs in `cv_content`, not in a heading in the body.

Roles that are one continuous tenure share a `tenure` id. Page 2 draws those roles on one rail and prints the company name only on the newest role. The id is explicit. Notes with the same id must sit next to each other in date order, and on the same CV page.

## Project notes

A note in `content/projects` needs `title`, `role`, `status`, and `link`. The body is the one-line CV description. Active projects are listed first.