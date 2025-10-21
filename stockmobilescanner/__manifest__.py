{
    "name": "Stock Mobile Scanner",
    "version": "19.0.1.0.0",
    "summary": "Simple mobile camera scanner UI for basic warehouse operations (receive/pick/pack/delivery)",
    "category": "Inventory/Barcode",
    "author": "Ahmad Heriyanto",
    "license": "LGPL-3",
    "website": "",
    "depends": ["base", "stock", "product", "web"],
    "data": [
        "views/stock_mobile_views.xml",
        "security/ir.model.access.csv"
    ],
    "assets": {
        "web.assets_frontend": [
            # We include static JS/CSS via template <script> tag; keeping simple
        ]
    },
    "installable": True,
    "application": False
}