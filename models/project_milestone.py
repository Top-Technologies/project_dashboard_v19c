from odoo import models, fields

class ProjectMilestone(models.Model):
    _inherit = 'project.milestone'

    x_phase_sequence = fields.Integer('Phase Order', default=10, help='Order in which phases appear on the dashboard')
