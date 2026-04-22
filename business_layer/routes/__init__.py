"""FastAPI routes — thin glue between HTTP and services.

Routes call services, never repositories directly. All route modules are
wired into the app in :mod:`business_layer.app`.

Sprint 0 ships the ``/health`` endpoint only.
"""
