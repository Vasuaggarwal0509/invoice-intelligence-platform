"""Business logic layer — orchestrates repositories + components/ pipeline.

Services raise :class:`business_layer.errors.PlatformError` subclasses;
the global handler maps those to HTTP responses. Services never see
FastAPI types.

Repository row-dataclasses (``UserRow``, ``WorkspaceRow``, …) are
re-exported here for the route layer — routes must not import
``business_layer.repositories.*`` directly (layer rule), but they
legitimately need these types to project into wire-format DTOs. Routes
get them through the services module instead.
"""

from business_layer.repositories.sessions import SessionRow
from business_layer.repositories.users import UserRow
from business_layer.repositories.workspaces import WorkspaceRow

__all__ = ["UserRow", "WorkspaceRow", "SessionRow"]
