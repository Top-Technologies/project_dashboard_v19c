from odoo import models, fields, api
from datetime import datetime


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_is_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_x_is_overdue',
        store=True,
    )
    client_action_ids = fields.One2many(
        'project.client.action', 'task_id', string='Client Actions'
    )
    risk_issue_ids = fields.One2many(
        'project.risk.issue', 'task_id', string='Risks and Issues'
    )

    @api.depends('date_deadline', 'stage_id', 'stage_id.name', 'project_id.x_project_type')
    def _compute_x_is_overdue(self):
        now = datetime.now()
        for task in self:
            if (
                task.date_deadline
                and task.date_deadline < now
                and task.stage_id.name not in ('Done', 'Cancelled')
                and not (
                    task.project_id.x_project_type == 'internal' and task.stage_id.name == 'Done'
                )
                and not (
                    task.project_id.x_project_type == 'technical' and task.stage_id.name == 'Implemented'
                )
            ):
                task.x_is_overdue = True
            else:
                task.x_is_overdue = False

    def write(self, vals):
        res = super().write(vals)
        # Task stage/state changes refresh the parent project status for both
        # project types so the internal status chart reflects task progress.
        if 'stage_id' in vals or 'state' in vals:
            projects = self.mapped('project_id')
            for project in projects:
                project._sync_project_status()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        # After tasks are created, promote project from New → In Progress if needed
        projects = tasks.mapped('project_id')
        for project in projects:
            project._sync_project_status()
        return tasks

