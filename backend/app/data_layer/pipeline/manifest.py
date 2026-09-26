from pathlib import Path
import json

def build_manifest(root: str) -> dict:
    p = Path(root)
    return {
        "root": str(p),
        "files": sorted(str(x.relative_to(p)) for x in p.rglob("*") if x.is_file()),
    }

def write_manifest(root: str, output: str) -> None:
    Path(output).write_text(json.dumps(build_manifest(root), indent=2), encoding="utf-8")
