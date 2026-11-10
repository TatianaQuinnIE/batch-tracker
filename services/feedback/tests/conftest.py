import sqlite3

import pytest

from app import create_app
from feedback import service


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    service.init_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def client(tmp_path):
    return create_app(str(tmp_path)).test_client()
