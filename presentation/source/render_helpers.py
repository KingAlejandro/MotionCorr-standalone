"""Load the authored composition in memory for deterministic local capture."""
from pathlib import Path
import base64
import mimetypes
import re

def inline_composition(root: Path) -> str:
    html = (root / 'index.html').read_text()
    def script(m):
        src = m.group(1)
        return '<script>' + (root / src).read_text().replace('</script>', '<\\/script>') + '</script>'
    html = re.sub(r'<script\s+src="([^"]+)"\s*></script>', script, html)
    def image(m):
        src = m.group(1)
        path = root / src
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        return 'src="data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode() + '"'
    html = re.sub(r'src="(assets/[^\"]+)"', image, html)
    return html
