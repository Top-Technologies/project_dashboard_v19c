from odoo import models, fields,api


class ProjectRiskIssue(models.Model):
    _name = 'project.risk.issue'
    _description = 'Project Risk and Issue'
    _order = 'severity desc, create_date desc'

    name = fields.Char(string='Title / Description', required=True)
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one('project.task', string='Task', ondelete='cascade', index=True)
    type = fields.Selection(
        selection=[
            ('risk', 'Risk'),
            ('issue', 'Issue'),
        ],
        string='Type',
        default='issue',
        required=True,
    )
    severity = fields.Selection(
        selection=[
            ('high', 'High'),
            ('medium', 'Medium'),
            ('low', 'Low'),
        ],
        string='Severity',
        default='medium',
        required=True,
    )
    status = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('in_progress', 'In Progress'),
            ('mitigated', 'Mitigated'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='open',
        required=True,
    )
    assigned_user_id = fields.Many2one('res.users', string='Assigned To')
    mitigation_plan = fields.Text(string='Mitigation / Resolution Plan')
    target_date = fields.Date(string='Target Resolution Date')
    submitted_date = fields.Date(string='Submitted Date', default=fields.Date.context_today,required=True,)

    closed_date = fields.Date(string='Closed Date' )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('submitted_date'):
                vals['submitted_date'] = fields.Date.context_today(self)

            if vals.get('status') == 'closed' and not vals.get('closed_date'):
                vals['closed_date'] = fields.Date.context_today(self)

        return super().create(vals_list)

    def write(self, vals):
        if 'status' in vals:
            vals = dict(vals)

            if vals['status'] == 'closed':
                vals['closed_date'] = fields.Date.context_today(self)
            elif vals['status'] != 'closed':
                vals['closed_date'] = False

        return super().write(vals)
