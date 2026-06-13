import base64
from datetime import datetime, timedelta, date
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.orm.environments import Query
from odoo.tools import html2plaintext
from odoo.http import request
import re
import requests
import io
from lxml import etree


from logging import getLogger
_logger = getLogger(__name__)

# feature
# commit

class ProductFamily(models.Model):
    _name = 'lamello.productfamily'
    _description = 'Termékacslád'

    name = fields.Char(string='Család', required=True)
    alternative_name = fields.Char(string='Hazai név')
    product_category_id = fields.Many2one('product.category', string='Termék kategória')


class ProductCategory(models.Model):
    _inherit = 'product.category'

    product_family_ids = fields.One2many('lamello.productfamily', 'product_category_id', string='Termékcsalád')
    

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    invoice_name = fields.Char(string='Számlázási név', translate=True)
    component_code = fields.Char(string='Alkatrészkód')
    
    product_family_id = fields.Many2one('lamello.productfamily', string='Termékcsalád', compute='_compute_product_family', store=True)
    # product_family_id = fields.Many2one('lamello.productfamily', string='Termékcsalád')
    is_accessory = fields.Boolean(string="Tartozék-e", compute="_compute_is_accessory", store=True)
    parcel_qty = fields.Integer(string='Csomag db')
    old_pt_id = fields.Integer()

    product_codes = fields.Char(
        string="Beszállítói termékkódok",
        compute="_compute_product_codes",
    )

    dimensions = fields.Char(
        string='Méret',
        compute='_compute_template_dimensions',
    )

    @api.depends('product_variant_ids.dimensions', 'product_variant_count')
    def _compute_template_dimensions(self):
        for tmpl in self:
            if tmpl.product_variant_count == 1:
                tmpl.dimensions = tmpl.product_variant_ids.dimensions
            else:
                tmpl.dimensions = False

    @api.depends('seller_ids.product_code')
    def _compute_product_codes(self):
        for template in self:
            # Összegyűjtjük az összes egyedi beszállítói kódot, ami nem üres
            codes = template.seller_ids.mapped('product_code')
            valid_codes = [code for code in codes if code]
            template.product_codes = ", ".join(set(valid_codes))

    @api.depends('optional_product_ids')
    def _compute_is_accessory(self):
        for product in self:
            domain = [('optional_product_ids', 'in', product.id)]
            count = self.env['product.template'].search_count(domain)
            product.is_accessory = count > 0

    @api.depends('categ_id', 'categ_id.product_family_ids', 'categ_id.parent_id.product_family_ids')
    def _compute_product_family(self):
        for product in self:
            family = False
            if product.categ_id:
                # Először megnézzük a közvetlen kategóriát
                if product.categ_id.product_family_ids:
                    family = product.categ_id.product_family_ids[0]
                # Ha nincs, akkor a szülő kategóriában keresünk
                elif product.categ_id.parent_id and product.categ_id.parent_id.product_family_ids:
                    family = product.categ_id.parent_id.product_family_ids[0]
            product.product_family_id = family.id if family else False


class Product(models.Model):
    _inherit = 'product.product'

    invoice_name = fields.Char(string='Számlázási név', translate=True)
    component_code = fields.Char(string='Alkatrészkód', compute='_compute_component_name', store=True, readonly=False)

    description = fields.Html('Description', translate=True)
    parcel_qty = fields.Integer(string='Csomag db')
    size_x = fields.Integer(string='X mm', compute='_compute_sizes', inverse='_inverse_size_x', store=True)
    size_y = fields.Integer(string='Y mm', compute='_compute_sizes', inverse='_inverse_size_y', store=True)
    size_z = fields.Integer(string='Z mm', compute='_compute_sizes', inverse='_inverse_size_z', store=True)
    dimensions = fields.Char(string='Méret', compute='_compute_dimensions', store=True)
    volume = fields.Float(compute='_compute_dimensions', store=True, readonly=False)
    old_pp_id = fields.Integer()

    product_codes = fields.Char(
        string="Beszállítói termékkódok", 
        compute="_compute_product_codes",
        store=True
    )

    @api.depends('product_tmpl_id.seller_ids.product_code', 'product_tmpl_id.seller_ids.product_id')
    def _compute_product_codes(self):
        for product in self:
            # A variánsnál figyelembe vesszük a sablon és a variáns-specifikus beszállítókat is
            relevant_sellers = product.seller_ids.filtered(
                lambda s: not s.product_id or s.product_id == product
            )
            
            # 2. A MAPPED-et a már SZŰRT listán (relevant_sellers) futtatjuk le!
            codes = relevant_sellers.mapped('product_code')
            valid_codes = [code for code in codes if code]
            product.product_codes = ", ".join(set(valid_codes))

    # @api.depends('product_tmpl_id.invoicing_name')
    # def _compute_invoicing_name(self):
    #     for product in self:
    #         if not product.invoicing_name:
    #             product.invoicing_name = product.product_tmpl_id.invoicing_name

    @api.depends('product_tmpl_id.component_code')
    def _compute_component_name(self):
        for product in self:
            if not product.component_code:
                product.component_code = product.product_tmpl_id.component_code

    @api.depends('product_template_attribute_value_ids', 'product_tmpl_id.attribute_line_ids.value_ids')
    def _compute_sizes(self):
        for product in self:
            x, y, z = False, False, False
            x_counter = 0
            y_counter = 0
            z_counter = 0

            # For variant products: read from product_template_attribute_value_ids
            # For no-variant products (single product.product per template): fall back
            # to template attribute lines, iterating over each line's single value.

            if product.product_template_attribute_value_ids:
                attr_pairs = [
                    (pav.attribute_id.name.lower(), pav.name)
                    for pav in product.product_template_attribute_value_ids
                ]
            else:
                attr_pairs = [
                    (line.attribute_id.name.lower(), val.name)
                    for line in product.product_tmpl_id.attribute_line_ids
                    for val in line.value_ids
                ]

            for attr_name, val_name in attr_pairs:

                if "méret" in attr_name:
                    match = re.fullmatch(r'\s*(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*', val_name or '')
                    if match:
                        x, y, z = (int(g) for g in match.groups())
                        x_counter += 1
                        y_counter += 1
                        z_counter += 1
                    continue

                try:
                    value = int(val_name)
                except (ValueError, TypeError):
                    continue

                if x_counter == 0 and ("szélesség" in attr_name or "x" in attr_name):
                    x = value
                    x_counter += 1
                elif y_counter == 0 and ("magasság" in attr_name or "y" in attr_name):
                    y = value
                    y_counter += 1
                elif z_counter == 0 and ("hosszúság" in attr_name or "mélység" in attr_name or "z" in attr_name):
                    z = value
                    z_counter += 1

            if x and y and z and (x_counter == 1 and y_counter == 1 and z_counter == 1):
                product.size_x = x
                product.size_y = y
                product.size_z = z

    def _inverse_size_x(self): 
        pass

    def _inverse_size_y(self): 
        pass

    def _inverse_size_z(self): 
        pass

    @api.depends('size_x', 'size_y', 'size_z')
    def _compute_dimensions(self):
        for product in self:
            res = []
            # Csak azokat adjuk hozzá, amiknek van értéke
            if product.size_x: res.append(str(product.size_x))
            if product.size_y: res.append(str(product.size_y))
            if product.size_z: res.append(str(product.size_z))
            
            # Összefűzzük "x" jellel, pl: "100 x 50 x 20"
            product.dimensions = " x ".join(res) if res else ""

            # size_x/y/z mm-ben vannak, a volume m3-ben kell
            product.volume = (product.size_x * product.size_y * product.size_z) / 1e9
            

class Batch(models.Model):
    _name = 'lamello.batch'
    _description = 'Ütem'

    name = fields.Char(string='Referencia', default='Új ütem')
    delivery_year = fields.Integer(string='Év', default=lambda self: datetime.now().year, required=True)
    delivery_week = fields.Integer(string='Szállítási hét', default=lambda self: datetime.now().isocalendar()[1], required=True)

    def _get_default_number(self):
        last_batch = self.search([], order='number desc', limit=1)
        if last_batch:
            return last_batch.number + 1
        return 1

    number = fields.Integer(string='Sorszám', default=_get_default_number, required=True)
    color = fields.Selection([('4', 'natúr'), ('8', 'bianco'), ('16', 'dió')], string='Szín')
    product_family_id = fields.Many2one('lamello.productfamily', string='Termékcsalád')
    manufacturing_order_ids = fields.One2many(
        'mrp.production',
        'batch_id',
        string='Gyártási megrendelések'
    )
    active = fields.Boolean(default=True)
    
    # Eladható termékek gyártási rendelései
    sale_mo_ids = fields.One2many(
        'mrp.production', 
        'batch_id', 
        string='Eladható termékek',
        domain=[('product_id.sale_ok', '=', True)]
    )

    # Nem eladható (pl. félkész, alapanyag) termékek gyártási rendelései
    non_sale_mo_ids = fields.One2many(
        'mrp.production', 
        'batch_id', 
        string='Belső/Félkész termékek',
        domain=[('product_id.sale_ok', '=', False)]
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új ütem') == 'Új ütem' or not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('lamello.batch')
                if not vals['name']:
                    seq_record = self.env['ir.sequence'].sudo().search([('code', '=', 'lamello.batch')], limit=1)
                    if seq_record:
                        vals['name'] = seq_record._next()
        records = super().create(vals_list)
        return records

    @api.constrains('delivery_year', 'delivery_week', 'number', 'color', 'product_family_id')
    def _check_unique_batch(self):
        for batch in self:
            existing_batch = self.search([
                ('id', '!=', batch.id),
                ('delivery_year', '=', batch.delivery_year),
                ('delivery_week', '=', batch.delivery_week),
                ('number', '=', batch.number),
                ('color', '=', batch.color),
                ('product_family_id', '=', batch.product_family_id.id)
            ], limit=1)
            if existing_batch:
                raise ValidationError(_("Már létezik ilyen ütem! Kérem módosítsd az év, hét, sorszám, szín vagy termékcsalád értékét."))

    def action_confirm_parent_mo(self):
        self.ensure_one()
        parent_mos = self.env['mrp.production'].search([
            ('batch_id', '=', self.id),
            ('product_id.sale_ok', '=', True),
            ('state', '=', 'draft'),
        ])
        if not parent_mos:
            raise UserError(_('Nincs megerősíthető értékesíthető termék gyártási rendelés ebben az ütemben.'))
        parent_mos.action_confirm()

    def action_confirm_components(self):
        self.ensure_one()
        child_mos = self.env['mrp.production'].search([
            ('batch_id', '=', self.id),
            ('product_id.sale_ok', '=', False),
            ('state', '=', 'draft'),
        ])
        if not child_mos:
            raise UserError(_('Nincs megerősíthető félkész/alkatrész gyártási rendelés ebben az ütemben.'))
        child_mos.action_confirm()

    def action_manufacture_and_store_components(self):
        self.ensure_one()
        child_mos = self.env['mrp.production'].search([
            ('batch_id', '=', self.id),
            ('product_id.sale_ok', '=', False),
            ('state', 'in', ['confirmed', 'progress', 'to_close']),
        ])
        if child_mos:
            for mo in child_mos:
                if mo.qty_producing < mo.product_qty:
                    mo.qty_producing = mo.product_qty
            child_mos.with_context(skip_backorder=True).button_mark_done()
        self.action_store_components()

    def action_store_components(self):
        self.ensure_one()
        child_mos = self.env['mrp.production'].search([
            ('batch_id', '=', self.id),
            ('product_id.sale_ok', '=', False),
            ('state', 'not in', ['draft', 'cancel']),
        ])
        # SFP pickings store multiple MO names in a single comma-separated origin string
        # (e.g. "WH/MO/00006,WH/MO/00007,WH/MO/00008"), so exact 'in' matching fails.
        # Search with ilike per name then Python-filter to SFPs (non-purchasable moves only).
        mo_names = child_mos.mapped('name')
        if not mo_names:
            return
        # Build OR domain manually: (n-1) '|' operators prefix n ilike clauses
        origin_clauses = [('origin', 'ilike', name) for name in mo_names]
        origin_domain = (['|'] * (len(origin_clauses) - 1) + origin_clauses
                         if len(origin_clauses) > 1 else origin_clauses)
        sfp_pickings = self.env['stock.picking'].search(
            origin_domain + [('state', 'not in', ('done', 'cancel'))]
        ).filtered(
            lambda p: all(
                not m.product_id.purchase_ok
                for m in p.move_ids.filtered(lambda m: m.state != 'cancel')
            )
        )
        if not sfp_pickings:
            return

        # Validate SFPs: deliver manufactured components to stock (standard destination).
        for move in sfp_pickings.mapped('move_ids').filtered(lambda m: m.state not in ('done', 'cancel')):
            move.quantity = move.product_uom_qty
        sfp_pickings.with_context(skip_immediate=True).button_validate()

        # After SFP delivers to stock, validate the split PC pickings so they move
        # components from stock to WH/Pre-Production, completing the supply chain.
        parent_mos = self.env['mrp.production'].search([
            ('batch_id', '=', self.id),
            ('product_id.sale_ok', '=', True),
            ('state', 'not in', ['draft', 'done', 'cancel']),
        ])
        for parent_mo in parent_mos:
            non_purchasable_raw = parent_mo.move_raw_ids.filtered(
                lambda m: not m.product_id.purchase_ok and m.state == 'waiting'
            )
            if not non_purchasable_raw:
                continue
            split_pickings = non_purchasable_raw.mapped('move_orig_ids.picking_id').filtered(
                lambda p: p.state not in ('done', 'cancel')
            )
            for move in split_pickings.mapped('move_ids').filtered(lambda m: m.state not in ('done', 'cancel')):
                move.quantity = move.product_uom_qty
            if split_pickings:
                split_pickings.with_context(skip_immediate=True).button_validate()

        parent_mos.action_assign()

    def unlink(self):
        self.write({'active': False})
        return True

    def action_open_mo_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Gyártási megrendelések létrehozása',
            'res_model': 'lamello.batch.mo.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_batch_id': self.id,
            },
        }


class MrpBom(models.Model):
    _inherit = 'mrp.bom.line'

    # Átemeljük a méretet a termékről a darabjegyzékre
    dimensions = fields.Char(related='product_id.dimensions', string='Méretek', readonly=True)
    component_code = fields.Char(related='product_id.component_code', string='Alkatrészkód', readonly=False, store=True)


class BatchMOWizard(models.TransientModel):
    _name = 'lamello.batch.mo.wizard'
    _description = 'Gyártási megrendelések létrehozása SOL alapján'

    batch_id = fields.Many2one('lamello.batch', string='Ütem', required=True, readonly=True)
    delivery_year = fields.Integer(string='Év', related='batch_id.delivery_year', store=False, readonly=True)
    delivery_week = fields.Integer(string='Szállítási hét', related='batch_id.delivery_week', store=False, readonly=True)
    product_family_id = fields.Many2one(string='Termékcsalád', related='batch_id.product_family_id', store=False, readonly=True)
    color = fields.Selection(string='Szín', related='batch_id.color', store=False, readonly=True)
    sale_order_line_ids = fields.Many2many('sale.order.line', 'lamello_wizard_sol_rel', 'wizard_id', 'sol_id', string='Értékesítési rendelés sorok')

    def action_create_manufacturing_orders(self):
        self.ensure_one()
        if not self.sale_order_line_ids:
            raise UserError(_('Válassz legalább egy értékesítési rendelés sort!'))

        created_mos = self.env['mrp.production']
        for line in self.sale_order_line_ids:
            product = line.product_id
            if not product or product.type not in ('consu', 'product'):
                continue

            bom = self.env['mrp.bom'].search(['|', ('product_id', '=', product.id), '&', ('product_id', '=', False), ('product_tmpl_id', '=', product.product_tmpl_id.id),], limit=1)
            mo_vals = {
                'product_id': product.id,
                'product_qty': line.product_uom_qty,
                'product_uom_id': line.product_uom_id.id,
                'bom_id': bom.id if bom else False,
                'origin': line.order_id.name,
                'company_id': line.company_id.id,
            }
            mo = self.env['mrp.production'].create(mo_vals)
            created_mos |= mo

        if created_mos:
            self.batch_id.manufacturing_order_ids = [(4, mo.id) for mo in created_mos]
            self.sale_order_line_ids.write({'batch_id': self.batch_id.id})
            sale_orders = self.sale_order_line_ids.mapped('order_id')
            sale_orders.write({'batch_id': [(4, self.batch_id.id)]})

        return {'type': 'ir.actions.act_window_close'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_year = fields.Integer(string='Év', required=True, default=lambda self: datetime.now().year)
    delivery_week = fields.Integer(string='Szállítási hét', required=True, default=lambda self: datetime.now().isocalendar().week)
    product_families = fields.Many2many('lamello.productfamily', string='Termékcsaládok', compute='_compute_product_families', store=True)
    type = fields.Selection([('export', 'Export'), ('domestic', 'Hazai')], string='Típus')
    sale_order_group_by_week_and_partner = fields.Boolean(string='Kiszállítás csoportosítása hét és partner szerint')
    client_order_ref = fields.Char(string='Hivatkozó referencia')
    batch_id = fields.Many2many('lamello.batch', 'sale_order_batch_rel', 'sale_order_id', 'batch_id', string='Ütem')
    has_manufacturing_order = fields.Boolean(
        string='Van gyártási rendelése',
        compute='_compute_has_manufacturing_order',
        store=True,
        compute_sudo=True,
    )

    @api.depends('stock_reference_ids.production_ids', 'stock_reference_ids.production_ids.state')
    def _compute_has_manufacturing_order(self):
        for order in self:
            mos = order.stock_reference_ids.production_ids
            order.has_manufacturing_order = bool(mos.filtered(lambda mo: mo.state != 'cancel'))

    @api.depends('order_line.product_id.product_tmpl_id.product_family_id')
    def _compute_product_families(self):
        for order in self:
            families = set()
            for line in order.order_line:
                if line.product_id.product_tmpl_id.product_family_id:
                    families.add(line.product_id.product_tmpl_id.product_family_id)
            order.product_families = [(6, 0, [f.id for f in families])]

            # alternatíva write: order.write({'product_families': [(6, 0, [f.id for f in families])]})
            # altrenatíva Command: order.product_families = Command.set([f.id for f in families])
            # https://www.odoo.com/forum/help-1/many2many-write-replaces-all-existing-records-in-the-set-by-the-ids-148267

    commitment_date = fields.Datetime(
        string="Delivery Date", 
        copy=False, 
        default=False,
        compute="_compute_commitment_date",
        inverse="_inverse_commitment_date",
        store=True,
        readonly=False,
        help="This is the delivery date promised to the customer. "
             "If set, the delivery order will be scheduled based on "
             "this date rather than product lead times.")

    @api.depends('delivery_year', 'delivery_week')
    def _compute_commitment_date(self):
        for order in self:
            if order.delivery_week:
                year = order.delivery_year
                week = order.delivery_week
                now = datetime.now()
                today_number = now.isoweekday()
                if today_number > 1 and week == now.isocalendar().week and year == now.year:
                    day = today_number
                else:
                    day = 1
                d = date.fromisocalendar(year, week, day)
                dt = datetime.combine(d, datetime.min.time())
                order.commitment_date = dt
            else:
                order.commitment_date = False

    def _inverse_commitment_date(self):
        for order in self:
            if order.commitment_date:
                dt = order.commitment_date
                order.delivery_year = dt.year
                order.delivery_week = dt.isocalendar().week

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._link_optional_products()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals:
            self._link_optional_products()
        return res

    def _link_optional_products(self):
        for order in self:
            last_main_line = False
            for line in order.order_line.sorted('sequence'):
                

                # utolsó főtermék sor megjegyzése, ha van tartozéka
                # utolsó főtermék sorhoz kapcsolás, ha nincs tarotzéka és a product_tmpl_id meszerepel a főtermék tartozékai között
                if line.product_id.optional_product_ids:
                    last_main_line = line
                elif last_main_line and not line.product_id.optional_product_ids and line.product_id.product_tmpl_id in last_main_line.product_id.optional_product_ids:
                    line.linked_line_id = last_main_line.id                


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    batch_id = fields.Many2one('lamello.batch', string='Ütem')
    order_partner_id = fields.Many2one(
        related='order_id.partner_id', 
        string="Vevő", 
        store=True,   # Opcionális: ha szűrni/keresni is akarsz rá
        readonly=True
    )
    parcel_qty = fields.Integer(string='Csomag db')
    product_size_x = fields.Integer(related='product_id.size_x', string='X', readonly=True)
    product_size_y = fields.Integer(related='product_id.size_y', string='Y', readonly=True)
    product_size_z = fields.Integer(related='product_id.size_z', string='Z', readonly=True)

    @api.onchange('product_id')
    def _onchange_product_id_parcel_qty(self):
        if self.product_id:
            self.parcel_qty = self.product_id.parcel_qty or self.product_id.product_tmpl_id.parcel_qty

    def _get_sale_order_line_multiline_description_sale(self):
        self.ensure_one()

        # 1. Alapértelmezett leírás (Terméknév + Variánsok)
        base_description = (
            self.product_id.get_product_multiline_description_sale()
            + self._get_sale_order_line_multiline_description_variants()
        )

        # 2. Megnézzük, mi van most a mezőben
        current_name = self.name or ""
        
        # 3. Meghatározzuk a kiindulási pontot:
        # Ha a jelenlegi név már tartalmazza az alapleírást és azon felül mást is,
        # akkor a jelenlegi nevet visszük tovább, hogy ne vesszen el a kézi módosítás.
        if current_name and base_description.strip() in current_name.strip():
            result_description = current_name
            has_custom_info = current_name.strip() != base_description.strip()
        else:
            result_description = base_description
            has_custom_info = False

        # 4. 'Option for' hozzáadása, de CSAK ha:
        # - Van szülő (linked_line_id)
        # - Nem combo item
        # - MÉG NINCS benne az "Option for" szöveg (hogy ne duplázza minden mentésnél)
        # - És NINCS egyedi kézi leírás (a kérésed szerint)
        
        # kikapcsolva
        # option_label = _("Option for:")
        option_label = _("")
        if (self.linked_line_id and 
            not self.combo_item_id and 
            not has_custom_info and 
            option_label not in result_description):
            
            result_description += "\n" + _(
                "Option for: %s",
                self.linked_line_id.product_id.with_context(display_default_code=False).display_name
            )

        return result_description


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('lamello.batch', string='Ütem')
    is_filtered_pick = fields.Boolean(string='Raktári kiadás csoportosítása', default=True)

    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Csak akkor fut le, ha nincs még kitöltve a batch_id, de van forrásbizonylat (origin)
            if not vals.get('batch_id') and vals.get('origin'):
                # Megnézzük, hogy a forrás (origin) egy másik gyártási rendelés-e (pl. "WH/MO/00012")
                parent_mo = self.env['mrp.production'].search([('name', '=', vals['origin'])], limit=1)
                
                if parent_mo and parent_mo.batch_id:
                    vals['batch_id'] = parent_mo.batch_id.id

        # Végül meghívjuk a gyári mentést
        return super(MrpProduction, self).create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if 'batch_id' in vals:
            for mo in self:
                child_mos = self.env['mrp.production'].search([('origin', '=', mo.name)])
                if child_mos:
                    child_mos.write({'batch_id': vals['batch_id']})
        return result

    def action_confirm(self):
        result = super().action_confirm()
        for mo in self.filtered(lambda m: m.batch_id and m.product_id.sale_ok and m.is_filtered_pick):
            # Split Pick Components into two separate pickings:
            # - original picking keeps only purchasable moves
            # - new picking holds non-purchasable (manufactured) moves
            non_purchasable_moves = mo.picking_ids.mapped('move_ids').filtered(
                lambda m: not m.product_id.purchase_ok and m.state not in ('done', 'cancel')
            )
            if non_purchasable_moves:
                ref = non_purchasable_moves[0]
                new_picking = self.env['stock.picking'].create({
                    'picking_type_id': ref.picking_type_id.id,
                    'location_id': ref.location_id.id,
                    'location_dest_id': ref.location_dest_id.id,
                    'origin': mo.name,
                    'company_id': mo.company_id.id,
                })
                non_purchasable_moves.write({'picking_id': new_picking.id})
                new_picking.action_confirm()
        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_year = fields.Integer(string='Év')
    delivery_week = fields.Integer(string='Szállítási hét')
    type = fields.Selection([('export', 'Export'), ('domestic', 'Hazai')], string='Típus')
    invoiced = fields.Boolean('Számlázva')

    total_qty = fields.Integer(string='Összmennyiség', compute='_compute_total_qty')
    total_parcel_qty = fields.Integer(string='Csomag mennyiség', compute='_compute_total_parcel_qty')
    total_weight = fields.Float(string='Összsúly', compute='_compute_total_weight')
    total_volume = fields.Float(string='Összvolumen', compute='_compute_total_volume')
    delivery_slip_type = fields.Selection([('default', 'Alapértelemzett'), 
                                           ('export', 'Export szállítólevél')], string='Szállítólevél sablon')

    # Az MO (Manufacturing Order) referenciája
    mo_id = fields.Many2one(
        'mrp.production', 
        string='Gyártási rendelés', 
        compute='_compute_mo_id', 
        store=True
    )
    
    # A lamello_batch_id egyszerű related mező, így automatikusan frissül
    # A store=True biztosítja a kereshetőséget és a riportálhatóságot
    # Megjegyzés: nem nevezhető 'batch_id', mert az ütközik a stock_picking_batch
    # modul saját 'batch_id' (Many2one -> stock.picking.batch) mezőjével.
    lamello_batch_id = fields.Many2one(
        'lamello.batch',
        related='mo_id.batch_id',
        string='Ütem',
        store=True,
        readonly=True
    )

    @api.depends('origin')
    def _compute_mo_id(self):
        for picking in self:
            mo = False
            if picking.origin:
                # Origin can be a comma-separated list (e.g. batch SFP pickings).
                # Take the first name to find the MO and its batch_id.
                first_name = picking.origin.split(',')[0].strip()
                mo = self.env['mrp.production'].search([('name', '=', first_name)], limit=1)
            picking.mo_id = mo


    @api.depends('move_ids.move_line_ids.line_parcel_qty')
    def _compute_total_parcel_qty(self):
        for picking in self:
            total_parcel_qty = 0
            for move in picking.move_ids:
                for move_line in move.move_line_ids:
                    total_parcel_qty += move_line.line_parcel_qty
            picking.total_parcel_qty = total_parcel_qty

    @api.depends('move_ids.move_line_ids.quantity')
    def _compute_total_qty(self):
        for picking in self:
            total_qty = 0
            for move in picking.move_ids:
                for move_line in move.move_line_ids:
                    total_qty += move_line.quantity
            picking.total_qty = total_qty

    @api.depends('move_ids.move_line_ids.product_id.weight')
    def _compute_total_weight(self):
        for picking in self:
            total_weight = 0
            for move in picking.move_ids:
                for move_line in move.move_line_ids:
                    total_weight += move_line.product_id.weight * move_line.quantity
            picking.total_weight = total_weight

    @api.depends('move_ids.move_line_ids.product_id.volume')
    def _compute_total_volume(self):
        for picking in self:
            total_volume = 0
            for move in picking.move_ids:
                for move_line in move.move_line_ids:
                    total_volume += move_line.product_id.volume * move_line.quantity
            picking.total_volume = total_volume

    def action_custom_create_invoice(self):
        for picking in self:
            if picking.state != 'done':
                raise UserError(_("Csak lezárt (Done) állapotú bizonylatból lehet számlát létrehozni!"))
            if not picking.partner_id:
                raise UserError(_("A szállítólevélhez nincs partner rendelve!"))

            # 1. Számla fejléc (account.move) létrehozása
            # def_payment_method = self.env['account.payment.method'].search([('name', 'ilike', 'átutalás')], limit=1)
            invoice_vals = {
                'move_type': 'out_invoice', # Vevői számla (bejövőnél: 'in_invoice')
                'partner_id': picking.partner_id.id,
                'invoice_date': fields.Date.context_today(self),
                'invoice_origin': picking.name,
                'currency_id': picking.sale_id.currency_id.id,  # <--- Itt adjuk át a devizát
                'l10n_hu_payment_mode': 'TRANSFER',
                'invoice_line_ids': [],
            }

            # 2. Számlasorok (account.move.line) előkészítése a kiadott mennyiségek alapján
            for move in picking.move_ids:
                if move.quantity > 0:
                    # Megkeressük a termékhez tartozó bevételi főkönyvi számot
                    accounts = move.product_id.product_tmpl_id.get_product_accounts()
                    account_id = accounts['income'] or self.env['ir.property']._get('property_account_income_categ_id', 'product.category')

                    line_vals = {
                        'name': move.product_id.display_name,
                        'product_id': move.product_id.id,
                        'quantity': move.quantity, # A ténylegesen kiadott (Done) mennyiség
                        'product_uom_id': move.product_uom.id,
                        'price_unit': move.product_id.lst_price, # Listaár (vagy SO sor ára, ha van)
                        'account_id': account_id.id,
                        'tax_ids': [(6, 0, move.product_id.taxes_id.ids)],
                        'price_unit': move.sale_line_id.price_unit,
                        'sale_line_ids': [(6, 0, [move.sale_line_id.id])]
                    }
                    invoice_vals['invoice_line_ids'].append((0, 0, line_vals))

            if not invoice_vals['invoice_line_ids']:
                raise UserError(_("Nincs kiszállított mennyiség, amit számlázni lehetne."))

            # 3. Számla létrehozása
            new_invoice = self.env['account.move'].create(invoice_vals)
            
            picking.invoiced = True
            
            # Opcionális: Számla megnyitása
            return {
                'name': _('Létrehozott számla'),
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': new_invoice.id,
                'type': 'ir.actions.act_window',
            }


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    def get_stock_picking_action_res_model(self):
        action = super(StockPickingType, self).get_stock_picking_action_res_model()
        # custom_view_id = self.env.ref('lamello_customizations.lamello_stock_picking_tree_custom').id
        # if self.code == 'outgoing':
        #     action['views'] = [
        #         (custom_view_id, 'tree'),
        #         (self.env.ref('stock.view_picking_form').id, 'form')
        #     ]
        return action

    # felső link
    def get_stock_picking_action_picking_type(self):
        # if self.code == 'outgoing':
        #     return self._get_action('lamello_customizations.action_lamello_picking_tree_outgoing')
        if self.code == 'internal':
            return self._get_action('lamello_customizations.action_lamello_picking_tree_internal')
        else:
            return super(StockPickingType, self).get_stock_picking_action_picking_type()

    # gomb, ready filter
    def get_action_picking_tree_ready(self):
        # if self.code == 'outgoing':
        #     return self._get_action('lamello_customizations.action_lamello_picking_tree_ready')
        if self.code == 'internal':
            return self._get_action('lamello_customizations.action_lamello_picking_tree_ready_internal')
        else:
            return self._get_action('stock.action_picking_tree_ready')


class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    note = fields.Html('Notes')

    def action_print_consolidated_delivery_note(self):
        self.ensure_one()
        partner_ids = set(self.picking_ids.mapped(lambda p: p.partner_id.id))
        if len(partner_ids) != 1:
            raise UserError(_("A konszolidált szállítólevél nyomtatásához az ütem összes szállítólevelének azonos partnerhez kell tartoznia."))
        return self.env.ref('lamello_customizations.action_lamello_report_consolidated_delivery').report_action(self)


class StockMove(models.Model):
    _inherit = 'stock.move'

    parcel_qty = fields.Integer(string='Csomag db', compute='_compute_parcel_qty', store=True, readonly=False)

    @api.depends('sale_line_id.parcel_qty', 'product_id.parcel_qty')
    def _compute_parcel_qty(self):
        for move in self:
            move.parcel_qty = move.sale_line_id.parcel_qty or move.product_id.parcel_qty

    # jó megoldás, de nem kell egyelőre
    # @api.depends('sale_line_id.order_id.type', 'product_id.invoice_name')
    # def _compute_description_picking(self):
    #     super()._compute_description_picking()
    #     for move in self:
    #         if (move.sale_line_id.order_id.type == 'export'
    #                 and not move.description_picking_manual
    #                 and move.product_id.invoice_name):
    #             move.description_picking = move.product_id.invoice_name

    def _search_picking_for_assignation_domain(self):
        sale_order = (
            self.reference_ids[:1].sale_ids[:1]
        )
        if sale_order.sale_order_group_by_week_and_partner:
            domain = [
                ('delivery_year', '=', sale_order.delivery_year),
                ('delivery_week', '=', sale_order.delivery_week),
                ('type', '=', sale_order.type),
                ('location_id', '=', self.location_id.id),
                ('location_dest_id', '=', (self.location_dest_id.id or self.picking_type_id.default_location_dest_id.id)),
                ('picking_type_id', '=', self.picking_type_id.id),
                ('printed', '=', False),
                ('state', 'in', ['ready', 'draft', 'confirmed', 'waiting', 'partially_available', 'assigned'])
                ]
            if self.partner_id and not self.reference_ids:
                domain += [('partner_id', '=', self.partner_id.id)]
        else:
            domain = super(StockMove, self)._search_picking_for_assignation_domain()
        return domain

    def _get_new_picking_values(self):
        sale_order = (
            self.reference_ids[:1].sale_ids[:1]
        )
        vals = super(StockMove, self)._get_new_picking_values()
        # if sale_order.type == 'export':
        #     vals['delivery_year'] = sale_order.delivery_year
        #     vals['delivery_week'] = sale_order.delivery_week
        vals['type'] = sale_order.type
        vals['delivery_year'] = sale_order.delivery_year
        vals['delivery_week'] = sale_order.delivery_week
        return vals


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    parcel_qty = fields.Integer(string='Csomag db', compute='_compute_parcel_qty', store=True, readonly=False)
    line_parcel_qty = fields.Integer(string='Csomag db összesen', compute='_compute_total_parcel_weight')

    @api.depends('move_id.parcel_qty')
    def _compute_parcel_qty(self):
        for line in self:
            line.parcel_qty = line.move_id.parcel_qty

    @api.depends('quantity', 'parcel_qty')
    def _compute_total_parcel_weight(self):
        for line in self:
            if line.parcel_qty > 0:
                line.line_parcel_qty = line.parcel_qty * line.quantity
            else:
                line.line_parcel_qty = line.quantity

class AccountMove(models.Model):
    _inherit = 'account.move'

    account_template_type = fields.Selection([('default', 'Alapértelemzett'), ('export', 'Export')], string='Számla sablon')
    group_by_so = fields.Boolean('Csoportosítás rendelések szerint')


class ResCompany(models.Model):
    _inherit = 'res.company'

    international_vat = fields.Char(string='Nemzetközi adószám')


class MrpComponentGroup(models.Model):
    _name = 'mrp.component.group'
    _description = 'Gyártási Komponens Csoportosítás'
    _order = 'sequence, id'

    name = fields.Char(string='Csoport neve', required=True, help="Pl. Fenekek, Oldalak")
    sequence = fields.Integer(string='Sorrend', default=10)
    
    keyword_ids = fields.One2many('mrp.component.group.keyword', 'group_id', string='Kulcsszavak')
    code_ids = fields.One2many('mrp.component.group.code', 'group_id', string='Komponens kódok')


class MrpComponentGroupKeyword(models.Model):
    _name = 'mrp.component.group.keyword'
    _description = 'Komponens Csoport Kulcsszó'
    
    name = fields.Char(string='Kulcsszó', required=True, help="A termék nevében keresendő kifejezés")
    group_id = fields.Many2one('mrp.component.group', string='Csoport', ondelete='cascade')


class MrpComponentGroupCode(models.Model):
    _name = 'mrp.component.group.code'
    _description = 'Komponens Csoport Kód'
    
    name = fields.Char(string='Kód', required=True, help="A BoM soron megadott komponens kód")
    group_id = fields.Many2one('mrp.component.group', string='Csoport', ondelete='cascade')


class ComponentReportParser(models.AbstractModel):
    _name = 'report.lamello_customizations.report_component_template'

    def get_real_child_mo(self, move):
        """
        Megkeresi a gyermek MO-t a stock_move_move_rel és a 
        created_production_id mezők alapján.
        """
        # 1. Megnézzük a move_orig_ids-t (visszafelé a láncon, ahogy az SQL-ben nézted)
        # A move.move_orig_ids azok a mozgások, amik "szülik" ezt az alapanyagot
        for orig_move in move.move_orig_ids:
            # Megnézzük, hogy ez a forrás-mozgás hozott-e létre közvetlenül gyártást
            if orig_move.created_production_id:
                return orig_move.created_production_id
                
            # Ha a mozgáshoz már hozzá van rendelve egy gyártás (mint késztermék)
            if orig_move.production_id:
                return orig_move.production_id

        # 2. Biztonsági tartalék: Origin + Product + State alapján
        # Ez akkor segít, ha a láncolat valamiért megszakadt az adatbázisban
        child_mo_backup = self.env['mrp.production'].search([
            ('origin', '=', move.raw_material_production_id.name),
            ('product_id', '=', move.product_id.id),
            ('state', '!=', 'cancel')
        ], limit=1)

        if child_mo_backup:
            return child_mo_backup

        return False

    def _build_batches(self, docs, demand=False):
        """Build the batches data structure for report templates.

        Iterates parent sale MOs → their raw moves → the real child MO for each move.
        Groups child MO products using component group rules loaded from the database.

        demand=False  all child MOs are included
        demand=True   only child MOs that are not yet done or cancelled
        """
        # Load component group rules from the database
        group_records = self.env['mrp.component.group'].search([])
        db_component_codes = {}   # {'F1': 'Fenekek', ...}
        db_keywords = {}          # {'Fenék': 'Fenekek', ...}
        group_names = []          # ordered list to preserve sequence

        for group in group_records:
            group_names.append(group.name)
            for code_rec in group.code_ids:
                db_component_codes[code_rec.name] = group.name
            for kw_rec in group.keyword_ids:
                db_keywords[kw_rec.name] = group.name

        batches_list = []

        for batch in docs.mapped('batch_id'):
            number = batch.number
            color = dict(batch._fields['color'].selection).get(batch.color)
            family = batch.product_family_id.name or ''
            week = batch.delivery_week

            batch_docs = docs.filtered(lambda m: m.batch_id == batch)
            sale_mos = batch_docs.filtered(lambda mo: mo.product_id.sale_ok)

            # {group_name: {product_id: {'product_id': record, 'qty': float}}}
            groups_dict = {name: {} for name in group_names}

            for mo in sale_mos:
                if mo.state not in ('confirmed', 'ready', 'in_progress', 'done'):
                    continue

                for move in mo.move_raw_ids:
                    # Skip purchased components — they have no child MO
                    if move.product_id.purchase_ok:
                        continue

                    child_mo = self.get_real_child_mo(move)
                    if not child_mo:
                        continue

                    # cancelled child MOs are never included
                    if child_mo.state == 'cancel':
                        continue
                    # demand mode requires at least confirmed (skip draft)
                    if demand and child_mo.state == 'draft':
                        continue

                    # Determine group: BOM line component code first, then keyword search
                    assigned_group = False
                    comp_code = move.bom_line_id.component_code if move.bom_line_id else False
                    if comp_code and comp_code in db_component_codes:
                        assigned_group = db_component_codes[comp_code]
                    if not assigned_group:
                        child_name = child_mo.product_id.name or ''
                        for kw, group_name in db_keywords.items():
                            if re.search(kw, child_name, re.IGNORECASE):
                                assigned_group = group_name
                                break

                    if not assigned_group:
                        continue

                    # Aggregate quantities per child MO product
                    p_id = child_mo.product_id.id
                    qty = child_mo.product_qty
                    if p_id in groups_dict[assigned_group]:
                        groups_dict[assigned_group][p_id]['qty'] += qty
                    else:
                        groups_dict[assigned_group][p_id] = {
                            'product_id': child_mo.product_id,
                            'qty': qty,
                        }

            # Convert to MockMove objects that the QWeb templates expect
            # (templates access line.product_id and line.product_uom_qty)
            final_groups = {name: [] for name in group_names}
            for group_key, products in groups_dict.items():
                for data in products.values():
                    mock_line = type('MockMove', (), {
                        'product_id': data['product_id'],
                        'product_uom_qty': data['qty'],
                    })
                    final_groups[group_key].append(mock_line)

            batches_list.append({
                'number': number,
                'color': color,
                'family': family,
                'week': week,
                'sale_mo_ids': sale_mos,
                'groups': final_groups,
            })

        return batches_list

    @api.model
    def _get_report_values(self, docids, data=None):
        if not docids and data and data.get('ids'):
            docids = data.get('ids')
        docs = self.env['mrp.production'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'mrp.production',
            'batches': self._build_batches(docs, demand=False),
        }


class PickingReportParser(models.AbstractModel):
    # Válogató lista (Tervezett) — inherits _build_batches(demand=False) from ComponentReportParser
    _name = 'report.lamello_customizations.report_picking_template'
    _inherit = 'report.lamello_customizations.report_component_template'


class PickingReportDemandParser(models.AbstractModel):
    # Válogató lista (Igény alapján) — only child MOs not yet done or cancelled
    _name = 'report.lamello_customizations.report_picking_template_demand'
    _inherit = 'report.lamello_customizations.report_component_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not docids and data and data.get('ids'):
            docids = data.get('ids')
        docs = self.env['mrp.production'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'mrp.production',
            'batches': self._build_batches(docs, demand=True),
        }


class ComponentDemandReportParser(models.AbstractModel):
    # Alkatrészlista (Igény alapján) — only child MOs not yet done or cancelled
    _name = 'report.lamello_customizations.report_component_template_demand'
    _inherit = 'report.lamello_customizations.report_component_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not docids and data and data.get('ids'):
            docids = data.get('ids')
        docs = self.env['mrp.production'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'mrp.production',
            'batches': self._build_batches(docs, demand=True),
        }


class LamelloBatchReportWizard(models.TransientModel):
    _name = 'lamello.batch.report.wizard'
    _description = 'Batch Riport Wizard'
    
    batch_id = fields.Many2one('lamello.batch', string='Ütem')
    delivery_year = fields.Integer(string='Év', default=lambda self: datetime.now().year)
    delivery_week = fields.Integer(string='Szállítási hét', default=lambda self: datetime.now().isocalendar().week)

    report_type = fields.Selection([
        ('component', 'Alkatrészlista (Tervezett)'),
        ('component_demand', 'Alkatrészlista (Igény alapján)'),
        ('picking', 'Válogató lista (Tervezett)'),
        ('picking_demand', 'Válogató lista (Igény alapján)'),
    ], string='Riport típusa', default='component', required=True)

    @api.onchange('batch_id')
    def _onchange_batch_id(self):
        if self.batch_id:
            self.delivery_year = self.batch_id.delivery_year
            self.delivery_week = self.batch_id.delivery_week

    def action_print(self):
        self.ensure_one()

        if self.batch_id:
            production_ids = self.env['mrp.production'].search([('batch_id', '=', self.batch_id.id)])
        else:
            batch_ids = self.env['lamello.batch'].search([
                ('delivery_year', '=', self.delivery_year),
                ('delivery_week', '=', self.delivery_week)
            ])
            production_ids = self.env['mrp.production'].search([('batch_id', 'in', batch_ids.ids)])

        data = {'ids': production_ids.ids, 'model': 'mrp.production'}

        report_map = {
            'component':        'lamello_customizations.action_report_component_list',
            'component_demand': 'lamello_customizations.action_report_component_list_demand',
            'picking':          'lamello_customizations.action_report_picking_list',
            'picking_demand':   'lamello_customizations.action_report_picking_list_demand',
        }
        action_ref = report_map[self.report_type]
        return self.env.ref(action_ref).report_action(production_ids, data=data)


# ez egy commit!!!

# class ResUsers(models.Model):
#     _inherit = 'res.users'

#     narrow_chatter = fields.Boolean(string='Keskeny üzenőfal', default=False)

#     def write(self, vals):
#         if list(vals.keys()) == ['narrow_chatter'] and self == self.env.user:
#             return super(ResUsers, self.sudo()).write(vals)
#         return super().write(vals)


# class IrHttp(models.AbstractModel):
#     _inherit = 'ir.http'

#     def session_info(self):
#         result = super().session_info()
#         user = None
#         if request is not None and getattr(request, 'env', None):
#             user = request.env.user
#         else:
#             user = self.env.user
#         if user:
#             result['narrow_chatter'] = user.narrow_chatter
#         return result
