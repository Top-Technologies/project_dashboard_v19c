from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    x_project_status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Project Status',
        default='new',
        required=True,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Inject the 4 fixed task stages into each vals dict BEFORE super().create()
        # so the new project already has type_ids set when the form first renders —
        # this prevents Odoo's "please add stages" prompt on the tasks kanban.
        fixed_stage_xmlids = [
            'project_dashboard_v19c.project_stage_new',
            'project_dashboard_v19c.project_stage_in_progress',
            'project_dashboard_v19c.project_stage_done',
            'project_dashboard_v19c.project_stage_cancelled',
        ]
        fixed_stage_ids = []
        for xmlid in fixed_stage_xmlids:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                fixed_stage_ids.append(stage.id)
        if fixed_stage_ids:
            stage_cmd = [(6, 0, fixed_stage_ids)]
            for vals in vals_list:
                if not vals.get('type_ids'):
                    vals['type_ids'] = stage_cmd
        return super().create(vals_list)

    def action_set_status_new(self):
        self.write({'x_project_status': 'new'})

    def action_set_status_in_progress(self):
        self.write({'x_project_status': 'in_progress'})

    def action_set_status_done(self):
        self.write({'x_project_status': 'done'})

    def action_set_status_cancelled(self):
        self.write({'x_project_status': 'cancelled'})