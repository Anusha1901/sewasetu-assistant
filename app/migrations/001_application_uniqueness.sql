-- Apply explicitly to existing databases; never modifies/deletes conflicting rows.
-- New databases receive these same indexes from schema.sql before the seed import.
-- A regular index build locks out writes while validating; appropriate for this
-- small handout database. Schedule a maintenance window on a live deployment.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS uq_app_application_no
    ON applications(application_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_app_active_mobile
    ON applications(mobile)
    WHERE status IN ('PENDING', 'APPROVED', 'DEEMED_APPROVED');
COMMIT;
