.PHONY: all
all: lint test

.PHONY: deps
deps: .deps-installed

.deps-installed: pyproject.toml uv.lock package.json package-lock.json
	./.template_scripts/uv_install_deps.sh
	./.template_scripts/npm_install_deps.sh
	uv run pre-commit install -f
	touch .deps-installed

.PHONY: lint
lint: deps
	uv run pre-commit run -a

.PHONY: test
test: deps

.PHONY: update_deps
update_deps: deps
	./.template_scripts/uv_update_deps.sh
	./.template_scripts/npm_update_deps.sh
	uv run pre-commit autoupdate

.PHONY: update_template
update_template: deps
	uv run copier update --trust

.PHONY: clean
clean:
	find . '(' -type f -name '*~' ')' -delete
	rm -f .deps-installed

.PHONY: deepclean
deepclean: clean
	rm -rf .venv
	rm -rf node_modules
	rm -rf .ruff_cache
	rm -rf .mypy_cache
