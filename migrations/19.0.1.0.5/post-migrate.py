from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['project.project'].search([
        ('x_project_type', '=', 'internal'),
    ])._ensure_internal_sdlc_stages()
