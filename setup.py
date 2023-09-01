#!/usr/bin/env python
"""Notify.

    Asynchronous library for sending notifications, used by Navigator.
See:
  https://github.com/phenobarbital/async-notify
"""
import ast
from os import path
from setuptools import find_packages, setup, Extension
from Cython.Build import cythonize


def get_path(filename):
    return path.join(path.dirname(path.abspath(__file__)), filename)


def readme():
    with open(get_path('README.md'), 'r', encoding='utf-8') as rd:
        return rd.read()


COMPILE_ARGS = ["-O2"]


extensions = [
    Extension(
        name='notify.exceptions',
        sources=['notify/exceptions.pyx'],
        extra_compile_args=COMPILE_ARGS,
        language="c"
    ),
    Extension(
        name='notify.types.typedefs',
        sources=['notify/types/typedefs.pyx'],
        extra_compile_args=COMPILE_ARGS,
    ),
]


version = get_path('notify/version.py')
with open(version, 'r', encoding='utf-8') as meta:
    # exec(meta.read())
    t = compile(meta.read(), version, 'exec', ast.PyCF_ONLY_AST)
    for node in (n for n in t.body if isinstance(n, ast.Assign)):
        if len(node.targets) == 1:
            name = node.targets[0]
            if isinstance(name, ast.Name) and name.id in (
                '__version__',
                '__title__',
                '__description__',
                '__author__',
                '__license__', '__author_email__'
            ):
                v = node.value
                if name.id == '__version__':
                    __version__ = v.s
                if name.id == '__title__':
                    __title__ = v.s
                if name.id == '__description__':
                    __description__ = v.s
                if name.id == '__license__':
                    __license__ = v.s
                if name.id == '__author__':
                    __author__ = v.s
                if name.id == '__author_email__':
                    __author_email__ = v.s

setup(
    name=__title__,
    version=__version__,
    author='Jesus Lara',
    author_email='jesuslara@phenobarbital.info',
    url='https://github.com/phenobarbital/async-notify',
    description=__description__,
    long_description=readme(),
    long_description_content_type='text/markdown',
    license=__license__,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Environment :: Web Environment',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Framework :: AsyncIO',
        'License :: OSI Approved :: BSD License',
    ],
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    package_data={"notify": ["py.typed"]},
    include_package_data=True,
    python_requires=">=3.9.16",
    zip_safe=False,
    setup_requires=[
        'wheel==0.40.0',
    ],
    install_requires=[
        'Cython==0.29.33',
        'wheel==0.40.0',
        'asyncio==3.4.3',
        'uvloop==0.17.0',
        'aiosmtplib==2.0.1',
        'python-datamodel>=0.3.12',
        'navconfig[default]>=1.3.5',
        'cloudpickle==2.2.1',
        'redis==4.5.5'
    ],
    extras_require={
        "default": [
            'emoji==2.2.0',
            'aiogram==2.25.1',
            'slack_bolt==1.18.0'
        ],
        "telegram": [
            'emoji==2.2.0',
            'aiogram==2.25.1',
            'pillow==9.5.0'
        ],
        "push": [
            'onesignal-sdk==2.0.0',
        ],
        "boto3": [
            "botocore==1.31.40",
            "aiobotocore==2.5.0",
            "aioboto3==11.2.0",
        ],
        "google": [
            'gmail==0.6.3',
            'google-auth>=2.6.0',
            'google-auth-httplib2>=0.1.0',
        ],
        "azure": [
            'pyo365==0.1.3',
            "o365==2.0.27",
            'msal==1.22.0',
            "Office365-REST-Python-Client==2.2.1",
        ],
        "all": [
            'emoji==2.2.0',
            'gmail==0.6.3',
            'google-auth>=2.6.0',
            'google-auth-httplib2>=0.1.0',
            'onesignal-sdk==2.0.0',
            "o365==2.0.27",
            "Office365-REST-Python-Client==2.2.1",
            'msal==1.22.0',
            'PySocks==1.7.1',
            'pyshorteners==1.0.1',
            'tweepy==4.14.0',
            'twilio==8.2.2',
            'slixmpp==1.8.3',
            "slack_bolt==1.18.0",
            'aiogram==2.25.1',
            'pillow==9.5.0'
        ]
    },
    ext_modules=cythonize(extensions),
    entry_points={
        'console_scripts': [
            'notify = notify.__main__:main'
        ]
    },
    project_urls={  # Optional
        'Source': 'https://github.com/phenobarbital/async-notify',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
