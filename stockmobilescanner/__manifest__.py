{
    "name": "Stock Mobile Scanner",
    "version": "19.0.1.0.0",
    "summary": "Simple mobile camera scanner UI for basic warehouse operations (receive/pick/pack/delivery)",
    "category": "Inventory/Barcode",
    "author": "Ahmad Heriyanto",
    "license": "LGPL-3",
    "website": "",
    "depends": [
        'base',
        'stock',
        'product',
        'web',
        'website',
        'fulfillment',
    ],
    "data": [
        "views/stock_mobile_views.xml",
        "views/hello_world_template.xml",
        "security/ir.model.access.csv",
    ],
    "assets": {
        # JS is an odoo-module (uses /** @odoo-module **/) so it needs the odoo module loader.
        # Place the ES-module in web.assets_frontend so the loader is present.
        "web.assets_frontend": [
            "stockmobilescanner/static/src/js/mobile_scanner.js"
        ],
        # Keep CSS in website bundle so it only affects website pages
        "website.assets_frontend": [
            "stockmobilescanner/static/src/css/mobile_scanner.css"
        ]
    },
    "installable": True,
    "application": False
}