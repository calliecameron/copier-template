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


class UvExtension(Extension):
    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["get_uv_version"] = UvExtension.get_uv_version
        environment.filters["get_uv_build_spec"] = UvExtension.get_uv_build_spec
        environment.filters["get_python_version"] = UvExtension.get_python_version

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
    def get_uv_version(_: str) -> str:
        raw = UvExtension._uv(["--version"]).stdout

        match = re.search(r"[0-9]+\.[0-9]+\.[0-9]+", raw)
        if match is None:
            raise ValueError("Can't find uv version")

        return match.group(0)

    @staticmethod
    def get_uv_build_spec(_: str) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            UvExtension._uv(
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

            data = UvExtension.get_pyproject_toml(
                os.path.join(tmpdir, "pyproject.toml"),
            )

        requires: list[str] = data.get("build-system", {}).get("requires", [])
        if not requires:
            raise ValueError("Can't find uv build spec")

        return requires[0]

    @staticmethod
    def _default_python_version() -> str:
        j = json.loads(
            UvExtension._uv(
                ["python", "list", "--output-format=json", "cpython"],
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
    def get_python_version(_: str) -> str:
        return (
            UvExtension._existing_python_version()
            or UvExtension._default_python_version()
        )

    @staticmethod
    def get_python_packages() -> frozenset[str]:
        result = UvExtension._uv(
            ["pip", "list", "--format=json"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return frozenset(p["name"] for p in json.loads(result.stdout))
        return frozenset()

    @staticmethod
    def get_pyproject_toml(filename: str = "pyproject.toml") -> frozendict[str, Any]:
        try:
            with open(filename, "rb") as f:
                return frozendict(tomllib.load(f))
        except OSError:
            return frozendict()


class NvmExtension(Extension):
    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["get_node_version"] = NvmExtension.get_node_version

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
    def get_node_version(_: str) -> str:
        return (
            NvmExtension._existing_node_version()
            or NvmExtension._default_node_version()
        )

    @staticmethod
    def get_node_packages() -> frozenset[str]:
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


class TomlValue(ABC):
    def __init__(self, *, key: str) -> None:
        super().__init__()
        self._key = tuple(part for part in key.split(".") if part)

    @abstractmethod
    def _typecheck(self, value: Any) -> bool:  # noqa: ANN401  # pragma: no cover
        raise NotImplementedError

    def get(self, data: Mapping[str, Any]) -> Any | None:  # noqa: ANN401
        for i, k in enumerate(self._key):
            if k not in data:
                return None
            v = data[k]
            if i == len(self._key) - 1:
                if not self._typecheck(v):
                    raise TypeError(
                        f"Value {'.'.join(self._key)} in pyproject.toml has unexpected "
                        f"type {type(v)}",
                    )
                return v
            if not isinstance(v, dict):
                raise TypeError(
                    f"Indexed into pyproject.toml value {'.'.join(self._key)} that "
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


@dataclass(frozen=True, kw_only=True)
class Metadata:
    pyproject_toml_value: TomlValue


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
            "project_version": Metadata(
                pyproject_toml_value=StrTomlValue(
                    key="project.version",
                ),
            ),
            "is_python_package": Metadata(
                pyproject_toml_value=BoolTomlValue(
                    key="tool.uv.package",
                ),
            ),
        },
    )

    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["expand_config"] = ConfigExtension.expand_config
        environment.filters["detect_config"] = ConfigExtension.detect_config
        environment.filters["file_type_tags"] = ConfigExtension.file_type_tags
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

        python_packages = UvExtension.get_python_packages()
        node_packages = NvmExtension.get_node_packages()
        pyproject_toml = UvExtension.get_pyproject_toml()

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
        for m, m_data in ConfigExtension._METADATA.items():
            data = m_data.pyproject_toml_value.get(pyproject_toml)
            if data is not None:
                metadata[m] = data

        return Config(
            file_types=frozenset(file_types),
            tools=frozenset(tools),
            metadata=frozendict(metadata),
        ).to_yaml()

    @staticmethod
    def file_type_tags(_: str) -> dict[str, list[str]]:
        return {
            file_type: sorted(data.tags)
            for file_type, data in ConfigExtension._FILE_TYPES.items()
        }

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
