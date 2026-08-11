from . import models
from . import controllers

def post_init_hook(env):
    projects = env['project.project'].search([('x_project_type', '=', 'client')])
    Milestone = env['project.milestone']
    
    default_milestones = [
        {'name': 'Preparation', 'x_phase_sequence': 10},
        {'name': 'Blueprint', 'x_phase_sequence': 20},
        {'name': 'Realization', 'x_phase_sequence': 30},
        {'name': 'Testing', 'x_phase_sequence': 40},
        {'name': 'Go-Live', 'x_phase_sequence': 50},
    ]

    for project in projects:
        if not Milestone.search_count([('project_id', '=', project.id)]):
            milestones_to_create = []
            for ms in default_milestones:
                new_ms = ms.copy()
                new_ms['project_id'] = project.id
                milestones_to_create.append(new_ms)
            Milestone.create(milestones_to_create)
