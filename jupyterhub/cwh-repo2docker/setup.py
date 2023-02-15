#!/usr/bin/env python
# coding: utf-8

import sys

v = sys.version_info
if v[:2] < (3,3):
    error = "ERROR: Jupyter Hub requires Python version 3.3 or above."
    print(error, file=sys.stderr)
    sys.exit(1)

from setuptools import setup

setup_args = dict(
    name                 = 'cwh-repo2docker',
    packages             = ['cwh_repo2docker'],
    version              = '0.1.0',
    platforms            = "Linux",
    include_package_data = True,
    install_requires     = [
        "coursewareuserspawner",
        "jupyterhub~=3.1",
        "aiodocker",
        'aiohttp']
)


def main():
    setup(**setup_args)

if __name__ == '__main__':
    main()
