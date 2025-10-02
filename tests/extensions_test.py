import pytest
from frozendict import frozendict
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_subprocess.fake_process import FakeProcess

from extensions.extensions import (
    BoolTomlValue,
    Config,
    ConfigExtension,
    GitExtension,
    NvmExtension,
    StrTomlValue,
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

    def test_get_pyproject_toml_existing(self, fs: FakeFilesystem) -> None:
        fs.create_file("pyproject.toml", contents='foo = "bar"')
        assert UvExtension.get_pyproject_toml() == {"foo": "bar"}

    def test_get_pyproject_toml_default(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
    ) -> None:
        assert UvExtension.get_pyproject_toml() == {}


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


class TestTomlValue:
    def test_bool_toml_value(self) -> None:
        b = BoolTomlValue(key="foo.bar")
        assert b.get({}) is None
        assert b.get({"foo": {}}) is None
        assert b.get({"foo": {"bar": True}})
        assert not b.get({"foo": {"bar": False}})
        with pytest.raises(TypeError):
            b.get({"foo": []})
        with pytest.raises(TypeError):
            b.get({"foo": {"bar": "baz"}})

        assert BoolTomlValue(key="").get({}) is None

    def test_str_toml_value(self) -> None:
        s = StrTomlValue(key="foo.bar")
        assert s.get({}) is None
        assert s.get({"foo": {}}) is None
        assert s.get({"foo": {"bar": "baz"}}) == "baz"
        with pytest.raises(TypeError):
            s.get({"foo": []})
        with pytest.raises(TypeError):
            s.get({"foo": {"bar": True}})

        assert StrTomlValue(key="").get({}) is None


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
            "metadata": {},
        }

    def test_file_type_tags(self) -> None:
        tags = ConfigExtension.file_type_tags("")
        assert tags
        for l in tags.values():
            assert l == sorted(l)

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
