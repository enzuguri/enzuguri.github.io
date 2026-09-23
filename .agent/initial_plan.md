Here is a complete, standalone technical specification document you can hand off to another agent. It includes the architecture, directory structure, core script implementation, and next steps for implementation.

Technical Specification: Python Static Site Generator (SSG) for Obsidian Vaults
1. Executive Summary
This document specifies the design for a custom, lightweight Python-based Static Site Generator (SSG). The system converts a standard local Obsidian vault into a static HTML digital garden.

The architecture uses:

obsidiantools: Parses the Obsidian vault structure, short-path wikilinks ([[Note Name]]), frontmatter, and backlink graphs.

Jinja2: Handles page layout compilation and HTML rendering.

Python-Markdown & pymdown-extensions: Converts Markdown content to sanitized HTML with support for standard Obsidian formatting (task lists, code blocks, tables).

livereload: Provides local development mode with live browser reloading on file changes.

2. System Architecture & Data Flow
[ Obsidian Vault (.md files) ]
              │
              ▼
   [ obsidiantools Engine ]  ──► (Resolves Wikilinks & Backlinks)
              │
              ▼
    [ Python-Markdown ]       ──► (Converts AST/Markdown to HTML)
              │
              ▼
      [ Jinja2 Engine ]       ──► (Injects Content into base.html / note.html)
              │
              ▼
  [ Output Directory (/dist) ] ──► (Served locally via LiveReload OR Deployed to Static Host)
3. Directory Structure
The project repository must follow this layout:

Plaintext
my_ssg/
├── vault/                # Target Obsidian Vault directory
│   ├── index.md          # Entrypoint / homepage
│   └── notes/            # Vault notes and subfolders
├── templates/            # Jinja2 template files
│   ├── base.html         # Global layout (HTML wrapper, CSS, nav)
│   └── note.html         # Individual note rendering template
├── dist/                 # Output directory for generated HTML files (gitignored)
├── generator.py          # Main Python script (Build + Dev mode)
├── requirements.txt      # Project dependencies
└── README.md
4. Dependencies (requirements.txt)
Plaintext
obsidiantools>=0.10.0
jinja2>=3.1.0
markdown>=3.5.0
pymdown-extensions>=10.0
livereload>=2.6.0
5. Template Specifications
templates/base.html
Provides the core layout, basic styling, and navigation:

HTML
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Digital Garden{% endblock %}</title>
    <style>
        :root {
            --bg-color: #ffffff;
            --text-color: #1a1a1a;
            --accent-color: #2563eb;
            --card-bg: #f8fafc;
            --border-color: #e2e8f0;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #0f172a;
                --text-color: #f8fafc;
                --accent-color: #60a5fa;
                --card-bg: #1e293b;
                --border-color: #334155;
            }
        }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            max-width: 800px;
            margin: 2rem auto;
            padding: 0 1rem;
            line-height: 1.6;
        }
        a { color: var(--accent-color); text-decoration: none; }
        a:hover { text-decoration: underline; }
        nav { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border-color); }
        .backlinks {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 1rem 1.5rem;
            border-radius: 8px;
            margin-top: 3rem;
        }
        .backlinks h3 { margin-top: 0; font-size: 1.1rem; }
        .backlinks ul { padding-left: 1.2rem; margin-bottom: 0; }
    </style>
</head>
<body>
    <nav>
        <a href="/index.html"><strong> Home</strong></a>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
templates/note.html
Extends base.html to display the note title, compiled body, and backlink listing:

HTML
{% extends "base.html" %}

{% block title %}{{ title }} - Digital Garden{% endblock %}

{% block content %}
    <article>
        <h1>{{ title }}</h1>
        <div class="note-body">
            {{ html_content | safe }}
        </div>
    </article>

    {% if backlinks %}
    <section class="backlinks">
        <h3>Linked References</h3>
        <ul>
            {% for page in backlinks %}
            <li><a href="/{{ page }}.html">{{ page }}</a></li>
            {% endfor %}
        </ul>
    </section>
    {% endif %}
{% endblock %}
6. Core Engine (generator.py)
The primary script handles building static pages and running a live-reloading development preview server.

Python
import sys
import shutil
from pathlib import Path
import markdown
import obsidiantools.api as otools
from jinja2 import Environment, FileSystemLoader
from livereload import Server

# Filepath Configuration
VAULT_DIR = Path("./vault")
DIST_DIR = Path("./dist")
TEMPLATE_DIR = Path("./templates")

# Initialize Jinja2 Environment
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
note_template = env.get_template("note.html")


def build_site():
    """Reads the Obsidian vault, transforms Markdown/wikilinks, and outputs HTML."""
    print("Building site...")

    # Reset output directory
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Gather vault metadata and link relationships
    vault = otools.Vault(VAULT_DIR).connect().gather()

    # 2. Configure Markdown parser with PyMdown extensions
    md = markdown.Markdown(
        extensions=[
            "extra",
            "codehilite",
            "pymdownx.tasklist",
            "pymdownx.superfences",
            "pymdownx.tilde",
        ]
    )

    # 3. Process each note in the vault index
    for note_title, source_text in vault.source_text_index.items():
        processed_text = source_text

        # Transform [[Wikilinks]] into relative HTML hyper links
        for wikilink in vault.get_wikilinks(note_title):
            processed_text = processed_text.replace(
                f"[[{wikilink}]]", f"[{wikilink}](/{wikilink}.html)"
            )

        # Convert Markdown string to HTML
        html_content = md.convert(processed_text)
        md.reset()  # Reset state for next iteration

        # Fetch backlinks targeting current note
        backlinks = vault.get_backlinks(note_title)

        # Render complete template
        output_html = note_template.render(
            title=note_title,
            html_content=html_content,
            backlinks=backlinks,
        )

        # Save rendered HTML to output folder
        out_file = DIST_DIR / f"{note_title}.html"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(output_html, encoding="utf-8")

    print(f"Build successful. Output generated in '{DIST_DIR}'.")


def serve():
    """Launches local dev server with hot-reloading on vault/template edits."""
    build_site()
    server = Server()
    
    # Watch directory trees for changes
    server.watch(str(VAULT_DIR / "**/*.md"), build_site)
    server.watch(str(TEMPLATE_DIR / "*.html"), build_site)
    
    print("Serving preview at http://127.0.0.1:5500")
    server.serve(root=str(DIST_DIR), port=5500)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        serve()
    else:
        build_site()
7. Execution Instructions
Install requirements:

Bash
pip install -r requirements.txt
Run local live preview server:

Bash
python generator.py dev
Compile static assets for production:

Bash
python generator.py
8. Requirements for Building Agent
When implementing this script, ensure the following features are handled or planned for subsequent passes:

Image & Attachment Sync: Add logic to copy non-Markdown files (.png, .jpg, .pdf) from the vault into dist/ and rewrite ![[image.png]] embed syntax.

Frontmatter Filtering: Read frontmatter fields (e.g., published: false) to skip rendering private or draft notes.

Subfolder Path Preservation: Ensure nested vault directories retain their relative routing structure when writing output files to dist/.