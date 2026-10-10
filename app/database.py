import os
from collections.abc import Generator
from collections.abc import Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def database_url_from_environment(environment: Mapping[str, str]) -> str:
    if configured := environment.get("DATABASE_URL"):
        return configured
    if host := environment.get("POSTGRES_HOST"):
        password = environment.get("POSTGRES_PASSWORD")
        if not password:
            raise RuntimeError("POSTGRES_PASSWORD is required when POSTGRES_HOST is set")
        return URL.create(
            "postgresql+psycopg",
            username=environment.get("POSTGRES_USER", "alphatest"),
            password=password,
            host=host,
            port=int(environment.get("POSTGRES_PORT", "5432")),
            database=environment.get("POSTGRES_DB", "alphatest"),
        ).render_as_string(hide_password=False)
    return "sqlite:///./alphatest.db"


DATABASE_URL = database_url_from_environment(os.environ)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
