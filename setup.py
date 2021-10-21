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
        'APScheduler==3.7.0',
        'asyncio==3.4.3',
        'uvloop==0.16.0',
        'outcome>=1.1.0',
        'pillow>=8.0.1',
        'httplib2>=0.20.1',
        'oauthlib==3.1.1',
        'PySocks==1.7.1',
        'google-auth>=2.3.0',
        'google-auth-httplib2>=0.1.0',
        'gmail==0.6.3',
        'pyo365==0.1.3',
        'slixmpp==1.7.0',
        'pyshorteners==1.0.1',
        'twilio==6.48.0',
        'telegram==0.0.1',
        'aioimaplib==0.9.0',
        'aiosmtplib==1.1.6',
        'tweepy==3.9.0',
        'tzlocal>=2.1',
        'pytz>=2021.3',
        'decorator>=5.1.0',
        'regex>=2021.9.30',
        'soupsieve>=2.2.1',
        'urllib3>=1.26.6',
        'requests>=2.25.0',
        'requests[socks]>=2.25.1',
        "botocore==1.19.29",
        "boto3==1.16.29",
        'six>=1.16.0',
        'pyasn>=1.6.1',
        'rsa>=4.7.2',
        'proxylist @ git+https://github.com/phenobarbital/proxylist@main#egg=proxylists',
        'python-telegram-bot @ git+https://github.com/phenobarbital/python-telegram-bot.git',
        'asyncdb @ git+https://github.com/phenobarbital/asyncdb.git@master#egg=asyncdb',
        'navconfig @ git+https://github.com/phenobarbital/NavConfig.git@main#egg=navconfig',
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
