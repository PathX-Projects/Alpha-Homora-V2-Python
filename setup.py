from setuptools import setup, find_packages


setup(
    name='alpha_homora_v2',
    version='0.0.2',
    author='PathX AI LLC',
    author_email='pathxtech@gmail.com',
    description='Testing installation of Package',
    url='https://github.com/PathX-Projects/Alpha-Homora-V2-Python',
    # license='MIT',
    packages=['alpha_homora_v2'],
    include_package_data=True,
    install_requires=[line.strip() for line in open('requirements.txt').readlines()],
)