import logging
from pathlib import Path
from notify.settings import MEMCACHE_HOST, MEMCACHE_PORT
from asyncdb.providers.mcache import mcache
from typing import (
    Dict,
    Optional
)

from jinja2 import (
    Environment,
    FileSystemLoader,
    MemcachedBytecodeCache
)

# TODO: implementing a bytecode-cache on redis or memcached
jinja_config = {
    'autoescape': True,
    'enable_async': False,
    'extensions': [
        'jinja2.ext.autoescape',
        'jinja2.ext.with_',
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
        self.cache = mcache(params={"host": MEMCACHE_HOST, "port": MEMCACHE_PORT})
        try:
            self.cache.connection()
        except Exception as err:
            logging.error(
                'Notify: Error Connecting to Memcached'
            )
            self.cache = None
        self.path = directory.resolve()
        if not self.path.exists():
            raise RuntimeError(
                'Notify: template directory {} does not exist'.format(directory)
            )
        if 'config' in kwargs:
            self.config = {**jinja_config, **kwargs['config']}
        else:
            self.config = jinja_config
        # creating loader:
        templateLoader = FileSystemLoader(
            searchpath=[str(self.path)]
        )
        if self.cache.is_connected():
            self.config['bytecode_cache'] = MemcachedBytecodeCache(
                self.cache,
                prefix='notify_template_',
                timeout=2,
                ignore_memcache_errors=True
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
                'Notify: Error loading Template Environment: {}'.format(err)
            )

    def get_template(self, filename: str):
        self.template = self.env.get_template(str(filename))
        return self.template

    @property
    def environment(self):
        return self.env

    def render(self, filename: str, params: Optional[Dict] = {}) -> str:
        result = None
        try:
            self.template = self.env.get_template(str(filename))
            result = self.template.render(**params)
        except Exception as err:
            raise RuntimeError(
            'Notify: Error rendering template: {}, error: {}'.format(
                filename,
                err
                )
            )
        finally:
            return result
