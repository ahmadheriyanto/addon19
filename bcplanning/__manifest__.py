{
    'name': "bcplanning",

    'summary': "Odoo integration with Business Central for BC Vendor portal",

    'description': """
        Odoo integration with Business Central for BC Vendor portal
    """,

    'author': "Ahmad Heriyanto",
    'website': "https://bc365optimizers.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Integration',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'web',
        'website',
    ],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/bc_planning_views.xml',
        # 'views/portal_projects.xml',
        'views/remove_website_odoo_logo.xml',
        'views/website_menu.xml',
        'views/partner_projects.xml',
        'views/partner_tasks.xml',
    ],
    'assets': {
        'web.assets_frontend': [            
            '/bcplanning/static/src/js/partner_project.js',
        ],
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    "application": True,
    "installable": True,
}

# '/bcplanning/static/src/js/projects_tabulator.js',

