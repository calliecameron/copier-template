# Copier template

[![template](https://img.shields.io/badge/template-calliecameron%2Fcopier--template-blue)](https://github.com/calliecameron/copier-template)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-blue?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![CI](https://github.com/calliecameron/copier-template/actions/workflows/ci.yml/badge.svg)](https://github.com/calliecameron/copier-template/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.12_%7C_3.13_%7C_3.14-blue)

A [Copier](https://github.com/copier-org/copier) template for multi-language projects.

This is mainly intended for personal use – it includes the languages and tools that I use.

Requirements:

- `make`, `uv`, `nvm`

Usage:

- First run:

  ```shell
  uv tool run \
    --with copier-template-extensions \
    --with cookiecutter \
    --with frozendict \
    --with identify \
    copier copy --trust https://github.com/calliecameron/copier-template .
  ```

- Subsequent runs:

  ```shell
  make template_update
  ```
