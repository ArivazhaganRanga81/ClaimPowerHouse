from __future__ import annotations

from collections.abc import Generator

import pytest
from app.database import Base
from app.services.seed import seed_demo
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session_factory(tmp_path):
    database_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as seed_session:
        seed_demo(seed_session)
    yield factory
    engine.dispose()


@pytest.fixture()
def session(session_factory) -> Generator[Session, None, None]:
    with session_factory() as value:
        yield value
