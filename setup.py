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
                    name.id in (
                        '__version__',
                        '__title__',
                        '__description__',
                        '__author__',
                        '__license__', '__author_email__'):
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
        'Cython==0.29.33',
        'wheel==0.40.0',
    ],
    install_requires=[
        'Cython==0.29.33',
        'wheel==0.40.0',
        'asyncio==3.4.3',
        'uvloop==0.17.0',
        'APScheduler==3.10.1',
        'aiosmtplib==2.0.1',
        'emoji==2.2.0',
        'aiogram==2.25.1',
        'pillow==9.4.0',
        'gmail==0.6.3',
        'google-auth>=2.6.0',
        'google-auth-httplib2>=0.1.0',
        'onesignal-sdk==2.0.0',
        'pyo365==0.1.3',
        'msal==1.21.0',
        'PySocks==1.7.1',
        'pyshorteners==1.0.1',
        'twilio==8.2.2',
        'tweepy==4.12.1',
        'slixmpp==1.8.3',
        "botocore==1.27.59",
        "boto3==1.26.149",
        "aiobotocore==2.4.2",
        "aioboto3==10.4.0",
        "o365==2.0.26",
        "slack_bolt==1.16.3",
        "asyncdb[default]>=2.2.0",
        "navconfig[default]>=1.1.0"
    ],
    project_urls={  # Optional
        'Source': 'https://github.com/phenobarbital/async-notify',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
