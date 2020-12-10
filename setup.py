#!/usr/bin/env python
"""Notify
    Asynchronous library for sending notifications, used by Navigator.
See:
https://bitbucket.org/mobileinsight1/query_api/src/master/
"""

from setuptools import setup, find_packages

setup(
    name='notify',
    version='0.1.2',
    url='https://bitbucket.org/mobileinsight1/query_api/',
    description='Asyncio Notification library with webSockets support',
    long_description='Asynchronous library for send notifications to users, used by Navigator',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3.7',
    ],
    author='Jesus Lara',
    author_email='jlara@trocglobal.com',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
    'numpy==1.19.4',
    'asyncio==3.4.3',
    'twilio==6.48.0',
    'telegram==0.0.1',
    'python-telegram-bot==13.0',
    'pillow==8.0.1',
    'gmail==0.6.3',
    'pyo365==0.1.3',
    'slixmpp==1.5.2',
    'pyshorteners==1.0.1',
    'tweepy==3.9.0',
    'asyncdb',
    'navconfig'
    ],
    dependency_links=[
        'git+https://github.com/phenobarbital/asyncdb.git@master#egg=asyncdb',
        'git+https://github.com/phenobarbital/NavConfig.git@main#egg=navconfig'
    ],
    project_urls={  # Optional
        'Source': 'https://bitbucket.org/mobileinsight1/query_api/',
        'Funding': 'https://paypal.me/phenobarbital',
        'Say Thanks!': 'https://saythanks.io/to/phenobarbital',
    },
)
