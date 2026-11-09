from odoo import models, api
from odoo.exceptions import UserError

# Names reserved for the 4 fixed stages defined in
# data/project_task_type_data.xml. A second record with one of these
# names (created e.g. via the Kanban "add a column" button) is what
# causes the duplicate-stages bug, since project_project.create() and
# any other lookup-by-name logic would then match every record sharing
# that name.
RESERVED_STAGE_NAMES = ('New', 'In Progress', 'Done', 'Cancelled')


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('install_mode'):
            if not self.env.user.has_group('base.group_system'):
                raise UserError(
                    "Task stages are managed by the system administrator. "
                    "You cannot create custom stages."
                )

        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('install_mode') and not self.env.user.has_group('base.group_system'):
            raise UserError(
                "Task stages are managed by the system administrator. "
                "You cannot modify stages."
            )
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('install_mode') and not self.env.user.has_group('base.group_system'):
            raise UserError(
                "Task stages are managed by the system administrator. "
                "You cannot delete stages."
            )
        return super().unlink()