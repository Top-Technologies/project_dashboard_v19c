from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    internal_projects = env['project.project'].search([
        ('x_project_type', '=', 'internal'),
    ])
    internal_projects._ensure_internal_sdlc_stages()

    technical_projects = env['project.project'].search([
        ('x_project_type', '=', 'technical'),
    ])
    technical_projects._ensure_technical_sdlc_stages()
