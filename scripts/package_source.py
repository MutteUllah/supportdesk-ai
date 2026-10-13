"""Create a clean source archive without dependencies, runtime data, credentials, or traces."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
destination = root.parent / "supportdesk-ai.zip"
excluded_directories = {
    ".git",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".local-storage",
    "test-results",
    "playwright-report",
    ".venv",
}


def files(directory):
    for path in sorted(directory.iterdir()):
        if path.name in excluded_directories or path.is_symlink():
            continue
        if path.is_dir():
            yield from files(path)
        elif (
            path.name == ".env"
            or path.name.startswith(".env.")
            and path.name != ".env.example"
        ) or path.suffix in {".db", ".pyc", ".tsbuildinfo", ".log"}:
            continue
        else:
            yield path


with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in files(root):
        archive.write(path, Path(root.name) / path.relative_to(root))
print(f"Created {destination.name} ({destination.stat().st_size:,} bytes)")
