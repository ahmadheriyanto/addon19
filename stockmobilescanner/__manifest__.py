{
    "name": "Stock Mobile Scanner",
    "version": "19.0.1.0.0",
    "summary": "Simple mobile camera scanner UI for basic warehouse operations (receive/pick/pack/delivery)",
    "category": "Inventory/Barcode",
    "author": "Ahmad Heriyanto",
    "license": "LGPL-3",
    "website": "",
    "depends": [
        "base",
        "stock",
        "product",
        "web",
        "website",
    ],
    "data": [
        "views/stock_mobile_views.xml",
        "views/hello_world_template.xml",
        "views/remove_website_odoo_logo.xml",
        "security/ir.model.access.csv",
    ],
    "assets": {
        "web.assets_frontend": [
            "stockmobilescanner/static/src/css/mobile_scanner.css",
            "stockmobilescanner/static/src/js/mobile_scanner.js"
        ],
        "website.assets_frontend": [
            "stockmobilescanner/static/src/css/mobile_scanner.css",
            "stockmobilescanner/static/src/js/mobile_scanner.js"
        ]
    },
    "installable": True,
    "application": False
}