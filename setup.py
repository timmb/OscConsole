from setuptools import setup
import py2app

APP = ['OscConsole.py']
DATA_FILES = []
OPTIONS = {'argv_emulation': False}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)