import logging
from pydantic import validate_call
from core.db.engine import make_sync_engine, to_sync_url, Engine

logger = logging.getLogger(__name__)


@validate_call
def create_pg_engine(database_url: str) -> Engine:
    logger.info("Connecting to Postgres")
    postgres = make_sync_engine(to_sync_url(str(database_url)))
    # Test the connection to the database at startup, will raise an error if it fails
    postgres.connect()
    logger.info("Successfully connected to Postgres")
    return postgres
