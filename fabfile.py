"""
Creating standalone Django apps is a PITA because you're not in a project, so
you don't have a settings.py file.  I can never remember to define
DJANGO_SETTINGS_MODULE, so I run these commands which get the right env
automatically.
"""
import functools
import os

from fabric.api import local as _local


NAME = os.path.basename(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.dirname(__file__))
APP_NAME = 'urlographer'

os.environ['DJANGO_SETTINGS_MODULE'] = 'test_app.settings'
os.environ['PYTHONPATH'] = os.pathsep.join([ROOT,])

_local = functools.partial(_local, capture=False)


def shell():
    """Start a Django shell with the test settings."""
    _local('django-admin.py shell')


def test():
    """Run the test suite."""
    _local('django-admin.py test')


def ipdb_test():
    """
    Run the test suite with ipdbplugin enabled for errors and failures,
    stopping after first error or failure.
    """
    _local('django-admin.py test --ipdb --ipdb-failures -sx')


def jenkins_test():
    """Run the test suite with Django Jenkins, cover, pep8 and pyflakes."""
    _local('django-admin.py jenkins')


def serve():
    """Start the Django dev server."""
    _local('django-admin.py runserver')


def syncdb():
    """Create a database for testing in the shell or server."""
    _local('django-admin.py syncdb')


def schema():
    """Create a schema migration for any changes."""
    _local('django-admin.py schemamigration %s --auto' % APP_NAME)


def migrate():
    """Update a testing database with south."""
    _local('django-admin.py migrate')


def pypi_upload():
    """build and upload to PyPi"""
    _local('python setup.py sdist bdist_egg upload')

