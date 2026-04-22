"""Data access — SQLAlchemy Core queries, no business logic.

Returns SQLAlchemy rows / lightweight dataclasses; never Pydantic DTOs.
Services map repository output to DTOs before returning to routes.

Sprint 0 ships empty; repositories arrive alongside their features.
"""
