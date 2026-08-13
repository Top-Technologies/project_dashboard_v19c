from odoo import models, fields


class ProjectClientAction(models.Model):
    _name = 'project.client.action'
    _description = 'Client Pending Action'
    _order = 'is_done asc, date_due asc, create_date desc'

    name = fields.Char(string='Action / Deliverable', required=True)
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one('project.task', string='Task', ondelete='cascade', index=True)
    date_due = fields.Date(string='Due Date')
    is_done = fields.Boolean(string='Completed', default=False)
    status = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('approved', 'Approved / Done'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='pending',
        required=True,
    )
    assigned_partner_id = fields.Many2one('res.partner', string='Client Contact')
    notes = fields.Text(string='Notes / Feedback')
