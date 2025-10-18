from __future__ import annotations

import json
import os.path
import re
import subprocess
import tempfile
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, override

from frozendict import frozendict
from identify import identify
from jinja2 import Environment, StrictUndefined
from jinja2.ext import Extension


class StrictUndefinedExtension(Extension):  # pragma: no cover
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.undefined = StrictUndefined


class GitExtension(Extension):
    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["get_git_user_name"] = GitExtension.get_git_user_name

    @staticmethod
    def get_git_user_name(default: str) -> str:
        result = subprocess.run(
            ["git", "config", "user.name"],
            check=False,
            capture_output=True,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return default


class PythonExtension(Extension):
    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["enumerate_python_versions"] = (
            PythonExtension.enumerate_python_versions
        )
        environment.filters["filter_python_versions_leq"] = (
            PythonExtension.filter_python_versions_leq
        )
        environment.filters["increment_python_version"] = (
            PythonExtension.increment_python_version
        )

    @staticmethod
    def parse_version(v: str) -> tuple[int, int]:
        match = re.fullmatch(r"([1-9][0-9]*)\.([0-9]+)(\.[0-9]+)?", v)
        if match is None:
            raise ValueError(f"Invalid python version '{v}'")
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def parse_versions(vs: Sequence[str]) -> list[tuple[int, int]]:
        return sorted({PythonExtension.parse_version(v) for v in vs})

    @staticmethod
    def join_versions(vs: Sequence[tuple[int, int]]) -> list[str]:
        return [f"{v[0]}.{v[1]}" for v in sorted(set(vs))]

    @staticmethod
    def enumerate_python_versions(first: str, last: str) -> list[str]:
        v1 = PythonExtension.parse_version(first)
        v2 = PythonExtension.parse_version(last)

        if v1[0] != v2[0]:
            raise ValueError(
                f"Python versions must have same major version; got {first} and {last}",
            )
        major = v1[0]

        if v1 > v2:
            raise ValueError(
                f"Python versions passed in the wrong order; got {first} and {last}",
            )

        return [f"{major}.{minor}" for minor in range(v1[1], v2[1] + 1)]

    @staticmethod
    def filter_python_versions_leq(
        versions: Sequence[str],
        max_version: str,
    ) -> list[str]:
        highest = PythonExtension.parse_version(max_version)
        return PythonExtension.join_versions(
            [v for v in PythonExtension.parse_versions(versions) if v <= highest],
        )

    @staticmethod
    def increment_python_version(version: str) -> str:
        major, minor = PythonExtension.parse_version(version)
        return f"{major}.{minor + 1}"


class Toml:
    @staticmethod
    def load(filename: str) -> frozendict[str, Any]:
        try:
            with open(filename, "rb") as f:
                return frozendict(tomllib.load(f))
        except OSError:
            return frozendict()


class UV:
    @staticmethod
    def _uv(
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        # Make sure we're calling the global uv, in case a dependency installed
        # a different version of uv inside the virtualenv.
        uv = os.getenv("UV", "uv")
        return subprocess.run(
            [uv, *args],
            capture_output=True,
            check=check,
            encoding="utf-8",
        )

    @staticmethod
    def uv_version() -> str:
        raw = UV._uv(["--version"]).stdout

        match = re.search(r"[0-9]+\.[0-9]+\.[0-9]+", raw)
        if match is None:
            raise ValueError("Can't find uv version")

        return match.group(0)

    @staticmethod
    def uv_build_spec() -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            UV._uv(
                [
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
                    tmpdir,
                ],
            )

            data = Toml.load(os.path.join(tmpdir, "pyproject.toml"))

        requires: list[str] = data.get("build-system", {}).get("requires", [])
        if not requires:
            raise ValueError("Can't find uv build spec")

        return requires[0]

    @staticmethod
    def _default_python_version(version_hint: str) -> str:
        j = json.loads(
            UV._uv(
                ["python", "list", "--output-format=json", f"cpython@{version_hint}"],
            ).stdout,
        )

        versions = set()
        for version in [v["version"] for v in j]:
            if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
                continue
            versions.add(tuple(int(part) for part in version.split(".")))

        if not versions:
            raise ValueError("Can't find a default python version")

        return ".".join(str(v) for v in sorted(versions, reverse=True)[0])

    @staticmethod
    def _existing_python_version() -> str:
        try:
            with open(".python-version") as f:
                return f.read().strip()
        except OSError:
            return ""

    @staticmethod
    def python_version(version_hint: str) -> str:
        existing = UV._existing_python_version()
        if existing and PythonExtension.parse_version(
            existing,
        ) == PythonExtension.parse_version(version_hint):
            return existing
        return UV._default_python_version(version_hint)

    @staticmethod
    def installed_python_packages() -> frozenset[str]:
        result = UV._uv(
            ["pip", "list", "--format=json"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return frozenset(p["name"] for p in json.loads(result.stdout))
        return frozenset()


class Nvm:
    @staticmethod
    def _default_node_version() -> str:
        return subprocess.run(
            ["bash", "-c", 'source "${NVM_DIR}/nvm.sh" && nvm version stable'],
            capture_output=True,
            check=True,
            encoding="utf-8",
        ).stdout.strip()

    @staticmethod
    def _existing_node_version() -> str:
        try:
            with open(".nvmrc") as f:
                return f.read().strip()
        except OSError:
            return ""

    @staticmethod
    def node_version() -> str:
        return Nvm._existing_node_version() or Nvm._default_node_version()

    @staticmethod
    def installed_node_packages() -> frozenset[str]:
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "${NVM_DIR}/nvm.sh" && nvm exec --silent npm list --json',
            ],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            return frozenset(
                name for name in json.loads(result.stdout).get("dependencies", {})
            )
        return frozenset()


@dataclass(frozen=True, kw_only=True)
class FileType:
    tools: frozenset[str]
    tags: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class Tool:
    config_file_types: frozenset[str]
    installed_by: str | None
    requires: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    file_regexes: frozenset[str] = frozenset()
    python_packages: frozendict[str, str] = frozendict()
    node_packages: frozendict[str, str] = frozendict()


class Metadata(ABC):
    @abstractmethod
    def get(self) -> Any | None:  # noqa: ANN401  # pragma: no cover
        raise NotImplementedError


class TomlValue(Metadata):
    def __init__(
        self,
        *,
        filename: str,
        key: str,
        default: Any | None = None,  # noqa: ANN401
    ) -> None:
        super().__init__()
        self._filename = filename
        self._key = tuple(part for part in key.split(".") if part)
        self._default = default

    @abstractmethod
    def _typecheck(self, value: Any) -> bool:  # noqa: ANN401  # pragma: no cover
        raise NotImplementedError

    @override
    def get(self) -> Any | None:
        data: Mapping[str, Any] = Toml.load(self._filename)
        for i, k in enumerate(self._key):
            if k not in data:
                return self._default
            v = data[k]
            if i == len(self._key) - 1:
                if not self._typecheck(v):
                    raise TypeError(
                        f"Value {'.'.join(self._key)} in {self._filename} has "
                        f"unexpected type {type(v)}",
                    )
                return v
            if not isinstance(v, dict):
                raise TypeError(
                    f"Indexed into {self._filename} value {'.'.join(self._key)} that "
                    f"isn't a dict (got {type(v)})",
                )
            data = v
        return None


class BoolTomlValue(TomlValue):
    @override
    def _typecheck(self, value: Any) -> bool:
        return isinstance(value, bool)


class StrTomlValue(TomlValue):
    @override
    def _typecheck(self, value: Any) -> bool:
        return isinstance(value, str)


class Call(Metadata):
    def __init__(self, fn: Callable[[], Any | None]) -> None:
        super().__init__()
        self._fn = fn

    @override
    def get(self) -> Any | None:
        return self._fn()


RawConfig = Mapping[str, Sequence[str] | Mapping[str, Any] | None]


@dataclass(frozen=True, kw_only=True)
class Config:
    file_types: frozenset[str]
    tools: frozenset[str]
    metadata: frozendict[str, Any]

    @staticmethod
    def from_yaml(data: RawConfig) -> Config:
        def _set(key: str) -> frozenset[str]:
            v = data.get(key, []) or []
            if not isinstance(v, Sequence):
                raise TypeError(
                    f"Config key '{key}' is {type(data[key])} (wanted "
                    f"Sequence[str] | None)",
                )
            return frozenset(v)

        def _dict(key: str) -> frozendict[str, Any]:
            v = data.get(key, {}) or {}
            if not isinstance(v, Mapping):
                raise TypeError(
                    f"Config key '{key}' is {type(data[key])} (wanted "
                    f"Mapping[str, Any] | None)",
                )
            return frozendict(v)

        return Config(
            file_types=_set("file_types"),
            tools=_set("tools"),
            metadata=_dict("metadata"),
        )

    def to_yaml(self) -> dict[str, list[str] | dict[str, Any]]:
        return {
            "file_types": sorted(self.file_types),
            "tools": sorted(self.tools),
            "metadata": dict(self.metadata),
        }


class ConfigExtension(Extension):
    _MIN_PYTHON_VERSION = "3.12"
    _MAX_PYTHON_VERSION = "3.14"

    _FILE_TYPES: frozendict[str, FileType] = frozendict(
        {
            "shell": FileType(
                tools=frozenset(
                    {
                        "shellcheck",
                        "shfmt",
                    },
                ),
                tags=frozenset(
                    {
                        "shell",
                    },
                ),
            ),
            "python": FileType(
                tools=frozenset(
                    {
                        "ruff",
                        "mypy",
                        "ast-grep",
                    },
                ),
                tags=frozenset(
                    {
                        "python",
                        "pyi",
                    },
                ),
            ),
            "javascript": FileType(
                tools=frozenset(
                    {
                        "prettier",
                        "eslint",
                    },
                ),
                tags=frozenset(
                    {
                        "javascript",
                    },
                ),
            ),
            "html": FileType(
                tools=frozenset(
                    {
                        "prettier",
                        "htmlvalidate",
                    },
                ),
                tags=frozenset(
                    {
                        "html",
                    },
                ),
            ),
            "css": FileType(
                tools=frozenset(
                    {
                        "prettier",
                        "stylelint",
                    },
                ),
                tags=frozenset(
                    {
                        "css",
                    },
                ),
            ),
            "markdown": FileType(
                tools=frozenset(
                    {
                        "prettier",
                        "markdownlint",
                    },
                ),
                tags=frozenset(
                    {
                        "markdown",
                    },
                ),
            ),
            "json": FileType(
                tools=frozenset(
                    {
                        "prettier",
                    },
                ),
                tags=frozenset(
                    {
                        "json",
                    },
                ),
            ),
            "yaml": FileType(
                tools=frozenset(
                    {
                        "prettier",
                        "yamllint",
                    },
                ),
                tags=frozenset(
                    {
                        "yaml",
                    },
                ),
            ),
            "toml": FileType(
                tools=frozenset(
                    {
                        "tombi",
                    },
                ),
                tags=frozenset(
                    {
                        "toml",
                    },
                ),
            ),
        },
    )

    _TOOLS: frozendict[str, Tool] = frozendict(
        {
            "uv": Tool(
                config_file_types=frozenset(
                    {
                        # also .python-version, uv.lock
                        "toml",  # pyproject.toml
                        "shell",  # .template_files/{uv_install_deps,uv_update_deps}
                        "python",  # .template_files/uv_outdated_deps.py
                    },
                ),
                installed_by=None,
                requires=frozenset(
                    {
                        "python-license-checker",
                    },
                ),
                python_packages=frozendict(
                    {
                        "frozendict": "2.4.6",
                        "packaging": "25.0",
                    },
                ),
            ),
            "copier": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .copier-answers.yml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "cookiecutter": "2.6.0",
                        "copier": "9.10.2",
                        "copier-template-extensions": "0.3.3",
                        "identify": "2.6.15",
                    },
                ),
            ),
            "pre-commit": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .pre-commit-config.yaml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "pre-commit": "4.3.0",
                    },
                ),
            ),
            "python-license-checker": Tool(
                config_file_types=frozenset(),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "licensecheck": "2025.1.0",
                    },
                ),
            ),
            "npm": Tool(
                config_file_types=frozenset(
                    {
                        # also .nvmrc, .npmrc
                        "json",  # package.json, package-lock.json
                        "shell",  # .template_files/{npm_install_deps,npm_update_deps}
                    },
                ),
                installed_by=None,
                requires=frozenset(
                    {
                        "node-license-checker",
                    },
                ),
            ),
            "node-license-checker": Tool(
                config_file_types=frozenset(),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "license-checker-rseidelsohn": "4.4.2",
                    },
                ),
            ),
            "prettier": Tool(
                config_file_types=frozenset(
                    {
                        # also .prettierignore
                        "json",  # package.json
                    },
                ),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "prettier": "3.6.2",
                    },
                ),
            ),
            "shellcheck": Tool(
                config_file_types=frozenset(),  # .shellcheckrc
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "shellcheck-py": "0.11.0.1",
                    },
                ),
            ),
            "shfmt": Tool(
                config_file_types=frozenset(),  # .editorconfig
                installed_by=None,
            ),
            "bats": Tool(
                config_file_types=frozenset(
                    {
                        "shell",  # .template_files/bats
                    },
                ),
                installed_by="npm",
                tags=frozenset(
                    {
                        "bats",
                    },
                ),
                node_packages=frozendict(
                    {
                        "bats": "1.12.0",
                        "bats-assert": "2.2.0",
                        "bats-support": "0.3.0",
                    },
                ),
            ),
            "ruff": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "ruff": "0.14.0",
                    },
                ),
            ),
            "mypy": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "mypy": "1.18.2",
                    },
                ),
            ),
            "pytest": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                file_regexes=frozenset(
                    {
                        r"(.*/)?conftest\.py",
                    },
                ),
                python_packages=frozendict(
                    {
                        "pytest": "8.4.2",
                        "pytest-cov": "7.0.0",
                        "pytest-custom_exit_code": "0.3.0",
                    },
                ),
            ),
            "eslint": Tool(
                config_file_types=frozenset(
                    {
                        "javascript",  # eslint.config.mjs
                    },
                ),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "@eslint/compat": "1.4.0",
                        "@eslint/js": "9.37.0",
                        "eslint": "9.37.0",
                        "eslint-config-prettier": "10.1.8",
                        "globals": "16.4.0",
                    },
                ),
            ),
            "htmlvalidate": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # .htmlvalidate.json
                    },
                ),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "html-validate": "10.1.1",
                    },
                ),
            ),
            "stylelint": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # package.json
                    },
                ),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "stylelint": "16.25.0",
                        "stylelint-config-standard": "39.0.1",
                    },
                ),
            ),
            "markdownlint": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # .markdownlint.json
                    },
                ),
                installed_by="npm",
                node_packages=frozendict(
                    {
                        "markdownlint-cli2": "0.18.1",
                    },
                ),
            ),
            "yamllint": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .yamllint.yml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "yamllint": "1.37.1",
                    },
                ),
            ),
            "tombi": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "tombi": "0.6.25",
                    },
                ),
            ),
            "ast-grep": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # sgconfig.yml, .ast_grep/*.yml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "ast-grep-cli": "0.39.6",
                    },
                ),
                file_regexes=frozenset(
                    {
                        r"\.ast_grep/.*",
                    },
                ),
            ),
            "typos": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "typos": "1.38.1",
                    },
                ),
            ),
            "bump-my-version": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "bump-my-version": "1.2.4",
                    },
                ),
            ),
            "gitleaks": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # .gitleaks.toml
                    },
                ),
                installed_by=None,
            ),
            "github-actions": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .github/workflows/*.yml
                    },
                ),
                installed_by=None,
                requires=frozenset(
                    {
                        "actionlint",
                        "zizmor",
                        "gha-update",
                    },
                ),
                file_regexes=frozenset(
                    {
                        r"\.github/workflows/.*.yml",
                    },
                ),
            ),
            "actionlint": Tool(
                config_file_types=frozenset(),
                installed_by=None,
            ),
            "zizmor": Tool(
                config_file_types=frozenset(),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "zizmor": "1.14.2",
                    },
                ),
            ),
            "gha-update": Tool(
                config_file_types=frozenset(),
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "gha-update": "0.2.0",
                    },
                ),
            ),
            "gitlint": Tool(
                config_file_types=frozenset(),  # .gitlint
                installed_by="uv",
                python_packages=frozendict(
                    {
                        "gitlint": "0.19.1",
                    },
                ),
            ),
        },
    )

    _METADATA = frozendict[str, Metadata](
        {
            "uv_version": Call(UV.uv_version),
            "uv_build_spec": Call(UV.uv_build_spec),
            "template_min_allowed_python_version": Call(
                lambda: ConfigExtension._MIN_PYTHON_VERSION,
            ),
            "template_max_allowed_python_version": Call(
                lambda: ConfigExtension._MAX_PYTHON_VERSION,
            ),
            "template_allowed_python_versions": Call(
                lambda: PythonExtension.enumerate_python_versions(
                    ConfigExtension._MIN_PYTHON_VERSION,
                    ConfigExtension._MAX_PYTHON_VERSION,
                ),
            ),
            "node_version": Call(Nvm.node_version),
            "file_type_tags": Call(lambda: ConfigExtension.file_type_tags()),
            "project_version": StrTomlValue(
                filename="pyproject.toml",
                key="project.version",
                default="0.0.0",
            ),
            "is_python_package": BoolTomlValue(
                filename="pyproject.toml",
                key="tool.uv.package",
            ),
        },
    )

    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["expand_config"] = ConfigExtension.expand_config
        environment.filters["detect_config"] = ConfigExtension.detect_config
        environment.filters["python_version_exact"] = (
            ConfigExtension.python_version_exact
        )
        environment.filters["python_packages"] = ConfigExtension.python_packages
        environment.filters["node_packages"] = ConfigExtension.node_packages

    @staticmethod
    def expand_config(
        new_raw: RawConfig,
        existing_raw: RawConfig,
    ) -> RawConfig:
        new = Config.from_yaml(new_raw)
        existing = Config.from_yaml(existing_raw)
        current_file_types = set(existing.file_types | new.file_types)
        current_tools = set(existing.tools | new.tools)

        while True:
            new_file_types = set(current_file_types)
            new_tools = set(current_tools)

            for file_type in new_file_types:
                new_tools.update(ConfigExtension._FILE_TYPES[file_type].tools)

            tools_to_add = set()
            for tool in new_tools:
                installed_by = ConfigExtension._TOOLS[tool].installed_by
                if installed_by:
                    tools_to_add.add(installed_by)
                tools_to_add.update(ConfigExtension._TOOLS[tool].requires)
            new_tools.update(tools_to_add)

            for tool in new_tools:
                new_file_types.update(ConfigExtension._TOOLS[tool].config_file_types)

            if new_file_types == current_file_types and new_tools == current_tools:
                return Config(
                    file_types=frozenset(new_file_types),
                    tools=frozenset(new_tools),
                    metadata=existing.metadata | new.metadata,
                ).to_yaml()

            current_file_types = new_file_types
            current_tools = new_tools

    @staticmethod
    def file_type_tags() -> dict[str, list[str]]:
        return {
            file_type: sorted(data.tags)
            for file_type, data in ConfigExtension._FILE_TYPES.items()
        }

    @staticmethod
    def detect_config(_: str) -> RawConfig:
        files = sorted(
            subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True,
                check=True,
                encoding="utf-8",
            )
            .stdout.strip()
            .splitlines(),
        )

        python_packages = UV.installed_python_packages()
        node_packages = Nvm.installed_node_packages()

        file_types = set()
        tools = set()

        for file in files:
            try:
                tags = identify.tags_from_path(file)
            except ValueError:
                continue

            for file_type, file_type_data in ConfigExtension._FILE_TYPES.items():
                if file_type_data.tags & tags:
                    file_types.add(file_type)

            for tool, tool_data in ConfigExtension._TOOLS.items():
                if (
                    tool_data.tags & tags
                    or tool_data.python_packages.keys() & python_packages
                    or tool_data.node_packages.keys() & node_packages
                ):
                    tools.add(tool)
                    continue

                for regex in tool_data.file_regexes:
                    if re.fullmatch(regex, file) is not None:
                        tools.add(tool)

        metadata = {}
        for m_name, m_data in ConfigExtension._METADATA.items():
            data = m_data.get()
            if data is not None:
                metadata[m_name] = data

        return Config(
            file_types=frozenset(file_types),
            tools=frozenset(tools),
            metadata=frozendict(metadata),
        ).to_yaml()

    @staticmethod
    def python_version_exact(version_hint: str) -> str:
        return UV.python_version(version_hint)

    @staticmethod
    def _packages(
        config: RawConfig,
        selector: Callable[[Tool], frozendict[str, str]],
    ) -> dict[str, str]:
        tools = Config.from_yaml(config).tools
        out: dict[str, str] = {}
        for tool, data in ConfigExtension._TOOLS.items():
            if tool in tools:
                out.update(selector(data))
        return out

    @staticmethod
    def python_packages(config: RawConfig) -> dict[str, str]:
        return ConfigExtension._packages(config, lambda d: d.python_packages)

    @staticmethod
    def node_packages(config: RawConfig) -> dict[str, str]:
        return ConfigExtension._packages(config, lambda d: d.node_packages)
