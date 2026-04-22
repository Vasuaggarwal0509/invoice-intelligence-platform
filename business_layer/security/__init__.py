"""Security primitives — passwords, sessions, encryption, headers, CSRF, rate-limit, OTP.

Each module exports narrow functions; no module takes global state beyond
:class:`business_layer.config.Settings`. Stateful pieces (rate-limit
buckets, session store) are wrapped behind an interface so the single-
process in-memory backing can be swapped for Redis later without changing
callers.
"""
