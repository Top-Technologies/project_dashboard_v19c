from odoo import models, fields

class ProjectMilestone(models.Model):
    _inherit = 'project.milestone'
    _order = 'x_phase_sequence asc, deadline asc, id asc'

    x_phase_sequence = fields.Integer('Phase Order', default=10, help='Order in which phases appear on the dashboard')
