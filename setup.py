from setuptools import setup, find_packages

VERSION = "0.1.0"

required_packages = [
    'click',
    'rich',
    'logging_tree',
]

setup(
    name='cflowgraph',
    version=VERSION,
    description='Nicer cflowgraph output.',
    author='cdw',
    entry_points={
        'console_scripts': [
            "cflowgraph=cflowgraph.main:entrypoint",
        ],
    },
    packages=find_packages(),
    install_requires=required_packages
)
