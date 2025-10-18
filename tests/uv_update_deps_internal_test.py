from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from frozendict import frozendict

from template_files.uv_update_deps_internal import (
    UV,
    Extra,
    Group,
    Main,
    Package,
    Packages,
    main,
    top_level_packages,
)

if TYPE_CHECKING:
    from pyfakefs.fake_filesystem import FakeFilesystem
    from pytest_mock import MockerFixture
    from pytest_subprocess.fake_process import FakeProcess

# ruff: noqa: S101


class TestPackage:
    def test_package(self) -> None:
        assert str(Package(name="foo", extras=frozenset())) == "foo"
        assert (
            str(Package(name="foo", extras=frozenset({"bar", "baz"}))) == "foo[bar,baz]"
        )


class TestLocation:
    def test_main(self) -> None:
        m = Main()
        assert m.arg() == ""
        assert str(m) == ""
        assert m != ""

    def test_group(self) -> None:
        g = Group("foo")
        assert g.arg() == "--group=foo"
        assert str(g) == "--group=foo"
        assert g != ""

    def test_extra(self) -> None:
        e = Extra("foo")
        assert e.arg() == "--optional=foo"
        assert str(e) == "--optional=foo"
        assert e != ""


class TestUV:
    def test_list_outdated(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"

        fp.register(
            ["uv", "pip", "list", "--format=json", "--outdated"],
            "[]",
        )
        assert UV.list_outdated() == frozenset()

        fp.register(
            ["uv", "pip", "list", "--format=json", "--outdated"],
            """[
    {"name": "foo", "version": "1"},
    {"name": "bar", "version": "2"}
]""",
        )
        assert UV.list_outdated() == frozenset({"foo", "bar"})

    def test_list_versions(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"

        fp.register(
            ["uv", "pip", "list", "--format=json"],
            "[]",
        )
        assert UV.list_versions() == frozendict()

        fp.register(
            ["uv", "pip", "list", "--format=json"],
            """[
    {"name": "foo", "version": "1"},
    {"name": "bar", "version": "2"}
]""",
        )
        assert UV.list_versions() == frozendict({"foo": "1", "bar": "2"})

    def test_remove(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "remove", "--frozen", "--group=dev", "foo"],
        )
        UV.remove(
            Group("dev"),
            Package(name="foo", extras=frozenset({"bar", "baz"})),
        )

    def test_add_raw(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "add", "--frozen", "--group=dev", "--raw", "foo[bar,baz]"],
        )
        UV.add_raw(
            Group("dev"),
            Package(name="foo", extras=frozenset({"bar", "baz"})),
        )

    def test_add_version(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "add", "--frozen", "--group=dev", "foo[bar,baz]==0.1.0"],
        )
        UV.add_version(
            Group("dev"),
            Package(name="foo", extras=frozenset({"bar", "baz"})),
            "0.1.0",
        )

    def test_sync(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "sync", "--all-extras", "--all-groups", "--upgrade"],
        )
        UV.sync()


class TestPackages:
    def test_packages(self) -> None:
        p1 = Package(
            name="foo",
            extras=frozenset({"bar", "baz"}),
        )
        p2 = Package(
            name="quux",
            extras=frozenset({"blah", "yay"}),
        )
        p3 = Package(
            name="a",
            extras=frozenset({"b", "c"}),
        )

        ps = Packages(
            main=frozenset({p1}),
            groups=frozendict(
                {
                    "A": frozenset({p2}),
                },
            ),
            extras=frozendict(
                {
                    "B": frozenset({p3}),
                    "C": frozenset({p1}),
                },
            ),
        )
        assert ps.all_names() == frozenset({"foo", "quux", "a"})

        assert list(ps) == [
            (Main(), p1),
            (Group("A"), p2),
            (Extra("B"), p3),
            (Extra("C"), p1),
        ]

        assert ps.filter({"foo"}) == Packages(
            main=frozenset({p1}),
            groups=frozendict(),
            extras=frozendict({"C": frozenset({p1})}),
        )


class TestTopLevelPackages:
    def test_top_level_packages(self, fs: FakeFilesystem) -> None:
        fs.create_file(
            "pyproject.toml",
            contents="""
[project]
dependencies = [
    "foo==0.1.0",
    "bar[A,B]==0.2.0",
]

[project.optional-dependencies]
extra = [
    "quux[D,E]==0.3.0",
    "bar==0.2.0",
]

[dependency-groups]
dev = [
    "bar==0.2.0",
    "baz[C]==0.1.0",
]
""",
        )

        assert top_level_packages() == Packages(
            main=frozenset(
                {
                    Package(name="foo", extras=frozenset()),
                    Package(name="bar", extras=frozenset({"A", "B"})),
                },
            ),
            groups=frozendict(
                {
                    "dev": frozenset(
                        {
                            Package(name="bar", extras=frozenset()),
                            Package(name="baz", extras=frozenset({"C"})),
                        },
                    ),
                },
            ),
            extras=frozendict(
                {
                    "extra": frozenset(
                        {
                            Package(name="bar", extras=frozenset()),
                            Package(name="quux", extras=frozenset({"D", "E"})),
                        },
                    ),
                },
            ),
        )

    def test_top_level_packages_empty(self, fs: FakeFilesystem) -> None:
        fs.create_file(
            "pyproject.toml",
            contents="""
[project]
dependencies = []
""",
        )

        assert top_level_packages() == Packages(
            main=frozenset(),
            groups=frozendict(),
            extras=frozendict(),
        )


class TestMain:
    def test_main(
        self,
        fs: FakeFilesystem,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fs.create_file(
            "pyproject.toml",
            contents="""
[project]
dependencies = [
    "foo==0.1.0",
    "bar[A,B]==0.2.0",
]

[project.optional-dependencies]
extra = [
    "quux[D,E]==0.3.0",
    "bar==0.2.0",
]

[dependency-groups]
dev = [
    "bar==0.2.0",
    "baz[C]==0.1.0",
]
""",
        )

        fp.register(
            ["uv", "pip", "list", "--format=json", "--outdated"],
            '[{"name": "bar", "version": "0.2.0"}]',
        )

        fp.register(
            ["uv", "remove", "--frozen", "bar"],
        )
        fp.register(
            ["uv", "remove", "--frozen", "--group=dev", "bar"],
        )
        fp.register(
            ["uv", "remove", "--frozen", "--optional=extra", "bar"],
        )

        fp.register(
            ["uv", "add", "--frozen", "--raw", "bar[A,B]"],
        )
        fp.register(
            ["uv", "add", "--frozen", "--group=dev", "--raw", "bar"],
        )
        fp.register(
            ["uv", "add", "--frozen", "--optional=extra", "--raw", "bar"],
        )

        fp.register(
            ["uv", "sync", "--all-extras", "--all-groups", "--upgrade"],
        )

        fp.register(
            ["uv", "pip", "list", "--format=json"],
            """[
    {"name": "foo", "version": "0.1.0"},
    {"name": "bar", "version": "0.4.0"},
    {"name": "baz", "version": "0.1.0"},
    {"name": "quux", "version": "0.3.0"}
]""",
        )

        fp.register(
            ["uv", "add", "--frozen", "bar[A,B]==0.4.0"],
        )
        fp.register(
            ["uv", "add", "--frozen", "--group=dev", "bar==0.4.0"],
        )
        fp.register(
            ["uv", "add", "--frozen", "--optional=extra", "bar==0.4.0"],
        )

        fp.register(
            ["uv", "sync", "--all-extras", "--all-groups", "--upgrade"],
        )

        main()

    def test_main_fails(
        self,
        fs: FakeFilesystem,  # noqa: ARG002
        fp: FakeProcess,  # noqa: ARG002
    ) -> None:
        with pytest.raises(SystemExit):
            main()
