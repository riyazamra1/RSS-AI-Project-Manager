from contextlib import contextmanager
from collections.abc import Iterator

import psycopg

from .core.config import settings


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url) as connection:
        yield connection
