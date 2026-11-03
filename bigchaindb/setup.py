# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0
# Modified by thematerials-network contributors, 2026; see NOTICE at the repository root.

"""
BigchainDB: The Blockchain Database

For full docs visit https://docs.bigchaindb.com

"""

import sys
from setuptools import setup, find_packages

if sys.version_info < (3, 12):
    sys.exit('Please use Python version 3.12 or higher.')

# get the version
version = {}
with open('bigchaindb/version.py') as fp:
    exec(fp.read(), version)

def check_setuptools_features():
    """Check if setuptools is up to date."""
    from importlib.metadata import version as get_version
    # setuptools 8.0 added PEP 440 `~=` support, which the old check probed for.
    if int(get_version('setuptools').split('.')[0]) < 8:
        sys.exit('Your Python distribution comes with an incompatible version '
                 'of `setuptools`. Please run:\n'
                 ' $ pip3 install --upgrade setuptools\n'
                 'and then run this command again')


check_setuptools_features()

dev_require = [
    'ipdb',
    'ipython',
    'watchdog',
    'logging_tree',
    'pre-commit'
]

docs_require = [
    'Sphinx~=1.0',
    'recommonmark>=0.4.0',
    'sphinx-rtd-theme>=0.1.9',
    'sphinxcontrib-httpdomain>=1.5.0',
    'sphinxcontrib-napoleon>=0.4.4',
    'aafigure>=0.6',
    'wget'
]

tests_require = [
    'coverage',
    'pep8',
    'flake8',
    'flake8-quotes==0.8.1',
    'hypothesis>=5.3.0',
    # Removed pylint because its GPL license isn't Apache2-compatible
    'pytest>=3.0.0',
    'pytest-cov==2.8.1',
    'pytest-mock',
    'pytest-xdist',
    'pytest-flask',
    'pytest-aiohttp',
    'pytest-asyncio',
    'tox',
] + docs_require

# The tested set: every version equals requirements-py312.txt (Python 3.12).
install_requires = [
    'aiohttp==3.14.5',
    'bigchaindb-abci==1.0.5',
    'cryptoconditions==0.8.0',
    'flask-cors==6.0.5',
    'flask-restful==0.3.10',
    'flask==3.1.3',
    'gunicorn==26.2.0',
    'jsonschema==4.26.0',
    'logstats==0.3.0',
    'packaging==26.3',
    'pymongo==4.19.0',
    'python-rapidjson==1.25',
    'pyyaml==6.0.3',
    'requests==2.34.2',
    'setproctitle==1.3.8',
]

setup(
    name='BigchainDB',
    version=version['__version__'],
    description='BigchainDB: The Blockchain Database',
    long_description=(
        "BigchainDB allows developers and enterprises to deploy blockchain "
        "proof-of-concepts, platforms and applications with a blockchain "
        "database. BigchainDB supports a wide range of industries and use cases "
        "from identity and intellectual property to supply chains, energy, IoT "
        "and financial ecosystems. With high throughput, low latency, powerful "
        "query functionality, decentralized control, immutable data storage and "
        "built-in asset support, BigchainDB is like a database with blockchain "
        "characteristics."
        ),
    url='https://github.com/BigchainDB/bigchaindb/',
    author='BigchainDB Contributors',
    author_email='contact@ipdb.global',
    license='Apache Software License 2.0',
    license_files=['LICENSE', 'LICENSES.md'],
    zip_safe=False,
    python_requires='>=3.12',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Database',
        'Topic :: Database :: Database Engines/Servers',
        'Topic :: Software Development',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.12',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: Linux',
    ],

    packages=find_packages(exclude=['tests*']),

    scripts=['pkg/scripts/bigchaindb-monit-config'],

    entry_points={
        'console_scripts': [
            'bigchaindb=bigchaindb.commands.bigchaindb:main'
        ],
    },
    install_requires=install_requires,
    setup_requires=['pytest-runner'],
    tests_require=tests_require,
    extras_require={
        'test': tests_require,
        'dev': dev_require + tests_require + docs_require,
        'docs': docs_require,
    },
    package_data={'bigchaindb.common.schema': ['*.yaml']},
)
