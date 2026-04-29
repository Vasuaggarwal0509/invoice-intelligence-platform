-- 0002_ca_linkage — enable CA persona + business↔CA linkage.
--
-- A business workspace may nominate a CA firm as their tax advisor. The
-- pairing is derived: the business stores the CA firm's GSTIN, and the
-- CA dashboard aggregates every business whose ca_gstin matches the
-- CA's own workspace.gstin. No invite flow in v1 — the CA signs up and
-- any business that has listed them appears on their dashboard.
--
-- Runs ONCE. The schema_migrations tracking table in
-- business_layer.db.engine.init_db() ensures we don't re-run and hit
-- "duplicate column" errors.

ALTER TABLE workspaces ADD COLUMN ca_gstin TEXT;

-- CA dashboard's main lookup: "all businesses whose ca_gstin = my gstin".
CREATE INDEX IF NOT EXISTS ix_workspaces_ca_gstin ON workspaces(ca_gstin);
