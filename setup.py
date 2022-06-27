from setuptools import setup, find_packages


setup(
    name='alpha_homora_v2',
    version='0.9.9',
    author='Harrison Schick',
    author_email='hschickdevs@gmail.com',
    description='Python package that allows for interacting with Alpha Homora v2 position smart contracts',
    url='https://github.com/PathX-Projects/Alpha-Homora-V2-Python',
    # license='MIT',
    packages=['alpha_homora_v2'],
    include_package_data=True,
    install_requires=[line.strip() for line in open('requirements.txt').readlines()],
)