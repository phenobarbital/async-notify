#!/usr/bin/env python
"""Notify.

    Asynchronous library for sending notifications, used by Navigator.
See:
  https://github.com/phenobarbital/async-notify
"""

from os import path
from setuptools import find_packages, setup


def get_path(filename):
    return path.join(path.dirname(path.abspath(__file__)), filename)


with open(get_path('README.md')) as readme:
    README = readme.read()


with open(get_path('notify/version.py')) as meta:
    exec(meta.read())

setup(
    name=__title__,
    version=__version__,
    url='https://github.com/phenobarbital/async-notify',
    description=__description__,
    long_description='Asynchronous library for send notifications to users, used by Navigator',
    python_requires=">=3.8.0",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3.8',
    ],
    author='Jesus Lara',
    author_email='jesuslara@phenobarbital.info',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    setup_requires=[
        "wheel==0.37.0",
        "asyncio==3.4.3",
        "Cython==0.29.28",
        "cryptography==3.4.7",
        "cpython==0.0.6"
    ],
    install_requires=[
        'wheel==0.37.0',
        'asyncio==3.4.3',
        'uvloop==0.16.0',
        'asyncdb @ git+https://github.com/phenobarbital/asyncdb.git@fix-versions#egg=asyncdb',
        'navconfig @ git+https://github.com/phenobarbital/NavConfig.git@new-version#egg=navconfig',
        'APScheduler==3.7.0',
        'aiosmtplib==1.1.6',
        'emoji==1.6.3',
        'aiogram==2.19',
        'pillow==9.0.1',
        'gmail==0.6.3',
        'google-auth>=2.6.0',
        'google-auth-httplib2>=0.1.0',
        'pyo365==0.1.3',
        'PySocks==1.7.1',
        'pyshorteners==1.0.1',
        'twilio==7.7.0',
        'tweepy==4.6.0',
        'slixmpp==1.8.0.1',
        "aiobotocore==2.1.1",
        "botocore==1.23.24",
    ],
    tests_require=[
            'pytest>=5.4.0',
            'coverage',
            'pytest-asyncio==0.14.0',
            'pytest-xdist==2.1.0',
            'pytest-assume==2.4.2'
    ],
    dependency_links=[
        'git+https://github.com/phenobarbital/asyncdb.git@master#egg=asyncdb',
        'git+https://github.com/phenobarbital/NavConfig.git@main#egg=navconfig'
    ],
    project_urls={  # Optional
        'Source': 'https://github.com/MobileInsight/navigator-notify',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
