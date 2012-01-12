from django.db.backends.creation import BaseDatabaseCreation
import base64
from django.utils.hashcompat import md5_constructor
import random

class DataTypesWrapper(dict):
    pass

class DatabaseCreation(BaseDatabaseCreation):
    # This dictionary maps Field objects to their associated MS SQL column
    # types, as strings. Column-type strings can contain format strings; they'll
    # be interpolated against the values of Field.__dict__ before being output.
    # If a column type is set to None, it won't be included in the output.
    #
    # Any format strings starting with "qn_" are quoted before being used in the
    # output (the "qn_" prefix is stripped before the lookup is performed.

    data_types = DataTypesWrapper({
    #data_types = {
        'AutoField':         'AUTOINC',
        'BooleanField':      'BOOLEAN',
        'CharField':         'VARCHAR(%(max_length)s)',
        'CommaSeparatedIntegerField': 'VARCHAR(%(max_length)s)',
        'DateField':         'DATE',
        'DateTimeField':     'DATETIME',
        'DecimalField':      'NUMERIC(%(max_digits)s, %(decimal_places)s)',
        'FileField':         'VARCHAR(%(max_length)s)',
        'FilePathField':     'VARCHAR(%(max_length)s)',
        'FloatField':        'DOUBLE PRECISION',
        'IntegerField':      'INT',
        'IPAddressField':    'VARCHAR(15)',
        'NullBooleanField':  'BOOLEAN',
        'OneToOneField':     'INT',
        'PositiveIntegerField': 'DWORD',
        'PositiveSmallIntegerField': 'WORD',
        'SlugField':         'VARCHAR(%(max_length)s)',
        'SmallIntegerField': 'SMALLINT',
        'TextField':         'TEXT',
        'TimeField':         'TIME',
    #}
    })

    def _destroy_test_db(self, test_database_name, verbosity):
        "Internal implementation - remove the test db tables."
        cursor = self.connection.cursor()
        self.set_autocommit()
        #time.sleep(1) # To avoid "database is being accessed by other users" errors.
        cursor.execute("ALTER DATABASE %s SET SINGLE_USER WITH ROLLBACK IMMEDIATE " % \
                self.connection.ops.quote_name(test_database_name))
        cursor.execute("DROP DATABASE %s" % \
                self.connection.ops.quote_name(test_database_name))
        self.connection.close()
