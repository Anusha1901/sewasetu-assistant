"""Optional hosted connection settings; the original INI remains the local default."""
import os
import re
import psycopg2


def connect(config):
    url = os.environ.get('DATABASE_URL')
    if url:
        schema = os.environ.get('DATABASE_SCHEMA', 'sewasetu')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('Invalid private database schema')
        # Schema is deliberately outside Supabase's exposed public API schemas.
        return psycopg2.connect(url, sslmode='require', connect_timeout=15,
                               options='-c search_path=' + schema + ' -c timezone=Asia/Kolkata')
    return psycopg2.connect(host=config.get('database', 'host'),
                            port=config.get('database', 'port'),
                            dbname=config.get('database', 'name'),
                            user=config.get('database', 'user'),
                            password=config.get('database', 'password'))
