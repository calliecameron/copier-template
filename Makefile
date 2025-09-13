.PHONY: all
all: lint test

.PHONY: deps
deps: .deps-installed

.deps-installed: pyproject.toml uv.lock package.json package-lock.json
	uv sync
	npm install
	uv run pre-commit install -f
	touch .deps-installed

.PHONY: lint
lint: deps
	uv run pre-commit run -a

.PHONY: test
test: deps

.PHONY: update_deps
update_deps: deps
	uv lock --upgrade
	bash -c 'source "$${NVM_DIR}/nvm.sh" && nvm use --save stable'
	npm outdated --parseable | cut -d : -f 4 | xargs npm install --save-exact
	rm -f package-lock.json
	rm -rf node_modules
	npm install
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
