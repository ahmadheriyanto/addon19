from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.modules import get_module_path
import os, os.path
from datetime import datetime
import base64
import xlrd
import math

class ImportReceiptLine(models.TransientModel):
    _name = 'stock.picking.import.receipt.fromdoc'
    _description = 'import xls file into stock picking line from document'

    upload_file = fields.Binary(string="Lookup Excel File")
    
    def import_format_excel(self):
        # ======================================= EXCEL FORMAT ========================================
        #   PRODUCT CODE    QTY     UOM     BATCH	EXPIRED	    PLS NUMBER	    SOURCE	    DESTINATION
        # =============================================================================================

        #active_ids = self.ids
        #raise UserError(_('self._context.active_id = %s' % self.env.context["active_id"]))
        stock_picking = self.env['stock.picking'].search([('id','=',self.env.context["active_id"])])

        if not stock_picking.partner_id.id:
            raise UserError(_('Please specify Partner in document %s' % stock_picking.name))

        if not stock_picking.picking_type_id.id:
            raise UserError(_('Please specify Operation Type in document %s' % stock_picking.name))

        if not stock_picking.state == 'draft':
            raise UserError(_('Document %s must has a state = Draft, current state is %s' % (stock_picking.name,stock_picking.state)))

        if not self.upload_file:
            raise UserError(_('Lookup xls excel file before upload'))
        mpath = get_module_path('fulfillment')
        out_file_name = 'inbound.xls'
        out_file = mpath + _('/tmp/' + out_file_name)
        #delete file if exist
        if os.path.exists(out_file):
            os.remove(out_file)
        data = base64.b64decode(self.upload_file)
        with open(out_file,'wb') as file:
            file.write(data) 
        xl_workbook = xlrd.open_workbook(file.name)
        sheet_names = xl_workbook.sheet_names()
        sheetname = 'Sheet1'
        if not (sheetname in sheet_names):
            raise UserError(_('Worksheet with name "%s" does not exist' % sheetname))
        xl_sheet = xl_workbook.sheet_by_name(sheetname)
        #Number of Columns
        num_cols = xl_sheet.ncols
        #header
        headers = []
        for col_idx in range(0, num_cols):
            cell_obj = xl_sheet.cell(0, col_idx)
            headers.append(cell_obj.value)
        import_data = []
        for row_idx in range(1, xl_sheet.nrows):
            row_dict = {}
            for col_idx in range(0, num_cols):
                cell_obj = xl_sheet.cell(row_idx,col_idx)
                row_dict[headers[col_idx]] = cell_obj.value
            import_data.append(row_dict)
        
        # Prepare context for create (so default_get can pick defaults if used)
        ctx = dict(self.sudo().env.context or {})
        # Prevent stock.move merge so each incoming line stays separate
        ctx['no_merge'] = True

        if import_data:
            for row in import_data:
                #Check master product
                product_no = row['PRODUCT CODE']
                if isinstance(product_no,int) or isinstance(product_no,float):
                    fractional, whole = math.modf(product_no)
                    if fractional == 0:
                        product_no = str(int(product_no))
                    else:
                        product_no = str(product_no)

                check_product = self.env['product.product'].search([('default_code','=',product_no)])
                if not check_product:
                    raise UserError(_('Product %s does not exist in master data' % product_no))
                else:
                    check_product = check_product[0]
                #Check master UoM
                check_uom = self.env['uom.uom'].search([('name','=',row['UOM'])])
                if not check_uom:
                    raise UserError(_('UoM %s does not exist in master data' % row['UOM']))
                else:
                    check_uom = check_uom[0]
                #                   0                   1                2               3             4             5                    6     
                #rowdata = [check_product.id,row['PRODUCT CODE'],row['PO NUMBER'],check_uom.id,row['UOM'],row['BATCH'],row['EXPIRED'],row['QTY']
                
                #mulai input data
                #Check Stock.lot
                #raise UserError(_('test: ijno = %s, Best before date = %s ' % (ijno,datetime(*xlrd.xldate_as_tuple(row['Best before date'], 0)))))
                batchno = row['BATCH']
                if isinstance(batchno,int) or isinstance(batchno,float):
                    fractional, whole = math.modf(batchno)
                    if fractional == 0:
                        batchno = str(int(batchno))
                    else:
                        batchno = str(batchno)

                check_lot = self.env['stock.lot'].search([('name','=',batchno),('product_id','=',check_product.id)])
                if not check_lot:
                    check_lot = self.env['stock.lot'].create({
                            'name': batchno,
                            'product_id': check_product.id,
                            'ref': batchno,
                            'use_date': datetime(*xlrd.xldate_as_tuple(row['EXPIRED'], 0))
                            })
                else:
                    check_lot = check_lot[0]
                
                move_line = {
                    'picking_id': stock_picking.id,
                    'description_picking':f'{check_product.name} LOT: {check_lot.name}',
                    'sequence':10,
                    'company_id':stock_picking.company_id.id,
                    'product_id': check_product.id,
                    'product_uom': check_uom.id,
                    'product_uom_qty': row['QTY'],
                    # 'suggest_lot_id': check_lot.id,
                    # 'packing_list_city': row['City'],
                }    

                if check_lot:
                    move_line['lot_ids'] = [(6, 0, check_lot.ids)]            

                if not (row['PLS NUMBER'] == ''):
                    move_line.update({
                        'origin': row['PLS NUMBER'],
                    })

                if not (row['SOURCE'] == ''):
                    loc_obj = []
                    source_loc = row['SOURCE']
                    loc_obj = self.env['stock.location'].search([('complete_name', '=', _('%s' % source_loc)),])
                    if not loc_obj:
                        raise UserError(_('Invalid source location %s' % source_loc))
                    move_line.update({
                        'location_id': loc_obj[0].id,
                    })
                else:
                    move_line.update({
                        "location_id": stock_picking.location_id.id,
                    })
                    

                if not (row['DESTINATION'] == ''):
                    loc_obj = []
                    source_loc = row['DESTINATION']
                    loc_obj = self.env['stock.location'].search([('complete_name', '=', _('%s' % source_loc)),])
                    if not loc_obj:
                        raise UserError(_('Invalid source destination %s' % source_loc))
                    move_line.update({
                        'location_dest_id': loc_obj[0].id,
                    })
                else:
                    move_line.update({
                        "location_dest_id": stock_picking.location_dest_id.id,
                    })

                stock_move = stock_picking.move_ids.with_context(ctx).create(move_line)

                if not (row['PLS NUMBER'] == ''):
                    stock_picking.update({
                        'origin': row['PLS NUMBER'],
                    })

                if row['CUSTOMER NAME']:
                    stock_picking.update({
                        'principal_customer_name': row['CUSTOMER NAME'],
                    })

                if row['CUSTOMER ADDRESS']:
                    stock_picking.update({
                        'principal_customer_address': row['CUSTOMER ADDRESS'],
                    })
                
                if row['COURIER']:
                    company = self.env.company.sudo()
                    transporter_cat = company.fulfillment_transporter_category_id
                    Partner = self.env['res.partner'].sudo()
                    partner = Partner.search([('category_id', 'in', [transporter_cat.id]), ('name', 'ilike', row['COURIER'])], limit=1)
                    if partner:
                        stock_picking.update({
                            'principal_courier_id': partner.id,
                        })


                #raise UserError(_('%s' % stock_move))