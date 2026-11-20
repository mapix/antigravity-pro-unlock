"""Exercise official skills CLI discovery, links, copies, repeat install and removal."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "antigravity-pro-unlock"
CLI = ROOT / "node_modules/.bin/skills"


def run(cwd, *args):
    result = subprocess.run([str(CLI), *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def validate_install(cwd, copied=False):
    canonical = cwd / ".agents/skills" / NAME
    claude = cwd / ".claude/skills" / NAME
    assert canonical.is_dir(), "Missing standard shared skill installation"
    assert claude.is_dir(), "Missing Claude Code projection"
    assert claude.is_symlink() is not copied, "Unexpected copy/link installation mode"
    for original in (ROOT / "skills" / NAME).rglob("*"):
        if original.is_file() and "__pycache__" not in original.parts:
            relative = original.relative_to(ROOT / "skills" / NAME)
            assert (canonical / relative).read_bytes() == original.read_bytes(), relative
            assert (claude / relative).read_bytes() == original.read_bytes(), relative
    subprocess.run([sys.executable, str(claude / "scripts/voice/build.py"), "--help"],
                   cwd=cwd, capture_output=True, check=True, timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(ROOT))
    args = parser.parse_args()
    if not CLI.exists():
        raise SystemExit("Run npm ci --ignore-scripts first")
    targets = ["-a", "codex", "-a", "claude-code", "-a", "cursor", "-a", "opencode"]
    with tempfile.TemporaryDirectory(prefix="pro-unlock-install-") as directory:
        work = Path(directory)
        before = set(work.iterdir())
        listing = run(work, "add", args.source, "--list")
        assert NAME in listing, "Skill not discoverable by the standard CLI"
        assert set(work.iterdir()) == before, "List modified the project"
        run(work, "add", args.source, "--skill", NAME, *targets, "-y")
        validate_install(work)
        run(work, "add", args.source, "--skill", NAME, *targets, "-y")
        validate_install(work)
        run(work, "remove", NAME, "-y")
        assert not (work / ".agents/skills" / NAME).exists()
        assert not (work / ".claude/skills" / NAME).exists()
        run(work, "add", args.source, "--skill", NAME, *targets, "--copy", "-y")
        validate_install(work, copied=True)
    print(json.dumps({"status": "passed", "source": args.source,
                      "cli_version": json.loads((ROOT / "node_modules/skills/package.json").read_text())["version"],
                      "agents": ["codex", "claude-code", "cursor", "opencode"],
                      "checks": ["discovery", "list-is-read-only", "link-install", "repeat-install", "remove", "copy-install"]}, indent=2))


if __name__ == "__main__":
    main()
