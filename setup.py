from setuptools import setup, find_packages


setup(
    name='alpha_homora_v2',
    version='0.0.1',
    author='PathX AI LLC',
    author_email='pathxtech@gmail.com',
    description='Testing installation of Package',
    url='https://github.com/PathX-Projects/Alpha-Homora-V2-Python',
    # license='MIT',
    packages=find_packages(),
    install_requires=[line.strip() for line in open('requirements.txt').readlines()],
)