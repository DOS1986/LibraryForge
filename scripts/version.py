from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
BACKEND_PYPROJECT = ROOT / "backend" / "pyproject.toml"
FRONTEND_PACKAGE = ROOT / "frontend" / "package.json"
FRONTEND_BUILD_INFO = (
    ROOT
    / "frontend"
    / "public"
    / "build-info.json"
)
GITIGNORE = ROOT / ".gitignore"

SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

PREPARE_FRONTEND_COMMAND = (
    "python ../scripts/version.py prepare-frontend"
)


def fail(message: str):
    print(
        f"ERROR: {message}",
        file=sys.stderr,
    )

    raise SystemExit(1)


def validate_version(
    value: str,
):
    version = value.strip()

    if not SEMVER_RE.fullmatch(
        version
    ):
        fail(
            "Version must use Semantic Versioning, "
            "for example 0.1.0-alpha.1 or 1.0.0."
        )

    return version


def read_canonical_version():
    if not VERSION_FILE.exists():
        fail(
            "Missing canonical version file: "
            f"{VERSION_FILE}"
        )

    return validate_version(
        VERSION_FILE.read_text(
            encoding="utf-8"
        )
    )


def read_backend_version():
    if not BACKEND_PYPROJECT.exists():
        fail(
            "Missing backend pyproject: "
            f"{BACKEND_PYPROJECT}"
        )

    text = BACKEND_PYPROJECT.read_text(
        encoding="utf-8"
    )

    project_match = re.search(
        r"(?ms)^\[project\]\s*$"
        r"(?P<body>.*?)(?=^\[|\Z)",
        text,
    )

    if not project_match:
        fail(
            "Could not find [project] in "
            "backend/pyproject.toml."
        )

    version_match = re.search(
        r'(?m)^version[ \t]*=[ \t]*"'
        r'(?P<version>[^"]+)"[ \t]*$',
        project_match.group(
            "body"
        ),
    )

    if not version_match:
        fail(
            "Could not find project.version in "
            "backend/pyproject.toml."
        )

    return version_match.group(
        "version"
    )


def read_frontend_package():
    if not FRONTEND_PACKAGE.exists():
        fail(
            "Missing frontend package.json: "
            f"{FRONTEND_PACKAGE}"
        )

    try:
        return json.loads(
            FRONTEND_PACKAGE.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError as exc:
        fail(
            "frontend/package.json is not valid JSON: "
            f"{exc}"
        )


def read_frontend_version():
    data = read_frontend_package()

    value = data.get(
        "version"
    )

    if not isinstance(
        value,
        str,
    ):
        fail(
            "frontend/package.json does not contain "
            "a string version."
        )

    return value


def update_backend_version(
    version: str,
):
    text = BACKEND_PYPROJECT.read_text(
        encoding="utf-8"
    )

    project_match = re.search(
        r"(?ms)^\[project\]\s*$"
        r"(?P<body>.*?)(?=^\[|\Z)",
        text,
    )

    if not project_match:
        fail(
            "Could not find [project] in "
            "backend/pyproject.toml."
        )

    body = project_match.group(
        "body"
    )

    updated_body, count = re.subn(
        r'(?m)^version[ \t]*=[ \t]*"[^"]+"[ \t]*$',
        f'version = "{version}"',
        body,
        count=1,
    )

    if count != 1:
        fail(
            "Could not update project.version in "
            "backend/pyproject.toml."
        )

    updated = (
        text[
            :project_match.start(
                "body"
            )
        ]
        + updated_body
        + text[
            project_match.end(
                "body"
            ):
        ]
    )

    BACKEND_PYPROJECT.write_text(
        updated,
        encoding="utf-8",
    )


def write_frontend_package(
    data,
):
    FRONTEND_PACKAGE.write_text(
        (
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ),
        encoding="utf-8",
    )


def update_frontend_version(
    version: str,
):
    data = read_frontend_package()

    data[
        "version"
    ] = version

    write_frontend_package(
        data
    )


def _git(
    *args: str,
):
    try:
        result = subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return None

    value = result.stdout.strip()

    return value or None


def get_git_sha():
    return _git(
        "rev-parse",
        "HEAD",
    )


def get_git_branch():
    return _git(
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
    )


def get_git_dirty():
    status = _git(
        "status",
        "--porcelain",
    )

    if status is None:
        return None

    return bool(
        status
    )


def prepare_frontend():
    version = read_canonical_version()

    FRONTEND_BUILD_INFO.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    git_sha = get_git_sha()

    data = {
        "name":
            "LibraryForge",

        "version":
            version,

        "git_sha":
            git_sha,

        "git_short_sha":
            (
                git_sha[:8]
                if git_sha
                else None
            ),

        "git_branch":
            get_git_branch(),

        "git_dirty":
            get_git_dirty(),

        "build_time":
            datetime.now(
                UTC
            ).isoformat(),
    }

    FRONTEND_BUILD_INFO.write_text(
        (
            json.dumps(
                data,
                indent=2,
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    print(
        "Prepared frontend build metadata:"
    )

    print(
        f"  version: {version}"
    )

    print(
        "  commit:  "
        + (
            data[
                "git_short_sha"
            ]
            or "unknown"
        )
    )

    print(
        "  dirty:   "
        + str(
            data[
                "git_dirty"
            ]
        )
    )

    return data


def _append_gitignore_entry():
    entry = (
        "/frontend/public/build-info.json"
    )

    existing = (
        GITIGNORE.read_text(
            encoding="utf-8"
        )
        if GITIGNORE.exists()
        else ""
    )

    lines = {
        line.strip()
        for line in existing.splitlines()
    }

    if entry in lines:
        return

    separator = (
        ""
        if not existing
        or existing.endswith(
            "\n"
        )
        else "\n"
    )

    block = (
        f"{separator}\n"
        "# Generated LibraryForge build metadata\n"
        f"{entry}\n"
    )

    with GITIGNORE.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            block
        )


def _chain_script(
    existing: str | None,
    command: str,
):
    if not existing:
        return command

    if command in existing:
        return existing

    return (
        f"{existing} && {command}"
    )


def install_frontend_hooks():
    data = read_frontend_package()

    scripts = data.get(
        "scripts"
    )

    if not isinstance(
        scripts,
        dict,
    ):
        scripts = {}

        data[
            "scripts"
        ] = scripts

    scripts[
        "predev"
    ] = _chain_script(
        scripts.get(
            "predev"
        ),
        PREPARE_FRONTEND_COMMAND,
    )

    scripts[
        "prebuild"
    ] = _chain_script(
        scripts.get(
            "prebuild"
        ),
        PREPARE_FRONTEND_COMMAND,
    )

    scripts[
        "version:show"
    ] = (
        "python ../scripts/version.py show"
    )

    scripts[
        "version:check"
    ] = (
        "python ../scripts/version.py check"
    )

    write_frontend_package(
        data
    )

    _append_gitignore_entry()

    print(
        "Installed frontend version hooks:"
    )

    print(
        "  npm run dev   -> refresh build-info.json"
    )

    print(
        "  npm run build -> refresh build-info.json"
    )


def sync_versions(
    version: str | None = None,
):
    canonical = validate_version(
        version
        or read_canonical_version()
    )

    VERSION_FILE.write_text(
        canonical + "\n",
        encoding="utf-8",
    )

    update_backend_version(
        canonical
    )

    update_frontend_version(
        canonical
    )

    return canonical


def check_versions():
    canonical = read_canonical_version()
    backend = read_backend_version()
    frontend = read_frontend_version()

    rows = [
        (
            "VERSION",
            canonical,
        ),
        (
            "backend/pyproject.toml",
            backend,
        ),
        (
            "frontend/package.json",
            frontend,
        ),
    ]

    for (
        label,
        value,
    ) in rows:
        marker = (
            "OK"
            if value == canonical
            else "MISMATCH"
        )

        print(
            f"{marker:8} "
            f"{label:28} "
            f"{value}"
        )

    mismatches = [
        (
            label,
            value,
        )
        for (
            label,
            value,
        ) in rows[
            1:
        ]
        if value != canonical
    ]

    if mismatches:
        fail(
            "Version files are out of sync. "
            "Run: python scripts/version.py sync"
        )

    print(
        "\nLibraryForge versions are synchronized."
    )


def set_version(
    version: str,
):
    canonical = sync_versions(
        version
    )

    prepare_frontend()

    print(
        f"\nLibraryForge version set to {canonical}."
    )

    print(
        "Updated:"
    )

    print(
        "  VERSION"
    )

    print(
        "  backend/pyproject.toml"
    )

    print(
        "  frontend/package.json"
    )

    print(
        "  frontend/public/build-info.json"
    )


def show_versions():
    canonical = read_canonical_version()

    print(
        f"LibraryForge: {canonical}"
    )

    print(
        "Backend:      "
        f"{read_backend_version()}"
    )

    print(
        "Frontend:     "
        f"{read_frontend_version()}"
    )


def check_tag(
    tag: str,
):
    expected = (
        f"v{read_canonical_version()}"
    )

    if tag != expected:
        fail(
            f"Git tag {tag!r} does not match "
            f"VERSION. Expected {expected!r}."
        )

    print(
        f"Git tag matches VERSION: {tag}"
    )


def install():
    version = sync_versions()

    install_frontend_hooks()

    prepare_frontend()

    print(
        "\nLibraryForge versioning installed "
        f"for {version}."
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "LibraryForge application "
            "version manager."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "install",
        help=(
            "One-time setup: synchronize versions, "
            "install frontend hooks, and prepare "
            "frontend build metadata."
        ),
    )

    subparsers.add_parser(
        "show",
        help=(
            "Show canonical, backend, and frontend "
            "versions."
        ),
    )

    subparsers.add_parser(
        "sync",
        help=(
            "Copy VERSION into backend and frontend "
            "package metadata."
        ),
    )

    subparsers.add_parser(
        "check",
        help=(
            "Fail if VERSION, backend, and frontend "
            "versions differ."
        ),
    )

    subparsers.add_parser(
        "prepare-frontend",
        help=(
            "Generate frontend/public/build-info.json "
            "for the current Git checkout."
        ),
    )

    set_parser = subparsers.add_parser(
        "set",
        help=(
            "Set a new semantic version and "
            "synchronize all version files."
        ),
    )

    set_parser.add_argument(
        "version"
    )

    tag_parser = subparsers.add_parser(
        "check-tag",
        help=(
            "Verify a Git tag matches the "
            "canonical VERSION."
        ),
    )

    tag_parser.add_argument(
        "tag"
    )

    return parser


def main():
    args = (
        build_parser()
        .parse_args()
    )

    if args.command == "install":
        install()
        return

    if args.command == "show":
        show_versions()
        return

    if args.command == "sync":
        version = sync_versions()

        print(
            "Synchronized LibraryForge "
            f"{version}."
        )

        return

    if args.command == "check":
        check_versions()
        return

    if args.command == "prepare-frontend":
        prepare_frontend()
        return

    if args.command == "set":
        set_version(
            args.version
        )

        return

    if args.command == "check-tag":
        check_tag(
            args.tag
        )

        return

    fail(
        f"Unknown command: {args.command}"
    )


if __name__ == "__main__":
    main()
