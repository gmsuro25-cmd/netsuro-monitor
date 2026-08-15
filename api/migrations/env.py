import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app.config import read_secret


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def database_url():
    user = os.environ["POSTGRES_USER"]
    password = read_secret("POSTGRES_PASSWORD")
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    database = os.environ["POSTGRES_DB"]
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )


def run_migrations_online():
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
