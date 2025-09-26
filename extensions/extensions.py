import json
import re
import subprocess
from collections.abc import Mapping, Sequence

from frozendict import frozendict
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


class ConfigExtension(Extension):
    _FILE_TYPE_TOOLS: frozendict[str, frozenset[str]] = frozendict(
        {
            "shell": frozenset(
                {
                    "shellcheck",
                    "shfmt",
                },
            ),
            "python": frozenset(
                {
                    "ruff",
                    "mypy",
                },
            ),
            "javascript": frozenset(
                {
                    "prettier",
                    "eslint",
                },
            ),
            "html": frozenset(
                {
                    "prettier",
                    "htmlvalidate",
                },
            ),
            "css": frozenset(
                {
                    "prettier",
                    "stylelint",
                },
            ),
            "markdown": frozenset(
                {
                    "prettier",
                    "markdownlint",
                },
            ),
            "json": frozenset(
                {
                    "prettier",
                },
            ),
            "yaml": frozenset(
                {
                    "prettier",
                    "yamllint",
                },
            ),
            "toml": frozenset(
                {
                    "tombi",
                },
            ),
        },
    )

    _TOOL_CONFIG_FILE_TYPES: frozendict[str, frozenset[str]] = frozendict(
        {
            "uv": frozenset(
                {
                    # also .python-version, uv.lock
                    "toml",  # pyproject.toml
                },
            ),
            "copier": frozenset(
                {
                    "yaml",  # .copier-answers.yml
                },
            ),
            "pre-commit": frozenset(
                {
                    "yaml",  # .pre-commit-config.yaml
                },
            ),
            "npm": frozenset(
                {
                    # also .nvmrc, .npmrc
                    "json",  # package.json, package-lock.json
                },
            ),
            "prettier": frozenset(
                {
                    # also .prettierignore
                    "json",  # package.json
                },
            ),
            "shellcheck": frozenset(),  # .shellcheckrc
            "shfmt": frozenset(),  # .editorconfig
            "ruff": frozenset(
                {
                    "toml",  # pyproject.toml
                },
            ),
            "mypy": frozenset(
                {
                    "toml",  # pyproject.toml
                },
            ),
            "eslint": frozenset(
                {
                    "javascript",  # eslint.config.mjs
                },
            ),
            "htmlvalidate": frozenset(
                {
                    "json",  # .htmlvalidate.json
                },
            ),
            "stylelint": frozenset(
                {
                    "json",  # package.json
                },
            ),
            "markdownlint": frozenset(
                {
                    "json",  # .markdownlint.json
                },
            ),
            "yamllint": frozenset(
                {
                    "yaml",  # .yamllint.yml
                },
            ),
            "tombi": frozenset(
                {
                    "toml",  # pyproject.toml
                },
            ),
            "typos": frozenset(
                {
                    "toml",  # pyproject.toml
                },
            ),
            "gitleaks": frozenset(
                {
                    "toml",  # .gitleaks.toml
                },
            ),
            "gitlint": frozenset(),  # .gitlint
        },
    )

    _TOOL_INSTALLED_BY: frozendict[str, str | None] = frozendict(
        {
            "uv": None,
            "copier": "uv",
            "pre-commit": "uv",
            "npm": None,
            "prettier": "npm",
            "shellcheck": "uv",
            "shfmt": None,
            "ruff": "uv",
            "mypy": "uv",
            "eslint": "npm",
            "htmlvalidate": "npm",
            "stylelint": "npm",
            "markdownlint": "npm",
            "yamllint": "uv",
            "tombi": "uv",
            "typos": "uv",
            "gitleaks": None,
            "gitlint": "uv",
        },
    )

    _ALWAYS_EXISTING_FILE_TYPES = frozenset(
        {
            "markdown",  # README.md
            "json",  # .vscode/settings.json
        },
    )

    _ALWAYS_USED_TOOLS = frozenset(
        {
            "uv",
            "copier",
            "pre-commit",
            "typos",
            "gitleaks",
            "gitlint",
        },
    )

    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_config"] = ConfigExtension.expand_config

    @staticmethod
    def expand_config(
        file_types: list[str] | None,
    ) -> dict[str, list[str]]:
        return ConfigExtension._expand_config(
            file_types or [],
            {
                "file_types": sorted(ConfigExtension._ALWAYS_EXISTING_FILE_TYPES),
                "tools": sorted(ConfigExtension._ALWAYS_USED_TOOLS),
            },
        )

    @staticmethod
    def _expand_config(
        file_types: list[str],
        existing: Mapping[str, Sequence[str]],
    ) -> dict[str, list[str]]:
        current_file_types = set(existing["file_types"]) | set(file_types)
        current_tools = set(existing["tools"])

        while True:
            new_file_types = set(current_file_types)
            new_tools = set(current_tools)

            for file_type in new_file_types:
                new_tools.update(ConfigExtension._FILE_TYPE_TOOLS[file_type])

            installers = set()
            for tool in new_tools:
                installed_by = ConfigExtension._TOOL_INSTALLED_BY[tool]
                if installed_by:
                    installers.add(installed_by)
            new_tools.update(installers)

            for tool in new_tools:
                new_file_types.update(ConfigExtension._TOOL_CONFIG_FILE_TYPES[tool])

            if new_file_types == current_file_types and new_tools == current_tools:
                return {
                    "file_types": sorted(new_file_types),
                    "tools": sorted(new_tools),
                }

            current_file_types = new_file_types
            current_tools = new_tools
