import xlsxwriter
import base64
from odoo import fields, models, api
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
import pytz
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class MsReportStock(models.TransientModel):
    _name = "ms.report.stock"
    _description = "Stock Report.xlsx"
    
    @api.model
    def get_default_date_model(self):
        return pytz.UTC.localize(datetime.now()).astimezone(timezone(self.env.user.tz or 'UTC'))
    
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)
    product_ids = fields.Many2many('product.product', 'ms_report_stock_product_rel', 'ms_report_stock_id',
        'product_id', 'Products')
    categ_ids = fields.Many2many('product.category', 'ms_report_stock_categ_rel', 'ms_report_stock_id',
        'categ_id', 'Categories')
    location_ids = fields.Many2many('stock.location', 'ms_report_stock_location_rel', 'ms_report_stock_id',
        'location_id', 'Locations')
    lot_ids = fields.Many2many('stock.lot', 'ms_report_stock_lot_rel', 'ms_report_stock_id',
        'lot_id', 'Batches')
    
    #<<DEV-002
    expired_on = fields.Selection([
                                    ('nofilter', 'None'),
                                    ('next3months', 'Next 3 Months'),
                                    ('next6months', 'Next 6 Months'),
                                    ('next9months', 'Next 9 Months'),
                                    ('next12months', 'Next 12 Months')
                                ], string='Expired on', default='nofilter')
    
    expired_until = fields.Char(compute='_compute_expired_date_period', string="Expired until", readonly=True)
    #>>
    room = fields.Selection([
        ('all', 'All Rooms'),
        ('dry', 'Dry Room'),
        ('cool', 'Cool Room')        
        ], string='Room', default='all')
    
    #<<DEV-002
    @api.depends('expired_on')
    def _compute_expired_date_period(self):
        today = fields.Date.today()
        untilday = ''
        for mydata in self:
            if mydata.expired_on == 'next3months':
                untilday =  (today + relativedelta(months=3)).strftime('%m/%d/%Y')
            if mydata.expired_on == 'next6months':
                untilday = (today + relativedelta(months=6)).strftime('%m/%d/%Y')
            if mydata.expired_on == 'next9months':
                untilday = (today + relativedelta(months=9)).strftime('%m/%d/%Y')
            if mydata.expired_on == 'next12months':
                untilday = (today + relativedelta(months=12)).strftime('%m/%d/%Y')
                    
            mydata.expired_until = untilday
    #>>        
        
    def print_test(self):
        data = self.read()[0]
        product_ids = data['product_ids']
        categ_ids = data['categ_ids']
        location_ids = data['location_ids']
        
        if categ_ids :
            product_ids = self.env['product.product'].search([('categ_id','in',categ_ids)])
            product_ids = [prod.id for prod in product_ids]
        where_product_ids = " 1=1 "
        where_product_ids2 = " 1=1 "
        if product_ids :
            where_product_ids = " quant.product_id in %s"%str(tuple(product_ids)).replace(',)', ')')
            where_product_ids2 = " product_id in %s"%str(tuple(product_ids)).replace(',)', ')')

        location_ids2 = self.env['stock.location'].search(['|',('usage','=','internal'),('usage','=','transit')])
        ids_location = [loc.id for loc in location_ids2]
        where_location_ids = " quant.location_id in %s"%str(tuple(ids_location)).replace(',)', ')')
        if location_ids :
            where_location_ids = " quant.location_id in %s"%str(tuple(location_ids)).replace(',)', ')')
        
        date_string = self.get_default_date_model().strftime("%Y-%m-%d %H:%M:%S")
        report_name = 'Stock Report'
        filename = '%s %s'%(report_name,date_string)

        raise UserError(where_location_ids)

    def print_excel_report_from_portal(self,stockreport):
        #_logger.critical('****** >>>> C E K: <<<<< ***** | model name = %s' % (stockreport._name))
        #raise UserError('stockreport.categ_id.id = %s' % stockreport.categ_id.id)
        
        #<<#DEV-015
        context = self._context
        current_uid = context.get('uid')
        user = self.env['res.users'].browse(current_uid)
        #>>

        product_ids = []
        if stockreport.categ_id.id:
            product_ids = self.env['product.product'].search([('categ_id','=',stockreport.categ_id.id)])
            product_ids = [prod.id for prod in product_ids]
            
        if stockreport.product_id.id != 0:
            if not (stockreport.product_id.id in product_ids):
                raise UserError('selected product is not in category allowed')
            product_ids = []
            product_ids.append(stockreport.product_id.id)
            
        where_product_ids = " 1=2 "
        if len(product_ids) != 0 :
            where_product_ids = " quant.product_id in %s"%str(tuple(product_ids)).replace(',)', ')')    
        
        where_location_ids = " 1=1 "
        if stockreport.location_id.id != 0:
            where_location_ids = " quant.location_id = %s" % stockreport.location_id.id
        else:
            location_ids2 = self.env['stock.location'].search(['|',('usage','=','internal'),('usage','=','transit')])
            ids_location = [loc.id for loc in location_ids2]
            where_location_ids = " quant.location_id in %s" % str(tuple(ids_location)).replace(',)', ')')   
        
        self._print_excel_report(where_product_ids, where_location_ids, others_model = stockreport)
        
        
    def print_excel_report_from_current_model(self):
        data = self.read()[0]
        product_ids = data['product_ids']
        categ_ids = data['categ_ids']
        location_ids = data['location_ids']
        lot_ids = data['lot_ids']
            
        product_ids2 = product_ids
        
        if categ_ids :
            product_ids = self.env['product.product'].search([('categ_id','in',categ_ids)])
            product_ids = [prod.id for prod in product_ids]

        if product_ids2:
            product_ids += product_ids2
        
        # if lot_ids exist then all of above product id wil=l be replace
        if lot_ids:
            #_logger.critical('****** >>>> C E K: <<<<< ***** | lot_ids = %s' % (lot_ids))
            lot_recs = self.env['stock.lot'].search([('id','in',lot_ids)])
            #_logger.critical('****** >>>> C E K: <<<<< ***** | lot_recs = %s' % (lot_recs))
            product_ids = [lot.product_id.id for lot in lot_recs]
            #_logger.critical('****** >>>> C E K: <<<<< ***** | product_ids = %s' % (product_ids))
                
        where_product_ids = " 1=1 "
        if product_ids :
            if lot_ids:
                where_product_ids = " quant.product_id in %s and quant.lot_id in %s " % (str(tuple(product_ids)).replace(',)', ')'), str(tuple(lot_ids)).replace(',)', ')'))
            else:
                where_product_ids = " quant.product_id in %s"%str(tuple(product_ids)).replace(',)', ')')
        
        if categ_ids and (not product_ids):
            where_product_ids = " 1=2 "
            

        location_ids2 = self.env['stock.location'].search(['|',('usage','=','internal'),('usage','=','transit')])
        ids_location = [loc.id for loc in location_ids2]
        where_location_ids = " quant.location_id in %s"%str(tuple(ids_location)).replace(',)', ')')
        if location_ids :
            #<<DEV-014
            #OLD: where_location_ids = " quant.location_id in %s"%str(tuple(location_ids)).replace(',)', ')')
            #NEW:
            _loc_domain = []
            for _locid in location_ids:
                _loc = self.env['stock.location'].search([('id','=',_locid)])
                _loc_domain.append(('parent_path', '=like', _loc.parent_path + '%'))
            _locs = self.env['stock.location'].search(_loc_domain)
            ids_location = [loc.id for loc in _locs]
            where_location_ids = " quant.location_id in %s"%str(tuple(ids_location)).replace(',)', ')')
            #>>

        if self.room == 'cool':
            where_location_ids += " AND loc.x_studio_cool_room = true "
        elif self.room == 'dry':
            where_location_ids += " AND (loc.x_studio_cool_room = false or loc.x_studio_cool_room IS NULL) "

        self._print_excel_report(where_product_ids, where_location_ids)
        
        filename = self.datas_fname + '%2Exlsx'

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'web/content/?model='+self._name+'&id='+str(self.id)+'&field=datas&download=true&filename='+filename,
        }
        
    def _print_excel_report(self, where_product_ids, where_location_ids, others_model = None):
        datetime_string = self.get_default_date_model().strftime("%Y-%m-%d %H:%M:%S")
        date_string = self.get_default_date_model().strftime("%Y-%m-%d")
        report_name = 'Stock Report'
        filename = '%s %s'%(report_name,date_string)
        lang = (self.env.user.lang or 'en_US')
        
        columns = [
            ('No', 5, 'no', 'no'),
            ('Product No', 30, 'char', 'char'),
            ('Product Name', 30, 'char', 'char'),
            ('Product Category', 20, 'char', 'char'),
            ('Location', 30, 'char', 'char'),
            ('Room', 10, 'char', 'char'),
            ('Partner Type', 10, 'char', 'char'),
            ('Product Volume (CBM)', 20, 'float', 'float'),
            ('Product Weight (KGS)', 20, 'float', 'float'),
            ('Batch', 30, 'char', 'char'),
            ('Expired date', 20, 'datetime', 'char'),
            ('Incoming Date', 20, 'datetime', 'char'),
            ('Stock Age', 20, 'number', 'char'),
            ('Total Stock', 20, 'number', 'number'), #2021.12.11
            ('Available', 20, 'number', 'number'),   #2021.12.11
            ('Reserved', 20, 'number', 'number'),    #2021.12.11
            ('Product Volume Total (CBM)', 20, 'float', 'float'),
            ('Product Weight Total (KGS)', 20, 'number', 'number'), #2021.12.11
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
        
        # change : quant.in_date + interval '%s' as date_in,
        query = f"""
            SELECT TBL1.productno, TBL1.product, TBL1.prod_categ, TBL1.location, TBL1.room, TBL1.partner_type, prod2.volume, prod2.weight, TBL1.lotserial, LOT2.use_date + interval '%s' as expired_date, TBL1.date_in, TBL1.aging, TBL1.total_product, TBL1.stock, TBL1.reserved, TBL1.volume, TBL1.weight FROM (
                SELECT
                    quant.product_id as prodid, 
                    prod_tmpl.default_code as productno,
                    prod_tmpl.name->>'{lang}' as product, 
                    categ.name as prod_categ, 
                    substring(loc.complete_name from position('/' IN loc.complete_name)+1) as location,
                    CASE WHEN loc.x_studio_cool_room THEN 'cool' ELSE 'dry' END as room,
                    quant.partner_type as partner_type,
                    lot.name as lotserial,
                    lot.id as lotid,
                    quant.in_date + interval '%s' as date_in, 
                    date_part('days', now() - (quant.in_date + interval '%s')) as aging,
                    sum(quant.quantity) as total_product, 
                    sum(quant.quantity-quant.reserved_quantity) as stock, 
                    sum(quant.reserved_quantity) as reserved,
                    sum(quant.quantity * prod.volume) as volume, 
                    sum(quant.quantity * prod.weight) as weight 
                FROM 
                    stock_quant quant
                LEFT JOIN 
                    stock_location loc on loc.id=quant.location_id
                LEFT JOIN 
                    product_product prod on prod.id=quant.product_id
                LEFT JOIN 
                    product_template prod_tmpl on prod_tmpl.id=prod.product_tmpl_id
                LEFT JOIN 
                    product_category categ on categ.id=prod_tmpl.categ_id
                LEFt JOIN
                    stock_lot lot on lot.id = quant.lot_id
                WHERE 
                    %s and %s 
                GROUP BY 
                    prodid, productno, product, prod_categ, location, room, partner_type, date_in, lotserial, lotid
                ORDER BY 
                    date_in ) TBL1 
            LEFT JOIN
                stock_lot LOT2 on LOT2.id = TBL1.lotid
            LEFT JOIN
                product_product prod2 on prod2.id = TBL1.prodid
            WHERE TBL1.total_product <> 0
        """
        
        #<<DEV-002 - Manage Expired Date
        expired_text = ''
        untilday = fields.Date.today()        
        if self.expired_on == 'next3months':
            untilday =  untilday + relativedelta(months=3)
        if self.expired_on == 'next6months':
            untilday = untilday + relativedelta(months=6)
        if self.expired_on == 'next9months':
            untilday = untilday + relativedelta(months=9)
        if self.expired_on == 'next12months':
            untilday = untilday + relativedelta(months=12)
        if untilday != fields.Date.today():
            query = query + (" AND LOT2.use_date <= '%s'::date" % untilday.strftime('%Y-%m-%d'))    
            expired_text = (' (Expired until %s)' % untilday.strftime('%m/%d/%Y'))
        #>>
        
        #raise UserError('%s' % (query%(hours,hours,hours,where_product_ids,where_location_ids)))
        
        self.env.cr.execute(query%(hours,hours,hours,where_product_ids,where_location_ids))
        result = self.env.cr.fetchall()
        
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)

        worksheet = workbook.add_worksheet(report_name)
        
        #<<DEV-002
        if expired_text != '':
            worksheet.merge_range('A2:P3', report_name + expired_text, wbf['title_doc'])
        else:    
            worksheet.merge_range('A2:P3', report_name, wbf['title_doc'])
        #>>
        
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
                    col_value = res[col - 1].strftime(datetime_format) if res[col - 1] else ''
                    wbf_value = wbf['content']
                else :
                    col_value = res[col-1] if res[col-1] else 0
                    if column_type == 'float' :
                        wbf_value = wbf['content_float']
                    else : #number
                        wbf_value = wbf['content_number']
                    column_float_number[col] = column_float_number.get(col, 0) + col_value

                worksheet.write(row-1, col, col_value, wbf_value)

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
        
        worksheet.write('A%s'%(row+2), 'Date %s (%s)'%(datetime_string,self.env.user.tz or 'UTC'), wbf['content_datetime'])
        workbook.close()
        out=base64.b64encode(fp.getvalue())
        
        if others_model:
            others_model.write({'filedata':out})
        else:
            self.write({'datas':out, 'datas_fname':filename}) #2021.12.11
        
        fp.close()
        
        #filename += '%2Exlsx'
        #return {
        #    'type': 'ir.actions.act_url',
        #    'target': 'new',
        #    'url': 'web/content/?model='+self._name+'&id='+str(self.id)+'&field=datas&download=true&filename='+filename,
        #}

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