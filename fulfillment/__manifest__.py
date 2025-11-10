{
    'name': "fulfillment",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Ahmad Heriyanto",
    'website': "https://www.aplikasierp.online",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Inventory',
    'version': '0.1',
    'license': 'LGPL-3',
    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'product',
        'website',
        'stock',
        'uom',
    ],
    "assets": {
        "web.assets_backend": [            
        ],
    },    
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/remove_website_odoo_logo.xml',
        'views/product_category_views.xml',
        'views/incoming_staging_views.xml',
        'views/portal_api_key_templates.xml',
        'views/portal_api_key_shortcut.xml',
        'views/res_users_apikeys_inherit.xml',
        'views/partner_category_views.xml',
        'views/view_partner_form.xml',
        'views/view_picking_form.xml',
        'views/view_picking_list.xml',
        'views/stock_picking_type_kanban_custom.xml',
        'views/stock_picking_type_action_custom.xml',
        'views/stock_picking_type_menu_add.xml',        
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'external_dependencies': {
        'python': ['segno', 'qrcode', 'Pillow'],
    },    
    "application": True,
    "installable": True,
}

