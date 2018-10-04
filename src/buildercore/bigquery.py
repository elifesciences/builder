BIGQUERY_SCHEMAS_FOLDER = 'src/buildercore/bigquery/schemas'

def schema(schema_name):
    return open('%s/%s.json' % (BIGQUERY_SCHEMAS_FOLDER, schema_name))
