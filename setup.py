#!/usr/bin/env python
"""Notify.

    Asynchronous library for sending notifications, used by Navigator.
See:
  https://github.com/phenobarbital/async-notify
"""

from setuptools import setup, find_packages

setup(
    name='notify',
    version=open("VERSION").read().strip(),
    url='https://github.com/phenobarbital/async-notify',
    description='Asyncio Notification library',
    long_description='Asynchronous library for send notifications to users, used by Navigator',
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
        "asyncio==3.4.3"
        "Cython==0.29.28",
        "cryptography==3.4.7",
        "cpython==0.0.6"
    ],
    install_requires=[
        'wheel==0.37.0',
        'APScheduler==3.7.0',
        'asyncio==3.4.3',
        'uvloop==0.16.0',
        'proxylists @ git+https://github.com/phenobarbital/proxylists@main#egg=proxylists',
        'asyncdb @ git+https://github.com/phenobarbital/asyncdb.git@fix-versions#egg=asyncdb',
        'navconfig @ git+https://github.com/phenobarbital/NavConfig.git@new-version#egg=navconfig',
    ],
    tests_require=[
            'pytest>=5.4.0',
            'coverage',
            'pytest-asyncio==0.14.0',
            'pytest-xdist==2.1.0',
            'pytest-assume==2.4.2'
    ],
    dependency_links=[
        'git+https://github.com/phenobarbital/python-telegram-bot.git@master#egg=python-telegram-bot',
        'git+https://github.com/phenobarbital/asyncdb.git@master#egg=asyncdb',
        'git+https://github.com/phenobarbital/NavConfig.git@main#egg=navconfig'
    ],
    project_urls={  # Optional
        'Source': 'https://github.com/MobileInsight/navigator-notify',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
