from odoo import models, fields, api, _

class StockLocationCustom(models.Model):
    _inherit = 'stock.location'
    
    main_parent = fields.Boolean('Main Parent')
    
    def israck(self):
        # Internal Location/WH/A/001/1
        complete_name_check = self.complete_name.split('/')
        rtv = (len(complete_name_check) >= 4)
        return rtv

    