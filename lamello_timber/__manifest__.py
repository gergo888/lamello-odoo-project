{
    'name': "lamello_timber",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
        Rönk és rakat feldolgozás adatainak nyilvántartása
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'purchase', 'purchase_stock'],

    # always loaded
    'data': [
        # 'security/lamello_security.xml',
        'security/ir.model.access.csv',        
        'data/stock_locations.xml',
        'data/sequences.xml',   
        'data/uom_data.xml',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}