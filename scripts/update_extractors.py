"""Upgrade extractors in the current environment, then record tested versions."""

import importlib.metadata
from pathlib import Path
import re
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]", "gallery-dl"],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=root, check=True
    )
    path = root / "requirements.txt"
    text = path.read_text(encoding="utf-8")
    for package, requirement in (("yt-dlp", "yt-dlp[default]"), ("gallery-dl", "gallery-dl")):
        version = importlib.metadata.version(package)
        text = re.sub(
            r"^" + re.escape(requirement) + r"==[^\r\n]+",
            f"{requirement}=={version}",
            text,
            flags=re.MULTILINE,
        )
        print(f"{package}: {version}")
    path.write_text(text, encoding="utf-8")
    print("Tests passed. Extractor pins updated in requirements.txt. Rebuild Docker if used.")


if __name__ == "__main__":
    main()
