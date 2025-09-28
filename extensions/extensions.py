import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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

    @staticmethod
    def get_python_packages() -> frozenset[str]:
        result = subprocess.run(
            ["uv", "pip", "list", "--format=json"],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            return frozenset(p["name"] for p in json.loads(result.stdout))
        return frozenset()


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
                        "frozendict": "2.4.6",
                        "identify": "2.6.14",
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
                        "ruff": "0.13.2",
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
                        "@eslint/js": "9.36.0",
                        "eslint": "9.36.0",
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
                        "html-validate": "10.0.0",
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
                        "stylelint": "16.24.0",
                        "stylelint-config-standard": "39.0.0",
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
                        "tombi": "0.6.17",
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
                        "typos": "1.36.3",
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
                        "zizmor": "1.14.1",
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

    def __init__(self, environment: Environment) -> None:  # pragma: no cover
        super().__init__(environment)
        environment.filters["expand_config"] = ConfigExtension.expand_config
        environment.filters["detect_config"] = ConfigExtension.detect_config
        environment.filters["file_type_tags"] = ConfigExtension.file_type_tags
        environment.filters["python_packages"] = ConfigExtension.python_packages
        environment.filters["node_packages"] = ConfigExtension.node_packages

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

        python_packages = UvExtension.get_python_packages()
        node_packages = NvmExtension.get_node_packages()

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

    @staticmethod
    def python_packages(config: Mapping[str, Sequence[str] | None]) -> dict[str, str]:
        tools = frozenset(config.get("tools", []) or [])
        out: dict[str, str] = {}
        for tool, data in ConfigExtension._TOOLS.items():
            if tool in tools:
                out.update(data.python_packages)
        return out

    @staticmethod
    def node_packages(config: Mapping[str, Sequence[str] | None]) -> dict[str, str]:
        tools = frozenset(config.get("tools", []) or [])
        out: dict[str, str] = {}
        for tool, data in ConfigExtension._TOOLS.items():
            if tool in tools:
                out.update(data.node_packages)
        return out
