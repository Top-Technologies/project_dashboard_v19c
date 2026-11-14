def migrate(cr, version):
    """Create and backfill the risk submission date before registry loading."""
    cr.execute("SELECT to_regclass('project_risk_issue')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        "ALTER TABLE project_risk_issue "
        "ADD COLUMN IF NOT EXISTS submitted_date date, "
        "ADD COLUMN IF NOT EXISTS closed_date date"
    )
    cr.execute(
        "UPDATE project_risk_issue "
        "SET submitted_date = COALESCE(submitted_date, create_date::date, CURRENT_DATE) "
        "WHERE submitted_date IS NULL"
    )
