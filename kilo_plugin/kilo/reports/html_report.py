"""Self-contained HTML validation report."""

from __future__ import annotations

from html import escape
from typing import Any


def render_validation_html(data: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(issue['severity'])}</td>"
        f"<td>{escape(issue['code'])}</td>"
        f"<td>{escape(issue['message'])}</td>"
        f"<td>{escape(issue.get('path') or '')}</td>"
        "</tr>"
        for issue in data["issues"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Kilo — KiCad Localizer validation</title>
<style>
body{{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bbb;padding:.45rem;text-align:left}}
.ok{{color:#176b2c}}.bad{{color:#a42020}}
</style></head><body>
<h1>Kilo — KiCad Localizer validation</h1>
<p>Project: <strong>{escape(data['project'])}</strong></p>
<p class="{'ok' if data['valid'] else 'bad'}">
Result: {'valid' if data['valid'] else 'errors found'}</p>
<table><thead><tr><th>Severity</th><th>Code</th><th>Message</th><th>Path</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>
"""
