from odoo import models, fields, api
from datetime import datetime


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_is_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_x_is_overdue',
        store=True,
    )

    @api.depends('date_deadline', 'stage_id', 'stage_id.name')
    def _compute_x_is_overdue(self):
        now = datetime.now()
        for task in self:
            if (
                task.date_deadline
                and task.date_deadline < now
                and task.stage_id.name not in ('Done', 'Cancelled')
            ):
                task.x_is_overdue = True
            else:
                task.x_is_overdue = False
