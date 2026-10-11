import sqlite3

import pytest

from batches import service as batches_service
from feedback import service as feedback_service


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    batches_service.init_schema(connection)
    feedback_service.init_schema(connection)
    yield connection
    connection.close()
