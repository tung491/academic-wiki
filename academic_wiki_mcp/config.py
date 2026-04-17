import os
from pathlib import Path

WIKI_ROOT = Path(os.environ.get("WIKI_ROOT", "~/ObsidianVault/03-Resources")).expanduser()
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
BROWSER_TIMEOUT = int(os.environ.get("BROWSER_TIMEOUT", "15000"))
