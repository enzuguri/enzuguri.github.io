from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader
from livereload import Server

ROOT = Path(__file__).parent
VAULT_DIR = ROOT / "content"
DIST_DIR = ROOT / "dist"
TEMPLATE_DIR = ROOT / "templates"
WIKILINK_PATTERN = re.compile(r"(!?)\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")


@dataclass(frozen=True)
class Note:
    source: Path
    relative_path: Path
    title: str
    url: str
    metadata: dict[str, list[str]]


def configured_vault() -> Path:
    return Path(os.environ.get("VAULT_DIR", str(VAULT_DIR))).resolve()


def parse_note(source: Path, vault_dir: Path) -> Note | None:
    relative_path = source.relative_to(vault_dir)
    parser = markdown.Markdown(extensions=["meta"])
    parser.convert(source.read_text(encoding="utf-8"))
    metadata = parser.Meta
    if metadata.get("published", ["true"])[0].lower() in {"false", "no", "0"}:
        return None
    url_path = relative_path.with_suffix(".html")
    return Note(source, relative_path, source.stem, url_path.as_posix(), metadata)


def collect_notes(vault_dir: Path) -> list[Note]:
    notes = []
    for source in sorted(vault_dir.rglob("*.md")):
        if any(part.startswith(".") for part in source.relative_to(vault_dir).parts):
            continue
        note = parse_note(source, vault_dir)
        if note is not None:
            notes.append(note)
    return notes


def note_lookup(notes: list[Note]) -> dict[str, Note]:
    lookup: dict[str, Note] = {}
    for note in notes:
        lookup[note.relative_path.with_suffix("").as_posix()] = note
        lookup.setdefault(note.title, note)
    return lookup


def render_body(note: Note, notes_by_name: dict[str, Note], parser: markdown.Markdown) -> str:
    source = note.source.read_text(encoding="utf-8")

    def replace_link(match: re.Match[str]) -> str:
        is_embed, target, label = match.groups()
        if is_embed:
            return match.group(0)
        target_note = notes_by_name.get(target.strip())
        if target_note is None:
            return label or target
        return f"[{label or target_note.title}]({target_note.url})"

    source = WIKILINK_PATTERN.sub(replace_link, source)
    return parser.convert(source)


def build_site() -> None:
    vault_dir = configured_vault()
    if not vault_dir.is_dir():
        raise SystemExit(f"Vault directory does not exist: {vault_dir}")

    notes = collect_notes(vault_dir)
    notes_by_name = note_lookup(notes)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    environment = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = environment.get_template("note.html")
    parser = markdown.Markdown(
        extensions=[
            "extra",
            "meta",
            "codehilite",
            "pymdownx.tasklist",
            "pymdownx.superfences",
            "pymdownx.tilde",
        ]
    )
    backlinks = {note.url: [] for note in notes}
    for note in notes:
        for target in WIKILINK_PATTERN.findall(note.source.read_text(encoding="utf-8")):
            target_note = notes_by_name.get(target[1].strip())
            if target_note is not None and note not in backlinks[target_note.url]:
                backlinks[target_note.url].append(note)

    for note in notes:
        html = render_body(note, notes_by_name, parser)
        parser.reset()
        output = template.render(
            title=note.title,
            html_content=html,
            backlinks=backlinks[note.url],
            note_url=note.url,
        )
        destination = DIST_DIR / note.url
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding="utf-8")

    for asset in vault_dir.rglob("*"):
        relative = asset.relative_to(vault_dir)
        if asset.is_file() and asset.suffix.lower() != ".md" and not any(part.startswith(".") for part in relative.parts):
            destination = DIST_DIR / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, destination)
    stylesheet = ROOT / "stylesheets" / "styles.css"
    if stylesheet.is_file():
        shutil.copy2(stylesheet, DIST_DIR / "styles.css")
    print(f"Built {len(notes)} note(s) into {DIST_DIR}")


def serve() -> None:
    build_site()
    server = Server()
    server.watch(str(configured_vault() / "**/*"), build_site)
    server.watch(str(TEMPLATE_DIR / "*.html"), build_site)
    print("Serving preview at http://127.0.0.1:5500")
    server.serve(root=str(DIST_DIR), port=5500)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        serve()
    else:
        build_site()


if __name__ == "__main__":
    main()