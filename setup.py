#!/usr/bin/env python
"""Notify.

    Asynchronous library for sending notifications, used by Navigator.
See:
https://bitbucket.org/mobileinsight1/query_api/src/master/
"""

from setuptools import setup, find_packages

setup(
    name='notify',
    version=open("VERSION").read().strip(),
    url='hhttps://github.com/MobileInsight/navigator-notify/',
    description='Asyncio Notification library with webSockets support',
    long_description='Asynchronous library for send notifications to users, used by Navigator',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3.8',
    ],
    author='Jesus Lara',
    author_email='jlara@trocglobal.com',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    setup_requires=[
        "wheel==0.37.0",
        "Cython==0.29.21",
        "asyncio==3.4.3"
    ],
    install_requires=[
        'wheel==0.37.0',
        'asyncio==3.4.3',
        'uvloop==0.16.0',
        'asyncdb>=1.7.20',
        'APScheduler==3.7.0',
        'python-telegram-bot @ git+https://github.com/phenobarbital/python-telegram-bot.git',
        'navconfig @ git+https://github.com/phenobarbital/NavConfig.git@main#egg=navconfig',
        'cffi==1.15.0',
        'pycparser==2.20',
        'decorator==5.1.0',
        'limits==1.5.1',
        'ply==3.11',
        'pylogbeat==2.0.0',
        'urllib3==1.26.7',
        'requests==2.26.0',
        'outcome==1.1.0',
        'pillow==8.0.1',
        'oauthlib==3.1.1',
        'PySocks==1.7.1',
        'gmail==0.6.3',
        'pyo365==0.1.3',
        'slixmpp==1.7.0',
        'pyshorteners==1.0.1',
        'twilio==6.48.0',
        'telegram==0.0.1',
        'aioimaplib==0.9.0',
        'aiosmtplib==1.1.6',
        'tweepy==3.9.0'
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
