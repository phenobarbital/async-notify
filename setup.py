#!/usr/bin/env python
"""Notify.

    Asynchronous library for sending notifications, used by Navigator.
See:
  https://github.com/phenobarbital/async-notify
"""
import ast
from os import path

from setuptools import find_packages, setup


def get_path(filename):
    return path.join(path.dirname(path.abspath(__file__)), filename)


def readme():
    with open(get_path('README.md'), 'r', encoding='utf-8') as rd:
        return rd.read()


version = get_path('notify/version.py')
with open(version, 'r', encoding='utf-8') as meta:
    # exec(meta.read())
    t = compile(meta.read(), version, 'exec', ast.PyCF_ONLY_AST)
    for node in (n for n in t.body if isinstance(n, ast.Assign)):
        if len(node.targets) == 1:
            name = node.targets[0]
            if isinstance(name, ast.Name) and \
                    name.id in {
                        '__version__',
                        '__title__',
                        '__description__',
                        '__author__',
                        '__license__', '__author_email__'}:
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
    url='https://github.com/phenobarbital/async-notify',
    description=__description__,
    long_description=readme(),
    long_description_content_type='text/markdown',
    python_requires=">=3.8.0",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Operating System :: POSIX :: Linux",
        "Environment :: Web Environment",
        "License :: OSI Approved :: BSD License",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Framework :: AsyncIO",
    ],
    keywords=['aiogram', 'asyncio', 'aioimaplib', 'aiobotocore'],
    author='Jesus Lara',
    author_email='jesuslara@phenobarbital.info',
    packages=find_packages(exclude=['contrib', 'docs', 'tests', 'examples']),
    setup_requires=[
        "wheel==0.38.4",
        "Cython==0.29.32",
        "asyncio==3.4.3"
    ],
    install_requires=[
        'asyncio==3.4.3',
        'uvloop==0.17.0',
        'APScheduler==3.9.1',
        'aiosmtplib==2.0.0',
        'emoji==2.1.0',
        'aiogram==2.23.1',
        'pillow==9.3.0',
        'gmail==0.6.3',
        'google-auth>=2.6.0',
        'google-auth-httplib2>=0.1.0',
        'onesignal-sdk==2.0.0',
        'pyo365==0.1.3',
        'msal==1.20.0',
        'PySocks==1.7.1',
        'pyshorteners==1.0.1',
        'twilio==7.15.3',
        'tweepy==4.12.1',
        'slixmpp==1.8.3',
        "botocore==1.27.59",
        "aiobotocore==2.4.0",
        "o365==2.0.21",
        "slack_bolt==1.15.3",
        "asyncdb>=2.1.30",
        "navconfig>=1.0.6"
    ],
    tests_require=[
            'pytest>=5.4.0',
            'coverage',
            'pytest-asyncio',
            'pytest-xdist',
            'pytest-assume'
    ],
    test_suite='tests',
    project_urls={  # Optional
        'Source': 'https://github.com/phenobarbital/async-notify',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
