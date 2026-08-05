"""Shared Jinja2 environment for the web app."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
jinja_env.filters["urlencode"] = lambda s: quote(str(s), safe="")
jinja_env.filters["tojson"] = lambda v: json.dumps(v)
