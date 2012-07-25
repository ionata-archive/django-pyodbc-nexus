from django.db.backends import BaseDatabaseOperations
from sql_server.pyodbc.nexus import query
import datetime
import time
import decimal
import unicodedata


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "sql_server.pyodbc.nexus.compiler"
    def __init__(self, connection):
        if connection._DJANGO_VERSION >= 14:
            super(DatabaseOperations, self).__init__(connection)
        else:
            super(DatabaseOperations, self).__init__()
        self.connection = connection
        self._ss_ver = None

    # TODO Work out how to find this out, if it is required
    sql_server_ver = 1

    def date_extract_sql(self, lookup_type, field_name):
        """
        Given a lookup_type of 'year', 'month', 'day' or 'week_day', returns
        the SQL that extracts a value from the given date field field_name.
        """
        if lookup_type == 'week_day':
            return "DATEPART(dw, %s)" % field_name
        else:
            return "DATEPART(%s, %s)" % (lookup_type, field_name)

    def date_trunc_sql(self, lookup_type, field_name):
        """
        Given a lookup_type of 'year', 'month' or 'day', returns the SQL that
        truncates the given date field field_name to a DATE object with only
        the given specificity.
        """
        if lookup_type == 'year':
            return "Convert(datetime, Convert(varchar, DATEPART(year, %s)) + '/01/01')" % field_name
        if lookup_type == 'month':
            return "Convert(datetime, Convert(varchar, DATEPART(year, %s)) + '/' + Convert(varchar, DATEPART(month, %s)) + '/01')" % (field_name, field_name)
        if lookup_type == 'day':
            return "Convert(datetime, Convert(varchar(12), %s, 112))" % field_name

    def field_cast_sql(self, db_type):
        """
        Given a column type (e.g. 'BLOB', 'VARCHAR'), returns the SQL necessary
        to cast it before using it in a WHERE statement. Note that the
        resulting string should contain a '%s' placeholder for the column being
        searched against.
        """
        if self.sql_server_ver < 2005 and db_type and db_type.lower() == 'ntext':
            return 'CAST(%s as nvarchar)'
        return '%s'

    def fulltext_search_sql(self, field_name):
        """
        Returns the SQL WHERE clause to use in order to perform a full-text
        search of the given field_name. Note that the resulting string should
        contain a '%s' placeholder for the value being searched against.
        """
        return 'CONTAINS(%s, %%s)' % field_name

    def last_insert_id(self, cursor, table_name, pk_name):
        """
        Given a cursor object that has just performed an INSERT statement into
        a table that has an auto-incrementing ID, returns the newly created ID.

        This method also receives the table name and the name of the primary-key
        column.
        """
        table_name = self.quote_name(table_name)
        cursor.execute("SELECT LASTAUTOINC")
        return cursor.fetchone()[0]

    def fetch_returned_insert_id(self, cursor):
        """
        Given a cursor object that has just performed an INSERT/OUTPUT statement
        into a table that has an auto-incrementing ID, returns the newly created
        ID.
        """
        return cursor.fetchone()[0]

    def lookup_cast(self, lookup_type):
        if lookup_type in ('iexact', 'icontains', 'istartswith', 'iendswith'):
            return "UPPER(%s)"
        return "%s"

    def query_class(self, DefaultQueryClass):
        """
        Given the default Query class, returns a custom Query class
        to use for this backend. Returns None if a custom Query isn't used.
        See also BaseDatabaseFeatures.uses_custom_query_class, which regulates
        whether this method is called at all.
        """
        return query.query_class(DefaultQueryClass)

    def quote_name(self, name):
        """
        Returns a quoted version of the given table, index or column name. Does
        not quote the given name if it's already been quoted.
        """
        if name.startswith('"') and name.endswith('"'):
            return name # Quoting once is enough.
        return '"%s"' % name

    def random_function_sql(self):
        """
        Returns a SQL expression that returns a random value.
        """
        return "RAND()"

    def last_executed_query(self, cursor, sql, params):
        """
        Returns a string of the query last executed by the given cursor, with
        placeholders replaced with actual values.

        `sql` is the raw query containing placeholders, and `params` is the
        sequence of parameters. These are used by default, but this method
        exists for database backends to provide a better implementation
        according to their own quoting schemes.
        """
        return super(DatabaseOperations, self).last_executed_query(cursor, cursor.last_sql, cursor.last_params)

    #def savepoint_create_sql(self, sid):
    #    """
    #    Returns the SQL for starting a new savepoint. Only required if the
    #    "uses_savepoints" feature is True. The "sid" parameter is a string
    #    for the savepoint id.
    #    """
    #    return "SAVE TRANSACTION %s" % sid

    #def savepoint_commit_sql(self, sid):
    #    """
    #    Returns the SQL for committing the given savepoint.
    #    """
    #    return "COMMIT TRANSACTION %s" % sid

    #def savepoint_rollback_sql(self, sid):
    #    """
    #    Returns the SQL for rolling back the given savepoint.
    #    """
    #    return "ROLLBACK TRANSACTION %s" % sid

    def sql_flush(self, style, tables, sequences):
        """
        Returns a list of SQL statements required to remove all data from
        the given database tables (without actually removing the tables
        themselves).

        The `style` argument is a Style object as returned by either
        color_style() or no_style() in django.core.management.color.
        """
        if tables:
            # Cannot use TRUNCATE on tables that are referenced by a FOREIGN KEY
            # So must use the much slower DELETE
            from django.db import connection
            cursor = connection.cursor()
            # Try to minimize the risks of the braindeaded inconsistency in
            # DBCC CHEKIDENT(table, RESEED, n) behavior.
            seqs = []
            for seq in sequences:
                cursor.execute("SELECT COUNT(*) FROM %s" % self.quote_name(seq["table"]))
                rowcnt = cursor.fetchone()[0]
                elem = {}
                if rowcnt:
                    elem['start_id'] = 0
                else:
                    elem['start_id'] = 1
                elem.update(seq)
                seqs.append(elem)
            cursor.execute("SELECT TABLE_NAME, CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_TYPE not in ('PRIMARY KEY','UNIQUE')")
            fks = cursor.fetchall()
            sql_list = ['ALTER TABLE %s NOCHECK CONSTRAINT %s;' % \
                    (self.quote_name(fk[0]), self.quote_name(fk[1])) for fk in fks]
            sql_list.extend(['%s %s %s;' % (style.SQL_KEYWORD('DELETE'), style.SQL_KEYWORD('FROM'),
                             style.SQL_FIELD(self.quote_name(table)) ) for table in tables])
            # Then reset the counters on each table.
            sql_list.extend(['%s %s (%s, %s, %s) %s %s;' % (
                style.SQL_KEYWORD('DBCC'),
                style.SQL_KEYWORD('CHECKIDENT'),
                style.SQL_FIELD(self.quote_name(seq["table"])),
                style.SQL_KEYWORD('RESEED'),
                style.SQL_FIELD('%d' % seq['start_id']),
                style.SQL_KEYWORD('WITH'),
                style.SQL_KEYWORD('NO_INFOMSGS'),
                ) for seq in seqs])
            sql_list.extend(['ALTER TABLE %s CHECK CONSTRAINT %s;' % \
                    (self.quote_name(fk[0]), self.quote_name(fk[1])) for fk in fks])
            return sql_list
        else:
            return []

    #def sequence_reset_sql(self, style, model_list):
    #    """
    #    Returns a list of the SQL statements required to reset sequences for
    #    the given models.
    #
    #    The `style` argument is a Style object as returned by either
    #    color_style() or no_style() in django.core.management.color.
    #    """
    #    from django.db import models
    #    output = []
    #    for model in model_list:
    #        for f in model._meta.local_fields:
    #            if isinstance(f, models.AutoField):
    #                output.append(...)
    #                break # Only one AutoField is allowed per model, so don't bother continuing.
    #        for f in model._meta.many_to_many:
    #            output.append(...)
    #    return output

    def start_transaction_sql(self):
        """
        Returns the SQL statement required to start a transaction.
        """
        return "START TRANSACTION;"

    def end_transaction_sql(self, success=True):
        if not success:
            return "ROLLBACK;"
        return "COMMIT;"

    def sql_for_tablespace(self, tablespace, inline=False):
        """
        Returns the SQL that will be appended to tables or rows to define
        a tablespace. Returns '' if the backend doesn't use tablespaces.
        """
        return "ON %s" % self.quote_name(tablespace)

    def prep_for_like_query(self, x):
        """Prepares a value for use in a LIKE query."""
        unicodedata.normalize('NFKD', x).encode('ascii','ignore').replace('\\', '\\\\').replace('[', '[[]').replace('%', '[%]').replace('_', '[_]')

    def prep_for_iexact_query(self, x):
        """
        Same as prep_for_like_query(), but called for "iexact" matches, which
        need not necessarily be implemented using "LIKE" in the backend.
        """
        return unicodedata.normalize('NFKD', x).encode('ascii', 'ignore')

    def value_to_db_date(self, value):
        """
        Transform a date value to an object compatible with what is expected
        by the backend driver for date columns.
        """
        if value is None:
            return None
        
        return value

    def value_to_db_datetime(self, value):
        """
        Transform a datetime value to an object compatible with what is expected
        by the backend driver for datetime columns.
        """
        if value is None:
            return None
        
        return value

    def value_to_db_time(self, value):
        """
        Transform a time value to an object compatible with what is expected
        by the backend driver for time columns.
        """
        if value is None:
            return None
        # SQL Server doesn't support microseconds
        if isinstance(value, basestring):
            value = datetime.datetime(*(time.strptime(value, '%H:%M:%S')[:6]))
        return value

    def year_lookup_bounds(self, value):
        """
        Returns a two-elements list with the lower and upper bound to be used
        with a BETWEEN operator to query a field value using a year lookup

        `value` is an int, containing the looked-up year.
        """
        first = '%s-01-01 00:00:00'
        # SQL Server doesn't support microseconds
        last = '%s-12-31 23:59:59'
        return [first % value, last % value]
    def value_to_db_decimal(self, value, max_digits, decimal_places):
        """
        Transform a decimal.Decimal value to an object compatible with what is
        expected by the backend driver for decimal (numeric) columns.
        """
        if value is None:
            return None
        if isinstance(value, decimal.Decimal):
            context = decimal.getcontext().copy()
            context.prec = max_digits
            return u"%.*f" % (decimal_places, value.quantize(decimal.Decimal(".1") ** decimal_places, context=context))
        else:
            return u"%.*f" % (decimal_places, value)

    def convert_values(self, value, field):
        """
        Coerce the value returned by the database backend into a consistent
        type that is compatible with the field type.

        In our case, cater for the fact that SQL Server < 2008 has no
        separate Date and Time data types.
        TODO: See how we'll handle this for SQL Server >= 2008
        """
        if value is None:
            return None

        if field and field.get_internal_type() == 'DateTimeField':
            if value is '':
                return None
            return value

        elif field and field.get_internal_type() == 'DateField':
            if value is '':
                return None
            if isinstance(value, datetime.datetime):
                value = value.date() # extract date

        elif field and field.get_internal_type() == 'TimeField' or (isinstance(value, datetime.datetime) and value.year == 1900 and value.month == value.day == 1):
            if value is '':
                return None

            if isinstance(value, basestring):
                try:
                    value = datetime.datetime.strptime(value, "%I:%M:%S %p").time()
                except ValueError:
                    try:
                        value = datetime.datetime.strptime(value, "%H:%M:%S").time()
                    except ValueError:
                        raise ValueError("Could not parse time string from database: %s" % value)
            else:
                try:
                    value = value.time() # extract time
                except:
                    raise ValueError("Value from database does not implement `time()`: %s" % value)
        # Some cases (for example when select_related() is used) aren't
        # caught by the DateField case above and date fields arrive from
        # the DB as datetime instances.
        # Implement a workaround stealing the idea from the Oracle
        # backend. It's not perfect so the same warning applies (i.e. if a
        # query results in valid date+time values with the time part set
        # to midnight, this workaround can surprise us by converting them
        # to the datetime.date Python type).
        elif isinstance(value, datetime.datetime) and value.hour == value.minute == value.second == value.microsecond == 0:
            value = value.date()
        # Force floats to the correct type
        elif value is not None and field and field.get_internal_type() == 'FloatField':
            value = float(value)
        return value