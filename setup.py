from setuptools import setup
import sys
if sys.version_info < (3, 9):
    sys.exit('Python 3.9+ required to install this package. Install it here: https://www.python.org/downloads/')

import alpha_homora_v2


def readme():
    with open("README.md") as infile:
        return infile.read().strip()


setup(
    name='alpha-homora-v2',
    version=alpha_homora_v2.__version__,
    author='Harrison Schick',
    author_email='hschickdevs@gmail.com',
    description='An unofficial Python package that wraps Alpha Homora V2 position smart contracts.',
    long_description=readme(),
    long_description_content_type="text/markdown",
    url='https://github.com/PathX-Projects/Alpha-Homora-V2-Python',
    license='Apache-2.0',
    packages=['alpha_homora_v2'],
    include_package_data=True,
    install_requires=[line.strip() for line in open('requirements.txt').readlines()],
    python_requires='>=3.9',
)