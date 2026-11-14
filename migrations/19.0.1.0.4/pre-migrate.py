def migrate(cr, version):
    cr.execute("SELECT to_regclass('project_risk_issue')")
    if not cr.fetchone()[0]:
        return

    # Production databases can be missing this column even though the model
    # field is already loaded. Add it before registry schema synchronization
    # so client project details can continue reading risk and issue records.
    cr.execute(
        "ALTER TABLE project_risk_issue "
        "ADD COLUMN IF NOT EXISTS submitted_date date"
    )
    cr.execute(
        "UPDATE project_risk_issue "
        "SET submitted_date = COALESCE(submitted_date, create_date::date, CURRENT_DATE) "
        "WHERE submitted_date IS NULL"
    )
