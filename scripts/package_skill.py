"""Build a reproducible skill-only ZIP and SHA-256 without private runtime data."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "antigravity-pro-unlock"
SOURCE = ROOT / "skills" / NAME


def main():
    version = json.loads((ROOT / "package.json").read_text())["version"]
    files = [SOURCE / "SKILL.md", SOURCE / "LICENSE",
             SOURCE / "references/mechanics.md", SOURCE / "scripts/antigravity_pro_unlock.py"]
    for file in files:
        if not file.is_file() or file.is_symlink():
            raise SystemExit(f"Missing or linked package input: {file}")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / f"{NAME}-{version}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for file in sorted(files):
            info = zipfile.ZipInfo(str(Path(NAME) / file.relative_to(SOURCE)), (2026, 11, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if file.suffix == ".py" else 0o100644) << 16
            bundle.writestr(info, file.read_bytes())
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert len(bundle.namelist()) == len(files)
        compile(bundle.read(f"{NAME}/scripts/antigravity_pro_unlock.py"), "antigravity_pro_unlock.py", "exec")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{checksum}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "version": version, "sha256": checksum, "files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
