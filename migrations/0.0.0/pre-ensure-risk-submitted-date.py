import json

def migrate(cr, version):
    cr.execute("SELECT to_regclass('project_risk_issue')")
    if cr.fetchone()[0]:
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

    cr.execute("SELECT id FROM ir_model_fields WHERE model = 'project.project' AND name = 'x_project_type'")
    row = cr.fetchone()
    if row:
        field_id = row[0]
        cr.execute("SELECT id FROM ir_model_fields_selection WHERE field_id = %s AND value = 'technical'", (field_id,))
        sel = cr.fetchone()
        if not sel:
            name_json = json.dumps({'en_US': 'Technical Project'})
            cr.execute("""
                INSERT INTO ir_model_fields_selection (field_id, value, name, sequence)
                VALUES (%s, 'technical', %s::jsonb, 2)
                RETURNING id
            """, (field_id, name_json))
            sel_id = cr.fetchone()[0]
            cr.execute("""
                INSERT INTO ir_model_data (name, module, model, res_id, noupdate)
                VALUES ('selection__project_project__x_project_type__technical', 'project_dashboard_v19c', 'ir.model.fields.selection', %s, false)
                ON CONFLICT (module, name) DO UPDATE SET res_id = EXCLUDED.res_id
            """, (sel_id,))
