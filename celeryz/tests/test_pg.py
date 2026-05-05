from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from celeryz.pg import create_pg_engine


def test_create_pg_engine_success(mocker: MockerFixture) -> None:
    mock_make_sync_engine: MagicMock = mocker.patch("celeryz.pg.make_sync_engine")
    mock_to_sync_url: MagicMock = mocker.patch(
        "celeryz.pg.to_sync_url",
        return_value="postgresql://user:pass@host/db",
    )

    mock_engine: Engine = cast(Engine, MagicMock(spec=Engine))
    mock_make_sync_engine.return_value = mock_engine

    engine: Engine = create_pg_engine("postgresql+asyncpg://user:pass@host/db")

    mock_to_sync_url.assert_called_once_with("postgresql+asyncpg://user:pass@host/db")
    mock_make_sync_engine.assert_called_once_with("postgresql://user:pass@host/db")
    mock_engine.connect.assert_called_once()
    assert engine == mock_engine


def test_create_pg_engine_failure(mocker: MockerFixture) -> None:
    mock_make_sync_engine: MagicMock = mocker.patch("celeryz.pg.make_sync_engine")
    mocker.patch("celeryz.pg.to_sync_url", return_value="postgresql://user:pass@host/db")

    mock_engine: Engine = cast(Engine, MagicMock(spec=Engine))
    # Simulate connection failure
    mock_engine.connect.side_effect = OperationalError(None, None, "Connection failed")
    mock_make_sync_engine.return_value = mock_engine

    with pytest.raises(OperationalError):
        create_pg_engine("postgresql+asyncpg://user:pass@host/db")
