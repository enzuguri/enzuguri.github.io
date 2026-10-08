from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader
from jsonschema import Draft202012Validator
from livereload import Server

ROOT = Path(__file__).parent
VAULT_DIR = ROOT / "content"
DIST_DIR = ROOT / "dist"
TEMPLATE_DIR = ROOT / "templates"
CV_DATA = ROOT / "data" / "cv.json"
CV_SCHEMA = ROOT / "data" / "cv.schema.json"
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
    render_cv(environment)
    print(f"Built {len(notes)} note(s) and cv.html into {DIST_DIR}")


def load_cv() -> dict:
    return validate_cv(json.loads(CV_DATA.read_text(encoding="utf-8")))


def validate_cv(document: dict) -> dict:
    schema = json.loads(CV_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return document
    rendered = "\n".join(
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise SystemExit(f"CV data does not match data/cv.schema.json:\n{rendered}")


def markdown_to_cv_data(vault_dir: Path) -> dict:
    notes = _read_notes(vault_dir)
    by_type: dict[str, list[tuple[Path, dict, str]]] = {}
    for path, meta, body in notes:
        by_type.setdefault(_note_type(path, vault_dir, meta), []).append((path, meta, body))
    profile_notes = by_type.get("profile", [])
    roles = by_type.get("employment", [])
    _assert_tenures(roles)
    experience = _role_entries(roles, front_page=True)
    contact = _contact_data(by_type.get("contact", []))
    if not contact["role"] and experience:
        contact["role"] = experience[0]["title"]
    if not contact["phoneNumber"] or not contact["role"]:
        raise SystemExit("contact note is missing a telephone and a role")
    return validate_cv({
        "contact": contact,
        "profile": _profile_text(profile_notes),
        "skills": _skill_groups(by_type.get("skills", [])),
        "languages": _language_names(by_type.get("languages", [])),
        "education": _education_entries(by_type.get("education", [])),
        "experience": experience,
        "otherExperience": _role_entries(roles, front_page=False),
        "projects": _project_entries(by_type.get("project", [])),
    })


def _read_notes(vault_dir: Path) -> list[tuple[Path, dict, str]]:
    notes = []
    for source in sorted(vault_dir.rglob("*.md")):
        relative = source.relative_to(vault_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        meta, body = _read_frontmatter(source)
        published = meta.get("published", True)
        if published in {False, "false", "no", "0"}:
            continue
        notes.append((source, meta, body))
    return notes


def _read_frontmatter(source: Path) -> tuple[dict, str]:
    text = source.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    try:
        loaded = yaml.safe_load(text[4:end].expandtabs(2)) or {}
    except yaml.YAMLError as error:
        raise SystemExit(f"{source.name}: {error}") from error
    if not isinstance(loaded, dict):
        raise SystemExit(f"{source.name}: frontmatter is not a mapping")
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    return loaded, body


def _note_type(path: Path, vault_dir: Path, meta: dict) -> str:
    declared = meta.get("type")
    if isinstance(declared, str) and declared:
        return declared
    folder = path.relative_to(vault_dir).parts[0]
    return {"employment": "employment", "education": "education", "projects": "project"}.get(folder, "")


def _single_note(notes: list[tuple[Path, dict, str]], kind: str) -> tuple[Path, dict, str]:
    if len(notes) != 1:
        raise SystemExit(f"expected one {kind} note, found {len(notes)}")
    return notes[0]


def _contact_data(notes: list[tuple[Path, dict, str]]) -> dict:
    _, meta, body = _single_note(notes, "contact")
    phone = str(meta.get("telephone") or meta.get("phone") or "") or _phone_number(body)
    role = str(meta.get("role") or "") or _headline(body)
    return {
        "name": str(meta["name"]),
        "role": role,
        "phoneNumber": phone.strip(),
        "email": str(meta["email"]),
        "location": str(meta["location"]),
        "linkedin": str(meta["linkedin"]),
    } | ({"github": str(meta["github"])} if meta.get("github") else {})


def _phone_number(body: str) -> str:
    match = re.search(r"Mobile:\s*([+\d][\d\s()+-]*)", body)
    if match is None:
        return ""
    return re.sub(r"\s*<br\s*/?>\s*", "", match.group(1)).strip()


def _headline(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "<br" in stripped:
            continue
        if re.match(r"(Mobile|Email|LinkedIn|Website):", stripped):
            continue
        return stripped
    return ""


def _profile_text(notes: list[tuple[Path, dict, str]]) -> str:
    _, _, body = _single_note(notes, "profile")
    text = body  # Do not strip; preserve leading/trailing newlines
    if not text:
        raise SystemExit("profile note has no body")
    return text


def _skill_groups(skill_notes: list[tuple[Path, dict, str]]) -> list[dict]:
    if not skill_notes:
        return []
    _, _, body = _single_note(skill_notes, "skills")
    return _heading_lists(body)


def _language_names(notes: list[tuple[Path, dict, str]]) -> list[str]:
    if not notes:
        return []
    _, _, body = _single_note(notes, "languages")
    return _bullets(body)


def _heading_lists(body: str) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            current = {"type": title, "names": []} if title else None
            if current is not None:
                groups.append(current)
            continue
        if current is not None and stripped.startswith("- "):
            current["names"].append(stripped[2:].strip())
    return [group for group in groups if group["names"]]


def _bullets(body: str) -> list[str]:
    return [line.strip()[2:].strip() for line in body.splitlines() if line.strip().startswith("- ")]


def _education_entries(notes: list[tuple[Path, dict, str]]) -> list[dict]:
    entries = []
    for _, meta, body in notes:
        entry: dict[str, str] = {"title": str(meta["qualification"])}
        if meta.get("institution"):
            entry["institution"] = str(meta["institution"])
        date = _format_range(meta.get("start_date"), meta.get("end_date"))
        if date:
            entry["date"] = date
        detail = _education_detail(body)
        if detail:
            entry["detail"] = detail
        entries.append(entry)
    entries.sort(key=lambda entry: entry.get("date", ""), reverse=True)
    return entries


def _education_detail(body: str) -> str:
    prose, highlights = _split_copy(body)
    return " ".join(part for part in (prose, *highlights) if part)


def _role_entries(notes: list[tuple[Path, dict, str]], *, front_page: bool) -> list[dict]:
    selected = [item for item in notes if _is_front_page(item[1]) is front_page]
    selected.sort(key=lambda item: _recency(item[1]), reverse=True)
    roles = []
    for _, meta, body in selected:
        content, highlights = _copy(meta, body)
        role = {
            "title": str(meta["role"]),
            "company": str(meta["company"]),
            "date": _format_range(meta.get("start_date"), meta.get("end_date")),
            "content": content,
        }
        if highlights:
            role["highlights"] = highlights
        tenure = _tenure_id(meta)
        if tenure:
            role["tenure"] = tenure
        roles.append(role)
    return roles


def _project_entries(notes: list[tuple[Path, dict, str]]) -> list[dict]:
    selected = sorted(notes, key=lambda item: (str(item[1].get("status") or "") != "active", str(item[1].get("title") or item[0].stem).lower()))
    projects = []
    for path, meta, body in selected:
        content, _ = _copy(meta, body)
        project = {
            "title": str(meta.get("title") or path.stem),
            "role": str(meta["role"]),
            "status": str(meta["status"]),
            "content": content,
        }
        link = str(meta.get("link") or "").strip()
        if link:
            project["link"] = link
        projects.append(project)
    return projects


def _is_front_page(meta: dict) -> bool:
    return meta.get("front_page") in {True, "true", "yes", "1"}


def _tenure_id(meta: dict) -> str:
    return str(meta.get("tenure") or "").strip()


def _assert_tenures(notes: list[tuple[Path, dict, str]]) -> None:
    ordered = sorted(notes, key=lambda item: _recency(item[1]), reverse=True)
    closed: set[str] = set()
    index = 0
    while index < len(ordered):
        tenure = _tenure_id(ordered[index][1])
        if not tenure:
            index += 1
            continue
        role = f"{ordered[index][1].get('role')} at {ordered[index][1].get('company')}"
        if tenure in closed:
            raise SystemExit(f"tenure '{tenure}' on {role} is split by another role")
        end = index
        front_page = _is_front_page(ordered[index][1])
        while end + 1 < len(ordered) and _tenure_id(ordered[end + 1][1]) == tenure:
            end += 1
            if _is_front_page(ordered[end][1]) != front_page:
                raise SystemExit(f"tenure '{tenure}' includes roles on both CV pages")
        closed.add(tenure)
        index = end + 1


def _recency(meta: dict) -> tuple[str, str]:
    end = str(meta.get("end_date") or meta.get("date") or "")
    start = str(meta.get("start_date") or "")
    if end.lower() == "present":
        end = "9999-99"
    return end, start


def _copy(meta: dict, body: str) -> tuple[str, list[str]]:
    # cv_content is the short CV copy. The note body is the longer LinkedIn version.
    raw = meta.get("cv_content")
    text = raw if isinstance(raw, str) and raw.strip() else body
    content, highlights = _split_copy(text)
    if content:
        return content, highlights
    if not highlights:
        raise SystemExit(f"{meta.get('company') or meta.get('title') or 'note'} has no CV copy")
    return highlights[0], highlights[1:]


def _split_copy(text: str) -> tuple[str, list[str]]:
    prose: list[str] = []
    highlights: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "Key activities included:":
            continue
        if stripped.startswith("- "):
            highlights.append(stripped[2:].strip())
        else:
            prose.append(stripped)
    return " ".join(prose), highlights


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _format_date(value: object) -> str:
    text = str(value).strip()
    if not text or text == "None":
        return ""
    if text.lower() == "present":
        return "present"
    if re.fullmatch(r"\d{4}", text):
        return text
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if match is None:
        return text
    year, month = match.groups()
    return f"{_MONTHS[int(month) - 1]} {year}"


def _format_range(start: object, end: object) -> str:
    start_text = _format_date(start)
    end_text = _format_date(end)
    if start_text and end_text:
        return f"{start_text} – {end_text}"
    return start_text or end_text


def render_cv(environment: Environment) -> None:
    cv = markdown_to_cv_data(configured_vault())
    html = environment.get_template("cv.html").render(cv=cv)
    (DIST_DIR / "cv.html").write_text(html, encoding="utf-8")
    stylesheet = ROOT / "stylesheets" / "cv.css"
    if stylesheet.is_file():
        shutil.copy2(stylesheet, DIST_DIR / "cv.css")
    print(
        f"CV {cv['contact']['name']}: "
        f"{len(cv['experience'])} roles, "
        f"{len(cv['otherExperience'])} other, "
        f"{len(cv['projects'])} projects"
    )


def serve() -> None:
    build_site()
    server = Server()
    server.watch(str(configured_vault() / "**/*"), build_site)
    server.watch(str(TEMPLATE_DIR / "*.html"), build_site)
    server.watch(str(ROOT / "stylesheets" / "*.css"), build_site)
    server.watch(str(ROOT / "data" / "*.json"), build_site)
    print("Serving preview at http://127.0.0.1:5500")
    server.serve(root=str(DIST_DIR), port=5500)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        serve()
    else:
        build_site()


if __name__ == "__main__":
    main()