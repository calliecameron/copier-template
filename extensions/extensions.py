import subprocess

from jinja2 import Environment, StrictUndefined
from jinja2.ext import Extension


class StrictUndefinedExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.undefined = StrictUndefined


def git_user_name(default: str) -> str:
    result = subprocess.run(
        ["git", "config", "user.name"],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return default


class GitExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["git_user_name"] = git_user_name


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

        for tool in tools:
            installed_by = tool_installed_by[tool]
            if installed_by:
                tools.add(installed_by)

        for tool in tools:
            next.update(tool_config_file_types[tool] or [])

        if next == current:
            return sorted(next)
        current = next


class ExpandFileTypesExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_file_types"] = expand_file_types


def expand_tools(
    file_types: list[str],
    file_type_tools: dict[str, list[str] | None],
    always_used_tools: list[str] | None,
) -> list[str]:
    tools = set(always_used_tools or [])
    for file_type in file_types:
        tools.update(file_type_tools[file_type] or [])
    return sorted(tools)


class ExpandToolsExtension(Extension):
    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        environment.filters["expand_tools"] = expand_tools
