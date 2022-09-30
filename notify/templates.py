from pathlib import Path
from typing import (
    Optional
)
from jinja2 import (
    Environment,
    FileSystemLoader
)


jinja_config = {
    'enable_async': False,
    'extensions': [
        'jinja2.ext.i18n'
    ]
}


class TemplateParser(object):
    """
    TemplateParser.

    This is a wrapper for the Jinja2 template engine.
    """
    def __init__(self, directory: Path, **kwargs):
        self.template = None
        self.path = directory.resolve()
        if not self.path.exists():
            raise RuntimeError(
                f'Notify: template directory {directory} does not exist'
            )
        if 'config' in kwargs:
            self.config = {**jinja_config, **kwargs['config']}
        else:
            self.config = jinja_config
        # creating loader:
        templateLoader = FileSystemLoader(
            searchpath=[str(self.path)]
        )
        # initialize the environment
        try:
            # TODO: check the bug ,encoding='ANSI'
            self.env = Environment(loader=templateLoader, **self.config)
            #compiled_path = BytesIO()
            compiled_path = str(self.path.joinpath('.compiled'))
            self.env.compile_templates(target=compiled_path, zip='deflated')
        except Exception as err:
            raise RuntimeError(
                f'Notify: Error loading Template Environment: {err}'
            ) from err

    def get_template(self, filename: str):
        self.template = self.env.get_template(str(filename))
        return self.template

    @property
    def environment(self):
        return self.env

    def render(self, filename: str, params: Optional[dict] = None) -> str:
        if not params:
            params = {}
        result = None
        try:
            self.template = self.env.get_template(str(filename))
            result = self.template.render(**params)
            return result
        except Exception as err:
            raise RuntimeError(
                f'Notify: Error rendering template: {filename}, error: {err}'
            ) from err
