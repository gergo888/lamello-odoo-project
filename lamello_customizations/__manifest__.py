{
    'name': "lamello_customizations",
    'summary': "Lamello customizations",
    'description': """
        Sales, Manufacturing and EDI customizations for Lamello.
    """,
    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',
    'depends': ['base', 'product', 'sale', 'mrp', 'l10n_hu_edi',],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/mrp_component_group_data.xml',
        'report/report_delivery_document_inherited.xml',
        'report/custom_invoice_report.xml',
        'report/report_component_template.xml',
        'report/report_component_template_demand.xml',
        'report/report_picking_template.xml',
        'report/report_picking_template_demand.xml',
        'report/lamello_report_views.xml',
        'report/mrp_report.xml',
        # 'report/report_lamello_stockpicking_operations.xml',
        'report/report_lamello_deliveryslip.xml',
        'views/views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lamello_customizations/static/src/scss/*',
            'lamello_customizations/static/src/js/*',
        ],
    }
}

