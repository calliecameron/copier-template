from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from frozendict import frozendict

from extensions.extensions import (
    UV,
    BoolTomlValue,
    Config,
    ConfigExtension,
    GitExtension,
    Nvm,
    PythonExtension,
    StrTomlValue,
    Toml,
)

if TYPE_CHECKING:
    from pyfakefs.fake_filesystem import FakeFilesystem
    from pytest_mock import MockerFixture
    from pytest_subprocess.fake_process import FakeProcess

# ruff: noqa: S101


class TestGitExtension:
    def test_get_git_user_name(self, fp: FakeProcess) -> None:
        fp.register(["git", "config", "user.name"], stdout=["foo"])
        assert GitExtension.get_git_user_name("bar") == "foo"

        fp.register(["git", "config", "user.name"], stdout=[])
        assert GitExtension.get_git_user_name("bar") == "bar"

        fp.register(["git", "config", "user.name"], returncode=1)
        assert GitExtension.get_git_user_name("bar") == "bar"


class TestPythonExtension:
    def test_parse_version(self) -> None:
        assert PythonExtension.parse_version("3.13") == (3, 13)
        assert PythonExtension.parse_version("3.13.2") == (3, 13)
        with pytest.raises(ValueError):
            PythonExtension.parse_version("3")
        with pytest.raises(ValueError):
            PythonExtension.parse_version("foo")

    def test_parse_versions(self) -> None:
        assert PythonExtension.parse_versions([]) == []
        assert PythonExtension.parse_versions(["3.13", "3.12", "3.12"]) == [
            (3, 12),
            (3, 13),
        ]

    def test_join_versions(self) -> None:
        assert PythonExtension.join_versions([]) == []
        assert PythonExtension.join_versions([(3, 13), (3, 12), (3, 12)]) == [
            "3.12",
            "3.13",
        ]

    def test_enumerate_python_versions(self) -> None:
        assert PythonExtension.enumerate_python_versions("3.12", "3.12") == ["3.12"]
        assert PythonExtension.enumerate_python_versions("3.12", "3.14") == [
            "3.12",
            "3.13",
            "3.14",
        ]

        with pytest.raises(ValueError):
            PythonExtension.enumerate_python_versions("2.7", "3.13")
        with pytest.raises(ValueError):
            PythonExtension.enumerate_python_versions("3.14", "3.13")

    def test_filter_python_versions_leq(self) -> None:
        assert PythonExtension.filter_python_versions_leq([], "3.13") == []
        assert PythonExtension.filter_python_versions_leq(
            ["3.14", "3.12", "3.13", "3.12"],
            "3.13",
        ) == ["3.12", "3.13"]

    def test_increment_python_version(self) -> None:
        assert PythonExtension.increment_python_version("3.13") == "3.14"


class TestToml:
    def test_load_existing(self, fs: FakeFilesystem) -> None:
        fs.create_file("pyproject.toml", contents='foo = "bar"')
        assert Toml.load("pyproject.toml") == {"foo": "bar"}

    def test_load_default(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        assert Toml.load("pyproject.toml") == {}


class TestUV:
    def test_uv_version(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "--version"],
            stdout="uv 0.9.0",
        )
        assert UV.uv_version() == "0.9.0"

    def test_uv_version_fails(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "--version"],
            stdout="uv",
        )
        with pytest.raises(ValueError):
            UV.uv_version()

    def test_uv_build_spec(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        mocker.patch(
            "tempfile.TemporaryDirectory",
        ).return_value.__enter__.return_value = "/foo/bar"
        fp.register(
            [
                "uv",
                "init",
                "--name",
                "temp",
                "--bare",
                "--package",
                "--build-backend",
                "uv",
                "--vcs",
                "none",
                "--author-from",
                "none",
                "--no-workspace",
                "/foo/bar",
            ],
        )
        fs.create_file(
            "/foo/bar/pyproject.toml",
            contents="""
[build-system]
requires = ["foo=bar"]
""",
        )
        assert UV.uv_build_spec() == "foo=bar"

    def test_uv_build_spec_fails(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        mocker.patch(
            "tempfile.TemporaryDirectory",
        ).return_value.__enter__.return_value = "/foo/bar"
        fp.register(
            [
                "uv",
                "init",
                "--name",
                "temp",
                "--bare",
                "--package",
                "--build-backend",
                "uv",
                "--vcs",
                "none",
                "--author-from",
                "none",
                "--no-workspace",
                "/foo/bar",
            ],
        )
        fs.create_file("/foo/bar/pyproject.toml")
        with pytest.raises(ValueError):
            UV.uv_build_spec()

    def test_python_version_existing(
        self,
        fp: FakeProcess,  # noqa: ARG002
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file(".python-version", contents="3.13.0")
        assert UV.python_version("3.13") == "3.13.0"

    def test_python_version_existing_different_minor_version(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fs.create_file(".python-version", contents="3.12.0")
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython@3.13"],
            stdout="""[
  {"version": "3.13.0"},
  {"version": "3.13.1"},
  {"version": "3.13.2rc1"}
]""",
        )
        assert UV.python_version("3.13") == "3.13.1"

    def test_python_version_default(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython@3.12"],
            stdout="""[
  {"version": "3.12.0"},
  {"version": "3.12.1"},
  {"version": "3.12.2rc1"}
]""",
        )
        assert UV.python_version("3.12") == "3.12.1"

    def test_python_version_fails(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython@3.13"],
            stdout='[{"version": "3.14.0rc1"}]',
        )
        with pytest.raises(ValueError):
            UV.python_version("3.13")

    def test_installed_python_packages(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "pip", "list", "--format=json"],
            '[{"name": "foo"}, {"name": "bar"}]',
        )
        assert UV.installed_python_packages() == frozenset({"foo", "bar"})

    def test_installed_python_packages_fails(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "pip", "list", "--format=json"],
            "",
        )
        assert UV.installed_python_packages() == frozenset()

        fp.register(
            ["uv", "pip", "list", "--format=json"],
            returncode=1,
        )
        assert UV.installed_python_packages() == frozenset()


class TestNvm:
    def test_node_version_existing(
        self,
        fp: FakeProcess,  # noqa: ARG002
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file(".nvmrc", contents="v24.6.0")
        assert Nvm.node_version() == "v24.6.0"

    def test_node_version_default(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        fp.register(
            ["bash", "-c", 'source "${NVM_DIR}/nvm.sh" && nvm version stable'],
            stdout="v24.5.0",
        )
        assert Nvm.node_version() == "v24.5.0"

    def test_installed_node_packages(self, fp: FakeProcess) -> None:
        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            "{}",
        )
        assert Nvm.installed_node_packages() == frozenset()

        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            '{"dependencies": {"foo": {}, "bar": {}}}',
        )
        assert Nvm.installed_node_packages() == frozenset({"foo", "bar"})

    def test_installed_node_packages_fails(self, fp: FakeProcess) -> None:
        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            "",
        )
        assert Nvm.installed_node_packages() == frozenset()

        fp.register(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            returncode=1,
        )
        assert Nvm.installed_node_packages() == frozenset()


class TestTomlValue:
    def test_bool_toml_value(self, fs: FakeFilesystem) -> None:
        b = BoolTomlValue(filename="pyproject.toml", key="foo.bar")
        fs.create_file("pyproject.toml", contents="")
        assert b.get() is None
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]")
        assert b.get() is None
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = true")
        assert b.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = false")
        assert b.get() is False
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="foo = []")
        with pytest.raises(TypeError):
            b.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = 'baz'")
        with pytest.raises(TypeError):
            b.get()

        b = BoolTomlValue(filename="pyproject.toml", key="foo.bar", default=False)
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="")
        assert b.get() is False
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]")
        assert b.get() is False
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = true")
        assert b.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = false")
        assert b.get() is False
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="foo = []")
        with pytest.raises(TypeError):
            b.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = 'baz'")
        with pytest.raises(TypeError):
            b.get()

        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="")
        assert BoolTomlValue(filename="pyproject.toml", key="").get() is None

    def test_str_toml_value(self, fs: FakeFilesystem) -> None:
        s = StrTomlValue(filename="pyproject.toml", key="foo.bar")
        fs.create_file("pyproject.toml", contents="")
        assert s.get() is None
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]")
        assert s.get() is None
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = 'baz'")
        assert s.get() == "baz"
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="foo = []")
        with pytest.raises(TypeError):
            s.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = true")
        with pytest.raises(TypeError):
            s.get()

        s = StrTomlValue(filename="pyproject.toml", key="foo.bar", default="quux")
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="")
        assert s.get() == "quux"
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]")
        assert s.get() == "quux"
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = 'baz'")
        assert s.get() == "baz"
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="foo = []")
        with pytest.raises(TypeError):
            s.get()
        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="[foo]\nbar = true")
        with pytest.raises(TypeError):
            s.get()

        fs.remove("pyproject.toml")
        fs.create_file("pyproject.toml", contents="")
        assert StrTomlValue(filename="pyproject.toml", key="").get() is None


class TestConfig:
    def test_from_yaml(self) -> None:
        assert Config.from_yaml({}) == Config(
            file_types=frozenset(),
            tools=frozenset(),
            metadata=frozendict(),
        )

        assert Config.from_yaml(
            {
                "file_types": None,
                "tools": None,
                "metadata": None,
            },
        ) == Config(
            file_types=frozenset(),
            tools=frozenset(),
            metadata=frozendict(),
        )

        assert Config.from_yaml(
            {
                "file_types": ["foo", "bar"],
                "tools": ["baz", "quux"],
                "metadata": {
                    "a": "b",
                    "c": 2,
                },
            },
        ) == Config(
            file_types=frozenset({"bar", "foo"}),
            tools=frozenset({"baz", "quux"}),
            metadata=frozendict(
                {
                    "a": "b",
                    "c": 2,
                },
            ),
        )

        with pytest.raises(TypeError):
            Config.from_yaml({"file_types": {"foo": "bar"}})
        with pytest.raises(TypeError):
            Config.from_yaml({"tools": {"foo": "bar"}})
        with pytest.raises(TypeError):
            Config.from_yaml({"metadata": ["foo"]})

    def test_to_yaml(self) -> None:
        assert Config(
            file_types=frozenset(),
            tools=frozenset(),
            metadata=frozendict(),
        ).to_yaml() == {
            "file_types": [],
            "tools": [],
            "metadata": {},
        }

        assert Config(
            file_types=frozenset({"foo", "bar"}),
            tools=frozenset({"baz", "quux"}),
            metadata=frozendict({"a": "b", "c": 2}),
        ).to_yaml() == {
            "file_types": ["bar", "foo"],
            "tools": ["baz", "quux"],
            "metadata": {"a": "b", "c": 2},
        }


class TestConfigExtension:
    def test_expand_config(self) -> None:
        assert ConfigExtension.expand_config({}, {}) == {
            "file_types": [],
            "tools": [],
            "metadata": {},
        }
        assert ConfigExtension.expand_config(
            {"file_types": None, "metadata": None},
            {"tools": None},
        ) == {
            "file_types": [],
            "tools": [],
            "metadata": {},
        }

        assert ConfigExtension.expand_config(
            {},
            {
                "file_types": ["shell"],
                "tools": ["pre-commit"],
                "metadata": {"foo": "bar"},
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
                "node-license-checker",
                "npm",
                "pre-commit",
                "prettier",
                "python-license-checker",
                "ruff",
                "shellcheck",
                "shfmt",
                "tombi",
                "uv",
                "yamllint",
            ],
            "metadata": {
                "foo": "bar",
            },
        }

        assert ConfigExtension.expand_config(
            {
                "file_types": ["markdown"],
                "tools": ["pytest"],
                "metadata": {"baz": 2},
            },
            {
                "file_types": ["shell"],
                "tools": ["pre-commit"],
                "metadata": {"foo": "bar"},
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
                "node-license-checker",
                "npm",
                "pre-commit",
                "prettier",
                "pytest",
                "python-license-checker",
                "ruff",
                "shellcheck",
                "shfmt",
                "tombi",
                "uv",
                "yamllint",
            ],
            "metadata": {
                "foo": "bar",
                "baz": 2,
            },
        }

    def test_file_type_tags(self) -> None:
        assert ConfigExtension.file_type_tags() == {
            "shell": ["shell"],
            "python": ["pyi", "python"],
            "javascript": ["javascript"],
            "html": ["html"],
            "css": ["css"],
            "markdown": ["markdown"],
            "json": ["json"],
            "yaml": ["yaml"],
            "toml": ["toml"],
        }

    def test_detect_config(
        self,
        fp: FakeProcess,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        mocker.patch(
            "tempfile.TemporaryDirectory",
        ).return_value.__enter__.return_value = "/foo/bar"

        fs.create_file("foo.py", contents="")
        fs.create_file("bar/bar", contents="#!/bin/bash")
        fs.chmod("bar/bar", 0o700)
        fs.create_file("baz.bats", contents="")
        fs.create_file("conftest.py", contents="")
        fs.create_file(
            "pyproject.toml",
            contents="""
[project]
version = "1.2.3"

[tool.uv]
package = false
""",
        )
        fs.create_file(".nvmrc", contents="v24.6.0")
        fs.create_file(
            "/foo/bar/pyproject.toml",
            contents="""
[build-system]
requires = ["foo=bar"]
""",
        )

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
            ["uv", "--version"],
            stdout="uv 0.9.0",
        )
        fp.register(
            [
                "uv",
                "init",
                "--name",
                "temp",
                "--bare",
                "--package",
                "--build-backend",
                "uv",
                "--vcs",
                "none",
                "--author-from",
                "none",
                "--no-workspace",
                "/foo/bar",
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
            "metadata": {
                "uv_version": "0.9.0",
                "uv_build_spec": "foo=bar",
                "template_min_allowed_python_version": "3.12",
                "template_max_allowed_python_version": "3.14",
                "template_allowed_python_versions": [
                    "3.12",
                    "3.13",
                    "3.14",
                ],
                "node_version": "v24.6.0",
                "file_type_tags": {
                    "shell": ["shell"],
                    "python": ["pyi", "python"],
                    "javascript": ["javascript"],
                    "html": ["html"],
                    "css": ["css"],
                    "markdown": ["markdown"],
                    "json": ["json"],
                    "yaml": ["yaml"],
                    "toml": ["toml"],
                },
                "project_version": "1.2.3",
                "is_python_package": False,
            },
        }

    def test_python_version_exact(
        self,
        fp: FakeProcess,  # noqa: ARG002
        fs: FakeFilesystem,
    ) -> None:
        fs.create_file(".python-version", contents="3.13.0")
        assert ConfigExtension.python_version_exact("3.13") == "3.13.0"

    def test_python_packages(self) -> None:
        assert ConfigExtension.python_packages(
            {"tools": ["pytest", "ruff"]},
        ).keys() == {
            "pytest",
            "pytest-cov",
            "pytest-custom_exit_code",
            "ruff",
        }

    def test_node_packages(self) -> None:
        assert ConfigExtension.node_packages(
            {"tools": ["prettier", "stylelint"]},
        ).keys() == {
            "prettier",
            "stylelint",
            "stylelint-config-standard",
        }
