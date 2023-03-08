CODE_DIRS := notify/ tests/ examples/

venv:
	python3.10 -m venv .venv
	echo 'run `source .venv/bin/activate` to start develop Notify'

develop:
	pip install wheel==0.38.4
	pip install -e .
	python -m pip install -Ur docs/requirements-dev.txt

dev:
	flit install --symlink

release: lint test clean
	flit publish

format:
	python -m black notify

lint:
	python -m pylint --rcfile .pylint notify/*.py
	python -m black --check notify
	flake8 $(CODE_DIRS)

test:
	tox
	python -m coverage run -m tests
	python -m coverage report
	python -m mypy notify/*.py
	python -m mypy notify/providers/*.py

distclean:
	rm -rf .venv
