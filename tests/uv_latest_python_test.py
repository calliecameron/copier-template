from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from template_files.uv_latest_python import main

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from pytest_subprocess.fake_process import FakeProcess


# ruff: noqa: S101


class TestMain:
    def test_main(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython@3.13"],
            stdout="""[
  {"version": "3.13.0"},
  {"version": "3.13.1"},
  {"version": "3.13.2rc1"}
]""",
        )

        main(["3.13"])
        assert capsys.readouterr().out.strip() == "3.13.1"

    def test_main_fails(
        self,
        fp: FakeProcess,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("os.getenv").return_value = "uv"
        fp.register(
            ["uv", "python", "list", "--output-format=json", "cpython@3.13"],
            stdout="""[
  {"version": "3.13.2rc1"}
]""",
        )

        with pytest.raises(ValueError):
            main(["3.13"])
