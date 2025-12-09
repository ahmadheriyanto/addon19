#DEV-010
import xlsxwriter
import base64
from odoo import fields, models, api
from io import BytesIO
from datetime import datetime
from pytz import timezone
import pytz
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class MsReportStock(models.TransientModel):
    _name = "ms.report.stock.putaway"
    _description = "Putaway Report.xlsx"
    
    @api.model
    def get_default_date_model(self):
        return pytz.UTC.localize(datetime.now()).astimezone(timezone(self.env.user.tz or 'UTC'))
    
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)
    product_ids = fields.Many2many('product.product', 'ms_report_stock_putaway_product_rel', 'ms_report_stock_putaway_id',
        'product_id', 'Products')
    categ_ids = fields.Many2many('product.category', 'ms_report_stock_putaway_categ_rel', 'ms_report_stock_putaway_id',
        'categ_id', 'Categories')
    #location_ids = fields.Many2many('stock.location', 'ms_report_stock_inbound_location_rel', 'ms_report_stock_inbound_id', 'location_id', 'Locations')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    #show_detail = fields.Boolean(string='Show Detail')
    template_loc = fields.Many2one('stock.location',string = 'Location')

    def print_excel_report(self):
        data = self.read()[0]
        product_ids = data['product_ids']
        categ_ids = data['categ_ids']
        #location_ids = data['location_ids']
        lang = (self.env.user.lang or 'en_US')
        
        # Get Filter Name
        product_filter_name = []
        if product_ids:
            product_filter_name = self.env['product.product'].search([('id','in',product_ids)])
            product_filter_name = [product.name for product in product_filter_name]
        categ_filter_name = []
        if categ_ids:
            categ_filter_name = self.env['product.category'].search([('id','in',categ_ids)])
            categ_filter_name = [cat.name for cat in categ_filter_name]
        date_filter_name = ''
        if self.date_start and (not self.date_end):
            date_filter_name = 'From %s' % (self.date_start)
        if (not self.date_start) and self.date_end:
            date_filter_name = 'Until %s' % (self.date_end)
        if self.date_start and self.date_end:
            date_filter_name = 'From %s Until %s' % (self.date_start,self.date_end)

        # Manage Product ids
        product_ids2 = product_ids

        if categ_ids :
            product_ids = self.env['product.product'].search([('categ_id','in',categ_ids)])
            product_ids = [prod.id for prod in product_ids]
        
        if product_ids2:
            product_ids += product_ids2

        where_product_ids = " 1=1 "
        if product_ids :
            where_product_ids = " sml.product_id in %s"%str(tuple(product_ids)).replace(',)', ')')

        if categ_ids and (not product_ids):
            where_product_ids = " 1=2 "
        
        # Manage Location ids
        where_putaway_picking_type_ids = " 1=1 "
        putaway_picking_type = self.env['stock.picking.type'].search([('code','in',['incoming','internal'])])
        putaway_picking_type_ids = [picking_type.id for picking_type in putaway_picking_type]
        if putaway_picking_type_ids:
            where_putaway_picking_type_ids = " sp.picking_type_id in %s" % str(tuple(putaway_picking_type_ids)).replace(',)', ')')

        #raise UserError('TEST ERROR, where_putaway_picking_type_ids = %s' % where_putaway_picking_type_ids)

        where_source_location_ids = " 1=1 "
        source_picking_type = self.env['stock.picking.type'].search([('code','=','incoming')])
        source_picking_type_default_location_ids = [picking_type.default_location_dest_id.id for picking_type in source_picking_type]
        if source_picking_type_default_location_ids:
            where_source_location_ids = " sml.location_id in %s" % str(tuple(source_picking_type_default_location_ids)).replace(',)', ')')

        # Manage Date Filter
        where_date_filter = " 1=1 "
        if self.date_start and (not self.date_end):
            where_date_filter = ' sml.date::timestamp::date>=\'%s\' ' % (self.date_start)
        if (not self.date_start) and self.date_end:
            where_date_filter = ' sml.date::timestamp::date<=\'%s\' ' % (self.date_end)
        if self.date_start and self.date_end:
            where_date_filter = ' sml.date::timestamp::date>=\'%s\' and sml.date::timestamp::date<=\'%s\' ' % (self.date_start,self.date_end)

        # Manage Location template: BY / DC
        where_loc_template = " (1 = 1) "
        if self.template_loc:
            where_loc_template = f" dest_loc.complete_name like '%{self.template_loc.name}%' "
        
        datetime_string = self.get_default_date_model().strftime("%Y-%m-%d %H:%M:%S")
        date_string = self.get_default_date_model().strftime("%Y-%m-%d")
        
        report_name = 'Putaway Report'
        
        filename = '%s %s'%(report_name,date_string)
        
        columns = []
        columns = [
                ('No', 5, 'no', 'no'),
                ('Date', 20, 'datetime', 'char'),
                ('PO Number', 30, 'char', 'char'),
                ('Source Location', 20, 'char_loc', 'char'),
                ('Product Code', 30, 'char', 'char'),
                ('Product Name', 80, 'char', 'char'),
                ('Partner Type', 3, 'char', 'char'),
                ('Batch Number', 30, 'char', 'char'),
                ('Qty', 20, 'number', 'number'),
                ('Exp. Date', 20, 'datetime', 'char'),
                ('Destination Location', 20, 'char_loc', 'char'),
                ('Product Volume (CBM)', 30, 'float', 'float'),
                ('Product Weight (KGS)', 30, 'number', 'number'),
                ('Document No.', 30, 'char', 'char')
            ]
            
        datetime_format = '%d %B %Y' #'%Y-%m-%d %H:%M:%S'
        utc = datetime.now().strftime(datetime_format)
        utc = datetime.strptime(utc, datetime_format)
        tz = self.get_default_date_model().strftime(datetime_format)
        tz = datetime.strptime(tz, datetime_format)
        duration = tz - utc
        hours = duration.seconds / 60 / 60
        if hours > 1 or hours < 1 :
            hours = str(hours) + ' hours'
        else :
            hours = str(hours) + ' hour'
        
        query = f"""   
                    select sml.date::timestamp::date as trans_date,
                        sp.origin as po_no,
                        source_loc.complete_name as source_loc,
                        prod.default_code as product_code,
                        pt.name->>'{lang}' as product_name,
                        sp.partner_type as partner_type,
                        lot.name as batch_no,
                        sml.quantity as qty,

                        lot.use_date::timestamp::date as exp_date,
                        
                        dest_loc.complete_name as destination_loc,
                        prod.volume * sml.quantity as volume,
                        prod.weight * sml.quantity as weight,
                        sp.name,
                        COALESCE(sml.move_id,0) as sml_move_id 
                    from 
                        stock_move_line sml 
                    inner join
                        stock_lot lot on sml.lot_id = lot.id
                    left join 
                        stock_picking sp on sml.picking_id = sp.id
                    left join
                        stock_location source_loc on sml.location_id = source_loc.id 
                    left join
                        stock_location dest_loc on sml.location_dest_id = dest_loc.id 
                    left join 
                        product_product prod on prod.id=sml.product_id
                    inner join
                        product_template pt on prod.product_tmpl_id = pt.id
                    left join 
                        stock_scrap scrap on scrap.picking_id = sp.id
                    where sml.state='done' and %s and %s and scrap.id IS NULL and %s and %s and %s
            """            
        
        retur_query = "select sml.date::timestamp::date as trans_date,"
        retur_query += " sp_origin.origin as po_no,"
        retur_query += " source_loc.complete_name as source_loc,"
        retur_query += " prod.default_code as product_code,"
        retur_query += f" pt.name->>'{lang}' as product_name,"
        retur_query += " sp_origin.partner_type as partner_type,"
        retur_query += " lot.name as batch_no,"
        retur_query += " sml.quantity as qty,"

        retur_query += " lot.use_date::timestamp::date as exp_date,"

        retur_query += " dest_loc.complete_name as destination_loc,"
        retur_query += " prod.volume * sml.quantity as volume,"
        retur_query += " prod.weight * sml.quantity as weight,"
        retur_query += " CONCAT(sp.name, ' - ', sp.origin) as sp_name,"
        retur_query += " COALESCE(sml.move_id,0) as sml_move_id "
        retur_query += " from "
        retur_query += " stock_move_line sml "
        retur_query += " inner join"
        retur_query += " stock_lot lot on sml.lot_id = lot.id"
        retur_query += " left join "
        retur_query += " stock_picking sp on sml.picking_id = sp.id"
        retur_query += " left join"
        retur_query += " stock_location source_loc on sml.location_id = source_loc.id "
        retur_query += " left join"
        retur_query += " stock_location dest_loc on sml.location_dest_id = dest_loc.id "
        retur_query += " left join "
        retur_query += " product_product prod on prod.id=sml.product_id"
        retur_query += " inner join"
        retur_query += " product_template pt on prod.product_tmpl_id = pt.id"
        retur_query += " left join "
        retur_query += " stock_scrap scrap on scrap.picking_id = sp.id"
        retur_query += " left join"
        retur_query += " stock_move sm on sm.id = sml.move_id"
        retur_query += " left join "
        retur_query += " stock_move sm_origin on sm_origin.id = sm.origin_returned_move_id"
        retur_query += " left join "
        retur_query += " stock_picking sp_origin on sp_origin.id = sm_origin.picking_id"
        retur_query += " where sml.state='done' and sml.id = %s"

        #raise UserError(query % (where_source_location_ids, where_putaway_picking_type_ids, where_date_filter, where_product_ids))

        self.env.cr.execute(query % (where_source_location_ids, where_putaway_picking_type_ids, where_date_filter, where_product_ids, where_loc_template)) #,self.env.user.company_id.id))
        result = self.env.cr.fetchall()
        if not result:
            raise UserError('Data for Putaway Report does not exist')
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)

        worksheet = workbook.add_worksheet(report_name)
        
        worksheet.merge_range('A2:K3', report_name, wbf['title_doc'])
        
        row = 4

        col = 0
        for column in columns :
            column_name = column[0]
            column_width = column[1]
            column_type = column[2]
            worksheet.set_column(col,col,column_width)
            worksheet.write(row, col, column_name, wbf['header_orange'])

            col += 1
        
        row += 1
        no = 1

        column_float_number = {}
        sml_retur_id = []

        for res in result :
            """
            if res[11]:
                refid = int(res[11])
                returs = self.env['stock.move'].search([('origin_returned_move_id','=',refid)])
                if returs:
                    for ret in returs:
                        stock_move_lines = self.env['stock.move.line'].search([('move_id','=',ret.id)])
                        if stock_move_lines:
                            for sml in stock_move_lines:
                                if sml.id:
                                    smlid = sml.id
                                    if not (smlid in sml_retur_id):                                        
                                        sml_retur_id.append(smlid)
            """
            col = 0
            for column in columns:
                column_name = column[0]
                column_width = column[1]
                column_type = column[2]
                if column_type == 'char' :
                    col_value = res[col-1] if res[col-1] else ''
                    wbf_value = wbf['content']
                elif column_type == 'char_loc':
                    col_value = self.get_location_name(res[col-1]) if res[col-1] else ''
                    wbf_value = wbf['content']
                elif column_type == 'no' :
                    col_value = no
                    wbf_value = wbf['content']
                elif column_type == 'datetime':
                    col_value = res[col - 1].strftime(datetime_format) if res[col - 1] else ''  #'%Y-%m-%d %H:%M:%S'
                    wbf_value = wbf['content']
                else :
                    col_value = res[col-1] if res[col-1] else 0
                    if column_type == 'float' :
                        wbf_value = wbf['content_float']
                    else : #number
                        wbf_value = wbf['content_number']
                    column_float_number[col] = column_float_number.get(col, 0) + col_value

                worksheet.write(row, col, col_value, wbf_value)

                col+=1
            
            # Write retur
            if res[13]:
                refid = int(res[13])
                returs = self.env['stock.move'].search([('origin_returned_move_id','=',refid)])
                if returs:
                    for ret in returs:
                        stock_move_lines = self.env['stock.move.line'].search([('move_id','=',ret.id)])
                        if stock_move_lines:
                            for sml in stock_move_lines:
                                if sml.id:
                                    rtv = retur_query % sml.id
                                    self.env.cr.execute(rtv) #,self.env.user.company_id.id))
                                    rtv_result = self.env.cr.fetchall()
                                    if rtv_result:
                                        for rtv_res in rtv_result :
                                            row += 1
                                            no+=1
                                            col = 0
                                            for column in columns:
                                                column_name = column[0]
                                                column_width = column[1]
                                                column_type = column[2]
                                                if column_type == 'char' :
                                                    col_value = rtv_res[col-1] if rtv_res[col-1] else ''
                                                    wbf_value = wbf['content']
                                                elif column_type == 'char_loc':
                                                    col_value = self.get_location_name(rtv_res[col-1]) if rtv_res[col-1] else ''
                                                    wbf_value = wbf['content']
                                                elif column_type == 'no' :
                                                    col_value = no
                                                    wbf_value = wbf['content']
                                                elif column_type == 'datetime':
                                                    col_value = rtv_res[col - 1].strftime(datetime_format) if rtv_res[col - 1] else ''  #'%Y-%m-%d %H:%M:%S'
                                                    wbf_value = wbf['content']
                                                else :
                                                    col_value = -1 * rtv_res[col-1] if rtv_res[col-1] else 0
                                                    if column_type == 'float' :
                                                        wbf_value = wbf['content_float']
                                                    else : #number
                                                        wbf_value = wbf['content_number']
                                                    column_float_number[col] = column_float_number.get(col, 0) + col_value

                                                worksheet.write(row, col, col_value, wbf_value)

                                                col+=1


            row+=1
            no+=1
        

        # Manage Retur
        # <<<>>>>

        worksheet.merge_range('A%s:B%s'%(row,row), 'Grand Total', wbf['total_orange'])
        for x in range(len(columns)) :
            if x in (0,1) :
                continue
            column_type = columns[x][3]
            if column_type == 'char' :
                worksheet.write(row-1,x, '', wbf['total_orange'])
            else :
                if column_type == 'float' :
                    wbf_value = wbf['total_float_orange']
                else : #number
                    wbf_value = wbf['total_number_orange']
                if x in column_float_number :
                    worksheet.write(row-1, x, column_float_number[x], wbf_value)
                else :
                    worksheet.write(row-1, x, 0, wbf_value)
        

        row+=2        
        worksheet.write('A%s'%row, 'Date Filter: %s'%date_filter_name, wbf['content_datetime']) #2021.12.11
        row+=1
        worksheet.write('A%s'%row, 'Product Filter: %s'%product_filter_name, wbf['content']) #2021.12.11
        row+=1
        worksheet.write('A%s'%row, 'Category Filter: %s'%categ_filter_name, wbf['content']) #2021.12.11
        row+=1
        worksheet.write('A%s'%row, 'Date %s (%s)'%(datetime_string,self.env.user.tz or 'UTC'), wbf['content_datetime'])
        workbook.close()
        out=base64.b64encode(fp.getvalue())
        self.write({'datas':out, 'datas_fname':filename})
        fp.close()
        filename += '%2Exlsx'

        #raise UserError('web/content/?model='+self._name+'&id='+str(self.id)+'&field=datas&download=true&filename='+filename)

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'web/content/?model='+self._name+'&id='+str(self.id)+'&field=datas&download=true&filename='+filename,
        }


    def get_location_name(self,complete_name):
        loca_qrcode = '';
        loc_list = complete_name.split('/')
        #raise UserError("loc_list = %s, len(loc_list) = %s" % (loc_list,len(loc_list)))
        if len(loc_list) == 0:
            loca_qrcode = complete_name
        else:
            n = 0
            for loc in loc_list:
                n += 1
                if n >= 2:
                    if loca_qrcode == '':
                        loca_qrcode = loc
                    else:
                        loca_qrcode += '/' + loc
        return loca_qrcode
    
    def add_workbook_format(self, workbook):
        #<<2021.12.11
        excel_param = self.env['ir.config_parameter'].search([('key','=','excel.font.name')])
        excel_font = excel_param.value
        if not excel_font:
            excel_font = 'Georgia'
            
        excel_param = self.env['ir.config_parameter'].search([('key','=','excel.float.format')])
        excel_float_format = excel_param.value
        if not excel_float_format:
            excel_float_format = '#,##0.00'
            
        excel_param = self.env['ir.config_parameter'].search([('key','=','excel.number.format')])
        excel_number_format = excel_param.value
        if not excel_number_format:
            excel_number_format = '#,##0'
        #>>
        
        colors = {
            'white_orange': '#FFFFDB',
            'orange': '#FFC300',
            'red': '#FF0000',
            'yellow': '#F6FA03',
        }

        wbf = {}
        wbf['header'] = workbook.add_format({'bold': 1,'align': 'center','bg_color': '#FFFFDB','font_color': '#000000', 'font_name': excel_font})
        wbf['header'].set_border()

        wbf['header_orange'] = workbook.add_format({'bold': 1,'align': 'center','bg_color': colors['orange'],'font_color': '#000000', 'font_name': excel_font})
        wbf['header_orange'].set_border()

        wbf['header_yellow'] = workbook.add_format({'bold': 1,'align': 'center','bg_color': colors['yellow'],'font_color': '#000000', 'font_name': excel_font})
        wbf['header_yellow'].set_border()
        
        wbf['header_no'] = workbook.add_format({'bold': 1,'align': 'center','bg_color': '#FFFFDB','font_color': '#000000', 'font_name': excel_font})
        wbf['header_no'].set_border()
        wbf['header_no'].set_align('vcenter')
                
        wbf['footer'] = workbook.add_format({'align':'left', 'font_name': excel_font})
        
        wbf['content_datetime'] = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'font_name': excel_font})
        wbf['content_datetime'].set_left()
        wbf['content_datetime'].set_right()
        
        wbf['content_date'] = workbook.add_format({'num_format': 'yyyy-mm-dd', 'font_name': excel_font})
        wbf['content_date'].set_left()
        wbf['content_date'].set_right() 
        
        wbf['title_doc'] = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 20,
            'font_name': excel_font,
        })
        
        wbf['company'] = workbook.add_format({'align': 'left', 'font_name': excel_font})
        wbf['company'].set_font_size(11)
        
        wbf['content'] = workbook.add_format()
        wbf['content'].set_left()
        wbf['content'].set_right() 
        wbf['content'].set_font_name(excel_font) #2021.12.11
        
        wbf['content_float'] = workbook.add_format({'align': 'right','num_format': excel_float_format, 'font_name': excel_font})
        wbf['content_float'].set_right() 
        wbf['content_float'].set_left()

        wbf['content_number'] = workbook.add_format({'align': 'right', 'num_format': excel_number_format, 'font_name': excel_font})
        wbf['content_number'].set_right() 
        wbf['content_number'].set_left() 
        
        wbf['content_percent'] = workbook.add_format({'align': 'right','num_format': '0.00%', 'font_name': excel_font})
        wbf['content_percent'].set_right() 
        wbf['content_percent'].set_left() 
                
        wbf['total_float'] = workbook.add_format({'bold':1, 'bg_color':colors['white_orange'], 'align':'right', 'num_format':excel_float_format, 'font_name': excel_font})
        wbf['total_float'].set_top()
        wbf['total_float'].set_bottom()            
        wbf['total_float'].set_left()
        wbf['total_float'].set_right()         
        
        wbf['total_number'] = workbook.add_format({'align':'right','bg_color': colors['white_orange'],'bold':1, 'num_format': excel_number_format, 'font_name': excel_font})
        wbf['total_number'].set_top()
        wbf['total_number'].set_bottom()            
        wbf['total_number'].set_left()
        wbf['total_number'].set_right()
        
        wbf['total'] = workbook.add_format({'bold':1, 'bg_color':colors['white_orange'], 'align':'center', 'font_name': excel_font})
        wbf['total'].set_left()
        wbf['total'].set_right()
        wbf['total'].set_top()
        wbf['total'].set_bottom()

        wbf['total_float_yellow'] = workbook.add_format({'bold':1, 'bg_color':colors['yellow'], 'align':'right', 'num_format':excel_float_format, 'font_name': excel_font})
        wbf['total_float_yellow'].set_top()
        wbf['total_float_yellow'].set_bottom()
        wbf['total_float_yellow'].set_left()
        wbf['total_float_yellow'].set_right()
        
        wbf['total_number_yellow'] = workbook.add_format({'align':'right','bg_color': colors['yellow'],'bold':1, 'num_format': excel_number_format, 'font_name': excel_font})
        wbf['total_number_yellow'].set_top()
        wbf['total_number_yellow'].set_bottom()
        wbf['total_number_yellow'].set_left()
        wbf['total_number_yellow'].set_right()
        
        wbf['total_yellow'] = workbook.add_format({'bold':1, 'bg_color':colors['yellow'], 'align':'center', 'font_name': excel_font})
        wbf['total_yellow'].set_left()
        wbf['total_yellow'].set_right()
        wbf['total_yellow'].set_top()
        wbf['total_yellow'].set_bottom()

        wbf['total_float_orange'] = workbook.add_format({'bold':1, 'bg_color':colors['orange'], 'align':'right', 'num_format':excel_float_format, 'font_name': excel_font})
        wbf['total_float_orange'].set_top()
        wbf['total_float_orange'].set_bottom()            
        wbf['total_float_orange'].set_left()
        wbf['total_float_orange'].set_right()         
        
        wbf['total_number_orange'] = workbook.add_format({'align':'right','bg_color': colors['orange'],'bold':1, 'num_format': excel_number_format, 'font_name': excel_font})
        wbf['total_number_orange'].set_top()
        wbf['total_number_orange'].set_bottom()            
        wbf['total_number_orange'].set_left()
        wbf['total_number_orange'].set_right()
        
        wbf['total_orange'] = workbook.add_format({'bold':1, 'bg_color':colors['orange'], 'align':'center', 'font_name': excel_font})
        wbf['total_orange'].set_left()
        wbf['total_orange'].set_right()
        wbf['total_orange'].set_top()
        wbf['total_orange'].set_bottom()
        
        wbf['header_detail_space'] = workbook.add_format({'font_name': excel_font})
        wbf['header_detail_space'].set_left()
        wbf['header_detail_space'].set_right()
        wbf['header_detail_space'].set_top()
        wbf['header_detail_space'].set_bottom()
        
        wbf['header_detail'] = workbook.add_format({'bg_color': '#E0FFC2', 'font_name': excel_font})
        wbf['header_detail'].set_left()
        wbf['header_detail'].set_right()
        wbf['header_detail'].set_top()
        wbf['header_detail'].set_bottom()
        
        return wbf, workbook
