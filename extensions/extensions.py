import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from frozendict import frozendict
from identify import identify
from jinja2 import Environment, StrictUndefined
from jinja2.ext import Extension

# ruff: noqa: INP001


class StrictUndefinedExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.undefined = StrictUndefined


class GitExtension(Extension):
    def __init__(self, environment: Environment) -> None:
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
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["get_python_version"] = UvExtension.get_python_version

    @staticmethod
    def _default_python_version() -> str:
        j = json.loads(
            subprocess.run(
                ["uv", "python", "list", "--output-format=json", "cpython"],
                capture_output=True,
                check=True,
                encoding="utf-8",
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


class NvmExtension(Extension):
    def __init__(self, environment: Environment) -> None:
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


@dataclass(frozen=True, kw_only=True)
class FileType:
    tools: frozenset[str]
    tags: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class Tool:
    config_file_types: frozenset[str]
    installed_by: str | None


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
                        "shell",  # .template_scripts/{uv_install_deps,uv_update_deps}
                        "python",  # .template_scripts/uv_outdated_deps.py
                    },
                ),
                installed_by=None,
            ),
            "copier": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .copier-answers.yml
                    },
                ),
                installed_by="uv",
            ),
            "pre-commit": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .pre-commit-config.yaml
                    },
                ),
                installed_by="uv",
            ),
            "npm": Tool(
                config_file_types=frozenset(
                    {
                        # also .nvmrc, .npmrc
                        "json",  # package.json, package-lock.json
                        "shell",  # .template_scripts/{npm_install_deps,npm_update_deps}
                    },
                ),
                installed_by=None,
            ),
            "prettier": Tool(
                config_file_types=frozenset(
                    {
                        # also .prettierignore
                        "json",  # package.json
                    },
                ),
                installed_by="npm",
            ),
            "shellcheck": Tool(
                config_file_types=frozenset(),  # .shellcheckrc
                installed_by="uv",
            ),
            "shfmt": Tool(
                config_file_types=frozenset(),  # .editorconfig
                installed_by=None,
            ),
            "bats": Tool(
                config_file_types=frozenset(
                    {
                        "shell",  # .template_scripts/bats
                    },
                ),
                installed_by="npm",
            ),
            "ruff": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
            ),
            "mypy": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
            ),
            "pytest": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
            ),
            "eslint": Tool(
                config_file_types=frozenset(
                    {
                        "javascript",  # eslint.config.mjs
                    },
                ),
                installed_by="npm",
            ),
            "htmlvalidate": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # .htmlvalidate.json
                    },
                ),
                installed_by="npm",
            ),
            "stylelint": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # package.json
                    },
                ),
                installed_by="npm",
            ),
            "markdownlint": Tool(
                config_file_types=frozenset(
                    {
                        "json",  # .markdownlint.json
                    },
                ),
                installed_by="npm",
            ),
            "yamllint": Tool(
                config_file_types=frozenset(
                    {
                        "yaml",  # .yamllint.yml
                    },
                ),
                installed_by="uv",
            ),
            "tombi": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
            ),
            "typos": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # pyproject.toml
                    },
                ),
                installed_by="uv",
            ),
            "gitleaks": Tool(
                config_file_types=frozenset(
                    {
                        "toml",  # .gitleaks.toml
                    },
                ),
                installed_by=None,
            ),
            "gitlint": Tool(
                config_file_types=frozenset(),  # .gitlint
                installed_by="uv",
            ),
        },
    )

    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_config"] = ConfigExtension.expand_config
        environment.filters["detect_config"] = ConfigExtension.detect_config
        environment.filters["file_type_tags"] = ConfigExtension.file_type_tags

    @staticmethod
    def expand_config(
        new: Mapping[str, Sequence[str] | None],
        existing: Mapping[str, Sequence[str] | None],
    ) -> dict[str, list[str]]:
        current_file_types = set(existing.get("file_types", []) or []) | set(
            new.get("file_types", []) or [],
        )
        current_tools = set(existing.get("tools", []) or []) | set(
            new.get("tools", []) or [],
        )

        while True:
            new_file_types = set(current_file_types)
            new_tools = set(current_tools)

            for file_type in new_file_types:
                new_tools.update(ConfigExtension._FILE_TYPES[file_type].tools)

            installers = set()
            for tool in new_tools:
                installed_by = ConfigExtension._TOOLS[tool].installed_by
                if installed_by:
                    installers.add(installed_by)
            new_tools.update(installers)

            for tool in new_tools:
                new_file_types.update(ConfigExtension._TOOLS[tool].config_file_types)

            if new_file_types == current_file_types and new_tools == current_tools:
                return {
                    "file_types": sorted(new_file_types),
                    "tools": sorted(new_tools),
                }

            current_file_types = new_file_types
            current_tools = new_tools

    @staticmethod
    def detect_config(_: str) -> dict[str, list[str]]:
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

        file_types = set()
        tools = set()

        for file in files:
            try:
                tags = identify.tags_from_path(file)
            except ValueError:
                continue
            for file_type, data in ConfigExtension._FILE_TYPES.items():
                if data.tags & tags:
                    file_types.add(file_type)

            if "bats" in tags:
                tools.add("bats")

            if PurePath(file).name == "conftest.py":
                tools.add("pytest")

        return {
            "file_types": sorted(file_types),
            "tools": sorted(tools),
        }

    @staticmethod
    def file_type_tags(_: str) -> dict[str, list[str]]:
        return {
            file_type: sorted(data.tags)
            for file_type, data in ConfigExtension._FILE_TYPES.items()
        }
