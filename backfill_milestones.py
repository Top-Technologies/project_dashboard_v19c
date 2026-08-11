import sys

env = self.env
Project = env['project.project']
Milestone = env['project.milestone']

projects = Project.search([('x_project_type', '=', 'client')])
print(f"Found {len(projects)} client projects.")

default_milestones = [
    {'name': 'Preparation', 'x_phase_sequence': 10},
    {'name': 'Blueprint', 'x_phase_sequence': 20},
    {'name': 'Realization', 'x_phase_sequence': 30},
    {'name': 'Testing', 'x_phase_sequence': 40},
    {'name': 'Go-Live', 'x_phase_sequence': 50},
]

created = 0
for project in projects:
    if not Milestone.search_count([('project_id', '=', project.id)]):
        milestones_to_create = []
        for ms in default_milestones:
            new_ms = ms.copy()
            new_ms['project_id'] = project.id
            milestones_to_create.append(new_ms)
        Milestone.create(milestones_to_create)
        created += 1

print(f"Created default milestones for {created} projects.")
env.cr.commit()
