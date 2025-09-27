import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_subprocess.fake_process import FakeProcess

from extensions.extensions import (
    ConfigExtension,
    GitExtension,
    NvmExtension,
    UvExtension,
)

# ruff: noqa: S101


class TestGitExtension:
    def test_get_git_user_name(self, fp: FakeProcess) -> None:
        fp.register(["git", "config", "user.name"], stdout=["foo"])
        assert GitExtension.get_git_user_name("bar") == "foo"

        fp.register(["git", "config", "user.name"], stdout=[])
        assert GitExtension.get_git_user_name("bar") == "bar"

        fp.register(["git", "config", "user.name"], returncode=1)
        assert GitExtension.get_git_user_name("bar") == "bar"


class TestUvExtension:
    def test_get_python_version_existing(
        self,
        fp: FakeProcess,  # noqa: ARG002
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file(".python-version", contents="3.13.0")
        assert UvExtension.get_python_version("") == "3.13.0"

    def test_get_python_version_default(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython"],
            stdout="""[
  {"version": "3.14.0rc1"},
  {"version": "3.12.0"},
  {"version": "3.13.1"}
]""",
        )
        assert UvExtension.get_python_version("") == "3.13.1"

    def test_get_python_version_fails(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython"],
            stdout='[{"version": "3.14.0rc1"}]',
        )
        with pytest.raises(ValueError):
            UvExtension.get_python_version("")

    def test_get_python_packages(self, fp: FakeProcess) -> None:
        fp.register(
            ["uv", "pip", "list", "--format=json"],
            '[{"name": "foo"}, {"name": "bar"}]',
        )
        assert UvExtension.get_python_packages() == frozenset({"foo", "bar"})

    def test_get_python_packages_fails(self, fp: FakeProcess) -> None:
        fp.register(
            ["uv", "pip", "list", "--format=json"],
            "",
        )
        assert UvExtension.get_python_packages() == frozenset()

        fp.register(
            ["uv", "pip", "list", "--format=json"],
            returncode=1,
        )
        assert UvExtension.get_python_packages() == frozenset()


class TestNvmExtension:
    def test_get_node_version_existing(
        self,
        fp: FakeProcess,  # noqa: ARG002
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file(".nvmrc", contents="v24.6.0")
        assert NvmExtension.get_node_version("") == "v24.6.0"

    def test_get_node_version_default(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        fp.register(
            ["bash", "-c", 'source "${NVM_DIR}/nvm.sh" && nvm version stable'],
            stdout="v24.5.0",
        )
        assert NvmExtension.get_node_version("") == "v24.5.0"

    def test_get_node_packages(self, fp: FakeProcess) -> None:
        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            "{}",
        )
        assert NvmExtension.get_node_packages() == frozenset()

        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            '{"dependencies": {"foo": {}, "bar": {}}}',
        )
        assert NvmExtension.get_node_packages() == frozenset({"foo", "bar"})

    def test_get_node_packages_fails(self, fp: FakeProcess) -> None:
        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            "",
        )
        assert NvmExtension.get_node_packages() == frozenset()

        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            returncode=1,
        )
        assert NvmExtension.get_node_packages() == frozenset()


class TestConfigExtension:
    def test_expand_config(self) -> None:
        assert ConfigExtension.expand_config({}, {}) == {"file_types": [], "tools": []}
        assert ConfigExtension.expand_config({"file_types": None}, {"tools": None}) == {
            "file_types": [],
            "tools": [],
        }

        assert ConfigExtension.expand_config(
            {},
            {
                "file_types": ["shell"],
                "tools": ["pre-commit"],
            },
        ) == {
            "file_types": [
                "json",
                "python",
                "shell",
                "toml",
                "yaml",
            ],
            "tools": [
                "mypy",
                "npm",
                "pre-commit",
                "prettier",
                "ruff",
                "shellcheck",
                "shfmt",
                "tombi",
                "uv",
                "yamllint",
            ],
        }

        assert ConfigExtension.expand_config(
            {
                "file_types": ["markdown"],
                "tools": ["pytest"],
            },
            {
                "file_types": ["shell"],
                "tools": ["pre-commit"],
            },
        ) == {
            "file_types": [
                "json",
                "markdown",
                "python",
                "shell",
                "toml",
                "yaml",
            ],
            "tools": [
                "markdownlint",
                "mypy",
                "npm",
                "pre-commit",
                "prettier",
                "pytest",
                "ruff",
                "shellcheck",
                "shfmt",
                "tombi",
                "uv",
                "yamllint",
            ],
        }

    def test_detect_config(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file("foo.py", contents="")
        fs.create_file("bar/bar", contents="#!/bin/bash")
        fs.chmod("bar/bar", 0o700)
        fs.create_file("baz.bats", contents="")
        fs.create_file("conftest.py", contents="")

        fp.register(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            stdout=[
                "foo.py",
                "bar/bar",
                "baz.bats",
                "quux",
                "conftest.py",
            ],
        )
        fp.register(
            ["uv", "pip", "list", "--format=json"],
            '[{"name": "mypy"}]',
        )
        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            '{"dependencies": {"prettier": {}}}',
        )

        assert ConfigExtension.detect_config("") == {
            "file_types": ["python", "shell"],
            "tools": ["bats", "mypy", "prettier", "pytest"],
        }

    def test_file_type_tags(self) -> None:
        tags = ConfigExtension.file_type_tags("")
        assert tags
        for l in tags.values():
            assert l == sorted(l)
