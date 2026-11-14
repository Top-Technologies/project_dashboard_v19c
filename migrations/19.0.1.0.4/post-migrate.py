from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    projects = env['project.project'].search([
        ('x_project_type', '=', 'internal'),
    ])
    projects._ensure_internal_sdlc_stages()
