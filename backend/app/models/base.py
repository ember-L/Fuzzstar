"""Declarative base shared by every ORM model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single metadata registry used by Alembic and the test fixtures."""
