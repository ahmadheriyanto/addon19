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
    _name = "ms.report.stock.inbound"
    _description = "Stock Inbound Report.xlsx"
    
    @api.model
    def get_default_date_model(self):
        return pytz.UTC.localize(datetime.now()).astimezone(timezone(self.env.user.tz or 'UTC'))
        
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)
    product_ids = fields.Many2many('product.product', 'ms_report_stock_inbound_product_rel', 'ms_report_stock_inbound_id',
        'product_id', 'Products')
    categ_ids = fields.Many2many('product.category', 'ms_report_stock_inbound_categ_rel', 'ms_report_stock_inbound_id',
        'categ_id', 'Categories')
    location_ids = fields.Many2many('stock.location', 'ms_report_stock_inbound_location_rel', 'ms_report_stock_inbound_id',
        'location_id', 'Locations')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    show_detail = fields.Boolean(string='Show Detail')

    def print_excel_report(self):
        data = self.read()[0]
        product_ids = data['product_ids']
        categ_ids = data['categ_ids']
        location_ids = data['location_ids']
        # Use user's language for JSONB translatable fields
        lang = (self.env.user.lang or 'en_US') #.replace('_', '-')
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

        # DEV-014: Manage Location ids
        inbound_where_location_ids = " 1=1 "
        outbound_where_location_ids = " 1=1 "
        if location_ids :
            _loc_domain = []
            for _locid in location_ids:
                _loc = self.env['stock.location'].search([('id','=',_locid)])
                _loc_domain.append(('parent_path', '=like', _loc.parent_path + '%'))
            #_loc_domain.append(('usage', '=', 'transit'))
            _locs = self.env['stock.location'].search(_loc_domain)
            ids_location = [loc.id for loc in _locs]
            inbound_where_location_ids = " sml.location_dest_id in %s"%str(tuple(ids_location)).replace(',)', ')')
            outbound_where_location_ids = " sml.location_id in %s"%str(tuple(ids_location)).replace(',)', ')')
        #>>

        # Manage Date Filter
        where_date_filter = " 1=1 "
        if self.date_start and (not self.date_end):
            where_date_filter = ' sml.date::timestamp::date>=\'%s\' ' % (self.date_start)
        if (not self.date_start) and self.date_end:
            where_date_filter = ' sml.date::timestamp::date<=\'%s\' ' % (self.date_end)
        if self.date_start and self.date_end:
            where_date_filter = ' sml.date::timestamp::date>=\'%s\' and sml.date::timestamp::date<=\'%s\' ' % (self.date_start,self.date_end)
        
        datetime_string = self.get_default_date_model().strftime("%Y-%m-%d %H:%M:%S")
        date_string = self.get_default_date_model().strftime("%Y-%m-%d")
        
        if self.show_detail:
            report_name = 'Stock Inbound Report (Detail)'
        else:
            report_name = 'Stock Inbound Report'
        
        filename = '%s %s'%(report_name,date_string)
        
        columns = []
        if self.show_detail:
            columns = [
                ('No', 5, 'no', 'no'),
                ('Date', 20, 'datetime', 'char'),
                ('PO Number', 30, 'char', 'char'),
                ('Customer', 30, 'char', 'char'), #2023.11.28
                ('Partner Type', 3, 'char', 'char'), #2023.11.28
                ('Product Code', 30, 'char', 'char'),
                ('Product Name', 80, 'char', 'char'),
                ('Batch Number', 30, 'char', 'char'),
                ('Expired Date', 30, 'datetime', 'char'),
                ('Document No.', 30, 'char', 'char'),
                ('Qty', 20, 'number', 'number'), #2021.12.11
                ('Product Volume (CBM)', 30, 'float', 'float'),
                ('Product Weight (KGS)', 30, 'number', 'number'), #2021.12.11
                ('Transfer No.', 30, 'char', 'char'),
                ('Transfer Name', 30, 'char', 'char'),
                ('Transfer Type', 30, 'char', 'char'),
                ('Stock Move Line Id', 30, 'no', 'no'),
                ('Stock Move Id', 30, 'no', 'no')
            ]
        else:
            columns = [
                ('No', 5, 'no', 'no'),
                ('Date', 20, 'datetime', 'char'),
                ('PO Number', 30, 'char', 'char'),
                ('Customer', 30, 'char', 'char'), #2023.11.28
                ('Qty', 20, 'number', 'number'), #2021.12.11
                ('Total Product Volume (CBM)', 30, 'float', 'float'),
                ('Total Product Weight (KGS)', 30, 'number', 'number') #2021.12.11
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
        
        query = ""
        if self.show_detail:
            query = f"""
                select join_tbl.trans_date,
                    join_tbl.po_no,
                    join_tbl.res_name,
                    join_tbl.partner_type,
                    join_tbl.product_code,
                    join_tbl.product_name,
                    join_tbl.batch_no,
                    join_tbl.expired_date,
                    join_tbl.document_no,
                    join_tbl.qty,
                    join_tbl.volume,
                    join_tbl.weight,
                    join_tbl.transfer_no,
                    join_tbl.transfer_name,
                    join_tbl.transfer_type,
                    join_tbl.stock_move_line_id,
                    join_tbl.stock_move_id                      
                from
                (   
                    select sml.date::timestamp::date as trans_date,
                        sp.origin as po_no,
                        res.name as res_name,
                        prod.default_code as product_code,
                        pt.name->>'{lang}' as product_name,
                        lot.name as batch_no,
                        lot.use_date::timestamp::date as expired_date,
                        sp.name as document_no,
                        sml.quantity as qty,
                        prod.volume * sml.quantity as volume,
                        prod.weight * sml.quantity as weight,
                        sp.name as transfer_no,
                        spt.name->>'{lang}' as transfer_name,
                        spt.code as transfer_type,
                        sml.id as stock_move_line_id,
                        sml.move_id as stock_move_id,
                        sp.partner_type as partner_type  
                    from 
                        stock_move_line sml 
                    inner join
                        stock_lot lot on sml.lot_id = lot.id
                    left join
                        stock_move sm on sml.move_id = sm.id
                    left join 
                        stock_picking sp on sml.picking_id = sp.id 
                    left join 
                        res_partner res on res.id = sp.partner_id
                    left join 
                        product_product prod on prod.id=sml.product_id
                    inner join
                        product_template pt on prod.product_tmpl_id = pt.id
                    left join
                        stock_picking_type spt on spt.id = sp.picking_type_id
                    left join 
                        stock_scrap scrap on scrap.picking_id = sp.id
                    where COALESCE(sm.origin_returned_move_id,0) = 0 and sml.state='done' and spt.code='incoming' and scrap.id IS NULL and %s and %s and %s 
                    
                    UNION ALL
                    
                    select sml.date::timestamp::date as trans_date,
                        sp.origin as po_no,
                        res.name as res_name,
                        prod.default_code as product_code,
                        pt.name->>'{lang}' as product_name,
                        lot.name as batch_no,
                        lot.use_date::timestamp::date as expired_date,
                        sp.name as document_no,
                        -1 * sml.quantity as qty,
                        -1 * prod.volume * sml.quantity as volume,
                        -1 * prod.weight * sml.quantity as weight,
                        sp.name as transfer_no,
                        spt.name->>'{lang}' as transfer_name,
                        spt.code as transfer_type,
                        sml.id as stock_move_line_id,
                        sml.move_id as stock_move_id,
                        sp.partner_type as partner_type  
                    from 
                        stock_move sm 
                    inner join 
                        stock_move_line sml on sm.id = sml.move_id  
                    inner join
                        stock_lot lot on sml.lot_id = lot.id 
                    left join 
                        stock_picking sp on sml.picking_id = sp.id 
                    left join 
                        res_partner res on res.id = sp.partner_id
                    left join 
                        product_product prod on prod.id=sml.product_id 
                    inner join
                        product_template pt on prod.product_tmpl_id = pt.id 
                    left join
                        stock_picking_type spt on spt.id = sp.picking_type_id 
                    where COALESCE(sm.origin_returned_move_id,0) <> 0 and sml.state='done' and spt.code='outgoing' and %s and %s and %s 
                    
                ) as join_tbl
                order by join_tbl.trans_date,join_tbl.po_no                        
            """           
        else:
            query = f"""
                select join_tbl.trans_date,
                    join_tbl.po_no,
                    join_tbl.res_name,
                    sum(join_tbl.qty) as qty,
                    sum(join_tbl.volume) as volume,
                    sum(join_tbl.weight) as weight 
                from 
                (                     
                    select sml.date::timestamp::date as trans_date,
                        sp.origin as po_no,
                        res.name as res_name,
                        sml.quantity as qty,
                        prod.volume * sml.quantity as volume,
                        prod.weight * sml.quantity as weight 
                    from 
                        stock_move_line sml 
                    inner join
                        stock_lot lot on sml.lot_id = lot.id
                    left join
                        stock_move sm on sml.move_id = sm.id
                    left join 
                        stock_picking sp on sml.picking_id = sp.id
                    left join 
                        res_partner res on res.id = sp.partner_id 
                    left join 
                        product_product prod on prod.id=sml.product_id
                    inner join
                        product_template pt on prod.product_tmpl_id = pt.id
                    left join
                        stock_picking_type spt on spt.id = sp.picking_type_id
                    left join 
                        stock_scrap scrap on scrap.picking_id = sp.id 
                    where COALESCE(sm.origin_returned_move_id,0) = 0 and sml.state='done' and spt.code='incoming' and scrap.id IS NULL and %s and %s and %s 
                    
                    UNION ALL
                    
                    select sml.date::timestamp::date as trans_date,
                        sp.origin as po_no,
                        res.name as res_name,
                        -1 * sml.quantity as qty,
                        -1 * prod.volume * sml.quantity as volume,
                        -1 * prod.weight * sml.quantity as weight 
                    from 
                        stock_move sm 
                    inner join 
                        stock_move_line sml on sm.id = sml.move_id  
                    inner join
                        stock_lot lot on sml.lot_id = lot.id 
                    left join 
                        stock_picking sp on sml.picking_id = sp.id
                    left join 
                        res_partner res on res.id = sp.partner_id 
                    left join 
                        product_product prod on prod.id=sml.product_id 
                    inner join
                        product_template pt on prod.product_tmpl_id = pt.id 
                    left join
                        stock_picking_type spt on spt.id = sp.picking_type_id 
                    where COALESCE(sm.origin_returned_move_id,0) <> 0 and sml.state='done' and spt.code='outgoing' and %s and %s and %s 
                    
                ) as join_tbl 
                group by join_tbl.trans_date,join_tbl.po_no,join_tbl.res_name;
            """
        
        #raise UserError(query % (where_date_filter,where_product_ids,self.env.user.company_id.id))

        self.env.cr.execute(query % (where_date_filter,where_product_ids,inbound_where_location_ids, where_date_filter,where_product_ids,outbound_where_location_ids)) #,self.env.user.company_id.id)) #DEV-014: add location filter
        result = self.env.cr.fetchall() #self._cr.fetchall()
        if not result:
            raise UserError('Data for Stock Inbound Report does not exist')
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)

        worksheet = workbook.add_worksheet(report_name)
        
        if self.show_detail:
            worksheet.merge_range('A2:Q3', report_name, wbf['title_doc']) #2023.11.28
        else:
            worksheet.merge_range('A2:G3', report_name, wbf['title_doc']) #2023.11.28
        
        row = 5

        col = 0
        for column in columns :
            column_name = column[0]
            column_width = column[1]
            column_type = column[2]
            worksheet.set_column(col,col,column_width)
            worksheet.write(row-1, col, column_name, wbf['header_orange'])

            col += 1
        
        row += 1
        row1 = row
        no = 1

        column_float_number = {}
        for res in result :
            #print("\n res",res)
            col = 0
            for column in columns:
                column_name = column[0]
                column_width = column[1]
                column_type = column[2]
                if column_type == 'char' :
                    col_value = res[col-1] if res[col-1] else ''
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

                try:
                    worksheet.write(row-1, col, col_value, wbf_value)
                except Exception as e:
                    print(f'{e} , col_value={col_value}, row={row}, col={col}')                

                col+=1
            
            row+=1
            no+=1
        
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
