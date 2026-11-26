"""Audit log is append-only at database level (PostgreSQL only).

PostgreSQL: triggers refuse UPDATE and DELETE on common_auditlog for every client (app, psql, admin tools).
TRUNCATE is not blocked, so `manage.py flush` and test databases still work; only the database owner can
TRUNCATE. SQLite (development): no trigger; the model code refuses changes (apps/common/models.py).
"""
from django.db import migrations

PG_UP = """
CREATE OR REPLACE FUNCTION firmflow_auditlog_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING MESSAGE = 'common_auditlog is append-only: ' || TG_OP || ' refused', ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS auditlog_no_update ON common_auditlog;
DROP TRIGGER IF EXISTS auditlog_no_delete ON common_auditlog;
CREATE TRIGGER auditlog_no_update BEFORE UPDATE ON common_auditlog FOR EACH ROW EXECUTE FUNCTION firmflow_auditlog_append_only();
CREATE TRIGGER auditlog_no_delete BEFORE DELETE ON common_auditlog FOR EACH ROW EXECUTE FUNCTION firmflow_auditlog_append_only();
"""
PG_DOWN = """
DROP TRIGGER IF EXISTS auditlog_no_update ON common_auditlog;
DROP TRIGGER IF EXISTS auditlog_no_delete ON common_auditlog;
DROP FUNCTION IF EXISTS firmflow_auditlog_append_only();
"""


def _run(schema_editor, sql):
    # Plain cursor, no parameters: the SQL is sent as it is (no placeholder formatting)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


def up(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        _run(schema_editor, PG_UP)


def down(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        _run(schema_editor, PG_DOWN)


class Migration(migrations.Migration):
    dependencies = [('common', '0001_initial')]
    operations = [migrations.RunPython(up, down)]
