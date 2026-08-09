import re

from libraryforge.versioning import (
    get_version_info,
    read_app_version,
    read_backend_package_version,
)


SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+"
    r"(?:-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


def test_app_version_is_semver():
    version = read_app_version()

    assert SEMVER_RE.fullmatch(
        version
    )


def test_backend_package_version_matches_app_version():
    package_version = (
        read_backend_package_version()
    )

    assert package_version is not None

    assert (
        package_version
        == read_app_version()
    )


def test_version_info_contains_build_identity():
    info = get_version_info(
        environment="test"
    )

    assert (
        info["name"]
        == "LibraryForge"
    )

    assert (
        info["version"]
        == read_app_version()
    )

    assert (
        info["environment"]
        == "test"
    )

    assert "git_sha" in info
    assert "git_dirty" in info
    assert "python_version" in info
    assert "django_version" in info
