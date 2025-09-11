'''
mitsfs.test
------------
Code to support unit tests for the mitsfs (python) library.

'''

import unittest
import psycopg2
import itertools
import subprocess
import os

__all__ = [
    'Case',
    ]

db_seed = itertools.count()
def make_dbname():
    return ('mitsfs%d'  % next(db_seed))


class Case(unittest.TestCase):
    """Subclass of unittest.TestCase with a mitsfs-schema'd database
    as a test fixture."""

    @staticmethod
    def adminsql(s, *args):
        """Run an sql command with privileges."""
        db = psycopg2.connect('dbname=postgres')
        db.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        c = db.cursor()
        c.execute('set role wheel')
        c.execute(s % args)
        db.close()

    def setUp(self):
        """Create an new, empty, uniquely named MITSFS database for
        this test case."""
        self.dbname = make_dbname()
        self.dsn = 'dbname=%s' % self.dbname
       
        try:
            self.adminsql("create database %s encoding='UTF8'", self.dbname)
        except psycopg2.OperationalError:
            raise
        
        # find a schema.sql file walking up the directory. Limit to 5 levels
        # to prevent infinite loops
        schema_path = '.'
        for i in range(5):
            if 'schema.sql' in os.listdir(schema_path):
                break
            schema_path = '../' + schema_path
            
        if 'schema.sql' not in os.listdir(schema_path):
            raise Exception
            
        try:
            output = subprocess.check_output(
                ('psql', self.dsn, '-f', schema_path + '/schema.sql'),
                stderr=subprocess.STDOUT,
                ).decode('utf-8')
        except subprocess.CalledProcessError as e:
            print(e.output)
            raise

        if 'ERROR' in output:
            print('\n'.join(
                line for line in output.splitlines() if 'ERROR' in line))

        self.assertNotIn('ERROR', output)

    def tearDown(self):
        """Tear down the test fixture database."""
        self.adminsql('drop database %s', self.dbname)
