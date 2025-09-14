import json
import re
import subprocess

from jinja2 import Environment, StrictUndefined
from jinja2.ext import Extension


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
            ).stdout
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


class ExpandFileTypesExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_file_types"] = (
            ExpandFileTypesExtension.expand_file_types
        )

    @staticmethod
    def expand_file_types(
        user_file_types: list[str] | None,
        file_type_tools: dict[str, list[str] | None],
        tool_config_file_types: dict[str, list[str] | None],
        tool_installed_by: dict[str, str | None],
        always_existing_file_types: list[str] | None,
        always_used_tools: list[str] | None,
    ) -> list[str]:
        always_used_tools = always_used_tools or []

        current = set(user_file_types or [])
        current.update(always_existing_file_types or [])
        for tool in always_used_tools:
            current.update(tool_config_file_types[tool] or [])

        tools = set(always_used_tools)

        while True:
            next = set(current)

            for file_type in next:
                tools.update(file_type_tools[file_type] or [])

            installers = set()
            for tool in tools:
                installed_by = tool_installed_by[tool]
                if installed_by:
                    installers.add(installed_by)
            tools.update(installers)

            for tool in tools:
                next.update(tool_config_file_types[tool] or [])

            if next == current:
                return sorted(next)
            current = next


class ExpandToolsExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_tools"] = ExpandToolsExtension.expand_tools

    @staticmethod
    def expand_tools(
        file_types: list[str],
        file_type_tools: dict[str, list[str] | None],
        tool_installed_by: dict[str, str | None],
        always_used_tools: list[str] | None,
    ) -> list[str]:
        current = set(always_used_tools or [])
        for file_type in file_types:
            current.update(file_type_tools[file_type] or [])

        while True:
            next = set(current)

            installers = set()
            for tool in next:
                installed_by = tool_installed_by[tool]
                if installed_by:
                    installers.add(installed_by)
            next.update(installers)

            if next == current:
                return sorted(next)
            current = next
