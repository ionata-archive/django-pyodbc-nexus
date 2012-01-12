#!/usr/bin/env python

from distutils.core import setup

setup(name='sql_server.pyodbc.nexus',
      version='1.0',
      description='Django NexusDB using pyodbc',
      author='Ionata Web Solutions',
      url='https://bitbucket.org/ionata/django-pyodbc-nexus',
      packages=['sql_server', 'sql_server.pyodbc', 'sql_server.pyodbc.nexus', 'sql_server.extra'],
     )
