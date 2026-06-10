from odoo import models, fields, api, _, tools
from math import pi, pow
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)



class Lot(models.Model):
    _inherit = 'stock.lot'

    wood_type_id = fields.Many2one('lamello.woodtype', string="Fatípus", ondelete='set null')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_forestry_company = fields.Boolean("Erdészeti/Fűrészárú beszállító")


class Product(models.Model):
    _inherit = 'product.product'

    stack_wood_type_ids = fields.One2many('lamello.woodtype', 'timber_stack_product_id', string="Fatípusok", ondelete='set null')
    log_wood_type_ids = fields.One2many('lamello.woodtype', 'timber_log_product_id', string="Fatípusok", ondelete='set null')
    stack_product = fields.Boolean("Rakat termék", compute="_compute_stack_product", store=True)
    log_product = fields.Boolean("Farönk termék", compute="_compute_log_product", store=True)

    @api.depends('stack_wood_type_ids')
    def _compute_stack_product(self):
        for rec in self:
            rec.stack_product = bool(rec.stack_wood_type_ids)

    @api.depends('log_wood_type_ids')
    def _compute_log_product(self):
        for rec in self:
            rec.log_product = bool(rec.log_wood_type_ids)


class WoodType(models.Model):
    _name = 'lamello.woodtype'
    _description = "Fa típus"
    _order = 'id desc'

    name = fields.Char("Név", compute="_compute_name", store=True)
    species = fields.Char("Megnevezés", required=True)
    quality = fields.Char("Minőségi osztály", required=True)
    description = fields.Text("Leírás")

    wood_group = fields.Selection([
        ('tolgy', 'Tölgy'),
        ('cser', 'Cser'),
        ('bukk', 'Bükk'),
        ('akac', 'Akác'),
        ('gyertyan', 'Gyertyán és egyéb kemény lombos'),
        ('nyar', 'Nyár'),
        ('egyeb', 'Egyéb lágy lomb'),
        ('fenyo', 'Fenyő'),
    ], string="Fafaj / csoport", required=True)

    timber_stack_product_id = fields.Many2one('product.product', string="Rakat termék", ondelete='set null')
    timber_log_product_id = fields.Many2one('product.product', string="Farönk termék", ondelete='set null')

    @api.depends('species', 'quality')
    def _compute_name(self):
        for rec in self:
            quality = ""
            if rec.quality:
                if "." in rec.quality:
                    quality = f"({rec.quality} osztály)"
                else:
                    quality = f"({rec.quality}. osztály)"
            rec.name = f"{rec.species} {quality}"

    @api.onchange('wood_group')
    def _onchange_wood_group(self):
        selected_group = self.wood_group
        self.species = dict(self._fields['wood_group'].selection).get(selected_group, '') if selected_group else ''

    def calculate_log_volume(self, atmero, hosszusag):
        self.ensure_one()

        if self.wood_group == 'tolgy':
            if atmero <= 30:
                beta = 0.008350
            elif 30 < atmero and atmero <= 50:
                beta = 0.011000
            elif 50 < atmero:
                beta = 0.013430
        elif self.wood_group == 'cser':
            if atmero <= 30:
                beta = 0.008540
            elif 30 < atmero and atmero <= 50:
                beta = 0.013000
            elif 50 < atmero:
                beta = 0.016200
        elif self.wood_group == 'bukk':
            if atmero <= 30:
                beta = 0.009410
            elif 30 < atmero and atmero <= 50:
                beta = 0.010800
            elif 50 < atmero:
                beta = 0.017600
        elif self.wood_group == 'akac':
            if atmero <= 30:
                beta = 0.010200
            elif 30 < atmero and atmero <= 50:
                beta = 0.016680
            elif 50 < atmero:
                beta = 0.018900
        elif self.wood_group == 'gyertyan':
            if atmero <= 30:
                beta = 0.007800
            elif 30 < atmero and atmero <= 50:
                beta = 0.011570
            elif 50 < atmero:
                beta = 0.014880
        elif self.wood_group == 'nyar':
            if atmero <= 30:
                beta = 0.009700
            elif 30 < atmero and atmero <= 50:
                beta = 0.013800
            elif 50 < atmero:
                beta = 0.019270
        elif self.wood_group == 'egyeb':
            if atmero <= 30:
                beta = 0.008570
            elif 30 < atmero and atmero <= 50:
                beta = 0.011500
            elif 50 < atmero:
                beta = 0.013270
        elif self.wood_group == 'fenyo':
            if atmero <= 30:
                beta = 0.009190			
            elif 30 < atmero and atmero <= 50:
                beta = 0.014320
            elif 50 < atmero:
                beta = 0.019475

        d = atmero / 100
        L = hosszusag / 100
        volume = ( ( ((pow(d, 2) * pi) / 4) + ((pow((d + L * beta), 2) * pi) / 4 )) / 2) * L

        return volume


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            species = vals.get('species', '')
            uom_m3 = self.env.ref('uom.product_uom_cubic_meter', raise_if_not_found=False)

            if not vals.get('timber_stack_product_id'):
                stack_name = f"{species} fűrészárú rakat"
                existing = self.env['product.product'].search([('name', '=', stack_name)], limit=1)
                
                if existing:
                    vals['timber_stack_product_id'] = existing.id
                else:
                    product = self.env['product.product'].create({
                        'name': stack_name,
                        'purchase_ok': True,
                        'sale_ok': True,
                        'type': 'consu',
                        'is_storable': True,
                        # 'tracking': 'lot',
                        'uom_id': uom_m3.id if uom_m3 else False,
                    })
                    vals['timber_stack_product_id'] = product.id

            if not vals.get('timber_log_product_id'):
                log_name = f"{species} farönk"
                existing = self.env['product.product'].search([('name', '=', log_name)], limit=1)
                
                if existing:
                    vals['timber_log_product_id'] = existing.id
                else:
                    product = self.env['product.product'].create({
                        'name': log_name,
                        'purchase_ok': True,
                        'sale_ok': False,
                        'type': 'consu',
                        'is_storable': True,
                        # 'tracking': 'lot',
                        'uom_id': uom_m3.id if uom_m3 else False,
                    })
                    vals['timber_log_product_id'] = product.id

        return super().create(vals_list)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    ronkjegyzek_id = fields.Many2one('lamello.ronkjegyzek', string="Rönkjegyzék", ondelete='set null')

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.partner_id.name})"

    has_timber_log_product = fields.Boolean(
        string="Tartalmaz rönköt",
        compute="_compute_has_timber_log_product",
        store=False
    )

    has_timber_stack_product = fields.Boolean(
        string="Tartalmaz rakatot",
        compute="_compute_has_timber_stack_product",
        store=False
    )

    @api.depends('order_line.product_id.log_product')
    def _compute_has_timber_log_product(self):
        for order in self:
            order.has_timber_log_product = any(
                line.product_id.log_product 
                for line in order.order_line
            )

    @api.depends('order_line.product_id.stack_product')
    def _compute_has_timber_stack_product(self):
        for order in self:
            order.has_timber_stack_product = any(
                line.product_id.stack_product 
                for line in order.order_line
            )

    def action_timber_log_list(self):
        if self.ronkjegyzek_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'lamello.ronkjegyzek',
                'view_mode': 'form',
                'res_id': self.ronkjegyzek_id.id,
            }
        else:
            new_ronkjegyzek = self.env['lamello.ronkjegyzek'].create({
                'purchase_date': self.date_order.date() if self.date_order else fields.Date.context_today(self),
                'expected_date': self.date_planned.date() if self.date_planned else fields.Date.context_today(self),
                'open_date': fields.Date.context_today(self),
                'description': f"Rönkjegyzék a {self.name} beszerzéshez",
            })
            self.ronkjegyzek_id = new_ronkjegyzek.id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'lamello.ronkjegyzek',
                'view_mode': 'form',
                'res_id': new_ronkjegyzek.id,
            }

    def action_timber_stack_list(self):
        timberstack_list = self.env['lamello.timberstack.list'].search([
            ('source_document', '=', f'purchase.order,{self.id}')  # ← 'model,id' formátum
        ], limit=1)
            
        if timberstack_list:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'lamello.timberstack.list',
                'view_mode': 'form',
                'res_id': timberstack_list.id,
            }
        else:
            new_stacklist = self.env['lamello.timberstack.list'].create({
                'source_document': f'purchase.order,{self.id}',  
                'description': f"Rakatjegyzék a {self.name} beszerzéshez",
            })
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'lamello.timberstack.list',
                'view_mode': 'form',
                'res_id': new_stacklist.id,
            }

    # Safer alternative: override the public button_confirm instead of the private _create_picking.
    # A picking is created momentarily then cancelled, leaving a cancelled WH/IN as an audit trail.
    # def button_confirm(self):
    #     res = super().button_confirm()
    #     for order in self:
    #         if order.partner_id.is_forestry_company:
    #             order.picking_ids.filtered(
    #                 lambda p: p.state not in ('done', 'cancel')
    #             ).action_cancel()
    #     return res
    
    def _create_picking(self):
        for order in self:
            if order.partner_id.is_forestry_company:
                return True
        return super()._create_picking()


class TimberLocation(models.Model):
    _name = 'lamello.timberlocation'
    _order = 'id desc'

    location_type = fields.Selection([
        ('store', 'Tárolóhely'),
        ('dryer', 'Szárító'),
        ('sawmill', 'Fűrészüzem'),
    ], string="Típus", required=True)

    location_scope = fields.Selection([
        ('internal', 'Belső'),
        ('external', 'Külső')
    ], default='internal', string="Elhelyezkedés", required=True)

    name = fields.Char("Név", store=True)
    address = fields.Char("Megnevezés", required=True)
    stock_location_id = fields.Many2one('stock.location', string="Kapcsolódó raktári hely", ondelete='restrict')
    stack_ids = fields.One2many("lamello.timberstack", "timber_location_id", string="Rakat", required=True, ondelete='cascade')
    to_manufacture = fields.Boolean("Gyártásba adás", default=False)

    @api.onchange('location_type')
    def _onchange_location_type(self):
        if self.location_type == 'sawmill':
            self.location_scope = 'external'

    @api.model_create_multi
    def create(self, vals_list):

        for vals in vals_list:
            if vals.get('location_type') == 'sawmill' and 'location_scope' not in vals:
                vals['location_scope'] = 'external'
            if vals.get('location_type'):
                address = vals.get('address', '')
                vals['name'] = address 
                location_type = vals.get('location_type', '')
                to_manufacture = vals.get('to_manufacture', False)
                type_dict = dict(self._fields['location_type'].selection)
                type_label = type_dict.get(location_type, '')
                location_name = f"{address} ({type_label})".strip()

                if location_type == 'sawmill':
                    usage = 'supplier'
                else:
                    usage = 'internal'

                if to_manufacture:
                    parent_ref = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                else:
                    parent_ref = self.env.ref('lamello_timber.location_timber_root', raise_if_not_found=False)

                parent_id = parent_ref.id if parent_ref else False

                stock_location_id = self.env['stock.location'].create({
                    'name': location_name,
                    'location_id': parent_id,
                    'usage': usage
                })
                vals['stock_location_id'] = stock_location_id.id

        return super(TimberLocation, self).create(vals_list)


    def write(self, vals):
        res = super(TimberLocation, self).write(vals)

        if any(k in vals for k in ['address', 'location_type', 'to_manufacture']):
            type_dict = dict(self._fields['location_type'].selection)

            for rec in self:
                if rec.stock_location_id:
                    address = rec.address
                    location_type = rec.location_type

                    location_name = f"{address} ({type_dict.get(location_type, '')})".strip()
                    usage = 'supplier' if location_type == 'sawmill' else 'internal'

                    if rec.to_manufacture:
                        parent_ref = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                    else:
                        parent_ref = self.env.ref('lamello_timber.location_timber_root', raise_if_not_found=False)

                    parent_id = parent_ref.id if parent_ref else False

                    rec.stock_location_id.write({
                        'name': location_name,
                        'usage': usage,
                        'location_id': parent_id,
                    })

        return res

    @api.constrains('location_type', 'to_manufacture', 'location_scope')
    def _check_location_constraints(self):
        for rec in self:
            if rec.location_type == 'store' and rec.to_manufacture and rec.location_scope == 'external':
                raise ValidationError("Külső tárhely esetén nem lehet gyártásba adni.")
            if rec.location_type == 'sawmill' and rec.location_scope != 'external':
                raise ValidationError("Fűrészüzem csak külső helyszín lehet.")
            if rec.location_type == 'dryer' and rec.location_scope != 'internal':
                raise ValidationError("Szárító csak belső helyszín lehet.")


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    ronkjegyzek_id = fields.Many2one(
        'lamello.ronkjegyzek', string="Rönkjegyzék", ondelete='set null'
    )


class Ronkjegyzek(models.Model):
    _name = 'lamello.ronkjegyzek'
    _description = "Rönkjegyzék"
    _order = 'id desc'

    state = fields.Selection([("open", "Nyitva"), ("confirmed", "Megerősítve"), ("closed", "Lezárva"), ("cancel", "Érvénytelenítve")], string="Állapot", copy=False, default="open")
    name = fields.Char('Sorszám', required=True, index='trigram', copy=False, default='Új rönkjegyzék')
    open_date = fields.Date("Nyitás dátuma", required=True, default=fields.Date.context_today)
    close_date = fields.Date("Zárás dátuma")
    description = fields.Html("Megjegyzés", sanitize=True)
    erdogazdasag_ids = fields.Many2many("res.partner", string='Beszállítók', compute="_compute_erdogazdasag_ids", domain=[('is_forestry_company', '=', True)])
    faronk_id = fields.Many2one("lamello.woodtype", string='Fatípus')
    purchase_date = fields.Date("Felvásárlás dátuma", required=True)
    expected_date = fields.Date("Várható beérkezés", required=True)

    faronk_line_ids = fields.One2many("lamello.faronkline", "ronkjegyzek_id", string='Tételek')

    # Kapcsolatok a folyamat többi lépéséhez (1:1 kapcsolat)
    ronkatvetel_id = fields.Many2one("lamello.ronkatvetel", string="Átvétel")
    ronkfeldolgozas_id = fields.Many2one("lamello.ronkfeldolgozas", string="Feldolgozás")
    purchase_order_ids = fields.One2many('purchase.order', 'ronkjegyzek_id', string="Beszerzési megrendelések")
    has_single_po = fields.Boolean(compute='_compute_has_single_po')
    has_multiple_partners = fields.Boolean(compute='_compute_has_multiple_partners')
    single_erdogazdasag_id = fields.Many2one('res.partner', compute='_compute_has_multiple_partners')

    # Összesítések
    m3 = fields.Float("m3", compute="_compute_osszesitesek", digits=(16, 3), store=True)
    db = fields.Integer("db", compute="_compute_osszesitesek", store=True)

    total_received_volume = fields.Float(string="Átvett térfogat (m3)", digits=(16, 3), compute="_compute_osszesitesek", store=True)
    total_received_quantity = fields.Integer(string="Átvett mennyiség (db)", compute="_compute_osszesitesek", store=True)

    total_processed_volume = fields.Float("Feldolgozott térfogat (m3)", compute="_compute_osszesitesek", digits=(16, 3), store=True)
    total_processed_quantity = fields.Integer(string="Feldolgozott mennyiség (db)", compute="_compute_osszesitesek", store=True)

    @api.depends('purchase_order_ids')
    def _compute_has_single_po(self):
        for rec in self:
            rec.has_single_po = len(rec.purchase_order_ids) == 1 or (len(rec.purchase_order_ids) == 0)

    @api.depends('purchase_order_ids.partner_id')
    def _compute_has_multiple_partners(self):
        for rec in self:
            partners = rec.purchase_order_ids.mapped('partner_id')
            rec.has_multiple_partners = len(partners) > 1
            rec.single_erdogazdasag_id = partners[0] if len(partners) == 1 else False

    @api.depends('purchase_order_ids.partner_id')
    def _compute_erdogazdasag_ids(self):
        for rec in self:
            rec.erdogazdasag_ids = rec.purchase_order_ids.mapped('partner_id')

    @api.depends('faronk_line_ids.m3', 'faronk_line_ids.atvett_m3', 'faronk_line_ids.received', 'faronk_line_ids.processed')
    def _compute_osszesitesek(self):
        for rec in self:
            lines = rec.faronk_line_ids
            rec.m3 = sum(lines.mapped('m3'))
            rec.db = len(lines)

            received_lines = lines.filtered(lambda l: l.received)
            rec.total_received_quantity = len(received_lines)
            rec.total_received_volume = sum(received_lines.mapped('atvett_m3'))

            processed_lines = lines.filtered(lambda l: l.processed)
            rec.total_processed_quantity = len(processed_lines)
            rec.total_processed_volume = sum(processed_lines.mapped('atvett_m3'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        # self.mapped('faronk_line_ids').write({'state': 'confirmed'})
        return True

    def action_transfer(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.ronkatvetel',
            'view_mode': 'form',
            'context': {
                'default_ronkjegyzek_id': self.id,
            }
        }

    def action_processing(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.ronkfeldolgozas',
            'view_mode': 'form',
            'context': {
                'default_ronkjegyzek_id': self.id,
            }
        }

    def action_close(self):
        self.write({
            'state': 'closed',
            'close_date': fields.Date.today()
        })

    def action_cancel(self):
        blocked = self.faronk_line_ids.filtered(lambda l: l.state in ('received', 'processed'))
        if blocked:
            tikketek = ', '.join(blocked.mapped('tikett'))
            raise UserError(_(
                "Nem érvényteleníthető: %(tikketek)s tételek már át lettek véve vagy feldolgozva.",
                tikketek=tikketek,
            ))
        self.mapped('faronk_line_ids').write({'state': 'cancel'})
        self.write({'state': 'cancel'})

    def action_create_new(self):
        new_rec = self.env['lamello.ronkjegyzek'].create({
            'faronk_id': self.faronk_id.id,
            'purchase_date': self.purchase_date,
            'expected_date': self.expected_date,
            'open_date': fields.Date.today(),
        })
        for line in self.faronk_line_ids:
            self.env['lamello.faronkline'].create({
                'ronkjegyzek_id': new_rec.id,
                'tikett': line.tikett,
                'hosszusag': line.hosszusag,
                'atmero': line.atmero,
                'po_id': line.po_id.id or False,
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.ronkjegyzek',
            'view_mode': 'form',
            'res_id': new_rec.id,
            'target': 'current',
        }

    @api.onchange('faronk_line_ids')
    def _onchange_faronk_line_ids(self):
        tikettek = [line.tikett for line in self.faronk_line_ids if line.tikett]
        if len(tikettek) != len(set(tikettek)):
            return {
                'warning': {
                    'title': "Duplikált tételek",
                    'message': "Ugyanaz a sorszám többször is szerepel a listában!",
                }
            }
        if self.faronk_line_ids:
            last_line = self.faronk_line_ids[-1]
            if last_line.tikett:
                exists = self.env['lamello.faronkline'].search_count([
                    ('tikett', '=', last_line.tikett),
                    ('id', '!=', last_line._origin.id)
                ])
                if exists > 0:
                    return {
                        'warning': {
                            'title': _("Hiba"),
                            'message': _("Ez a sorszám már létezik az adatbázisban!")
                        }
                    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új rönkjegyzék') == 'Új rönkjegyzék':
                vals['name'] = self.env['ir.sequence'].next_by_code('lamello.ronkjegyzek')
        return super().create(vals_list)


class FaronkLine(models.Model):
    _name = 'lamello.faronkline'
    _description = "Rönkjegyzék tételei"

    state = fields.Selection([
        # ("draft", "Vázlat"),
        # ("confirmed", "Megerősítve"),
        ("recorded", "Rögzítve"),
        ("received", "Átvéve"),
        ("processed", "Feldolgozva"),
        ("cancel", "Érvénytelenítve")
    ], string="Állapot", copy=False, default="recorded")

    elteres_m3 = fields.Float("Eltérés (m3)", digits=(16, 3), store=True, compute="_compute_difference")

    timber_location_id = fields.Many2one("lamello.timberlocation", string="Tárhely", ondelete='restrict')

    ronkjegyzek_id = fields.Many2one("lamello.ronkjegyzek", string="Rönkjegyzék", required=True, ondelete='cascade')
    po_id = fields.Many2one('purchase.order', string='Rendelés', ondelete='set null')
    po_partner_id = fields.Many2one('res.partner', related='po_id.partner_id', string='Szállító', store=False)
    tikett = fields.Char("Sorszám", required=True)

    hosszusag = fields.Float("Hosszúság (cm)", digits=(16, 3), required=True)
    atmero = fields.Float("Átmérő (cm)", digits=(16, 3), required=True)
    m3 = fields.Float("Térfogat (m3)", digits=(16, 3), compute="_compute_terfogat", store=True)

    # átvétel
    received = fields.Boolean("Átvett", default=False)
    transfer_date = fields.Date("Beszállítás dátuma")
    atvett_hosszusag = fields.Float(string="Átvett hosszúság (cm)", digits=(16, 3))
    atvett_atmero = fields.Float(string="Átvett átmérő (cm)", digits=(16, 3))
    atvett_m3 = fields.Float("Átvett térfogat (m3)", digits=(16, 3))

    # feldolgozás
    processed = fields.Boolean("Feldolgozva", default=False)
    processed_date = fields.Date("Feldolgozás dátuma")

    @api.depends("received", "atvett_m3", "m3")
    def _compute_difference(self):
        for rec in self:
            if rec.received:
                rec.elteres_m3 = rec.atvett_m3 - rec.m3
            else:
                rec.elteres_m3 = 0.0

    @api.depends("hosszusag", "atmero")
    def _compute_terfogat(self):
        for rec in self:
            rec.m3 = rec.ronkjegyzek_id.faronk_id.calculate_log_volume(rec.atmero, rec.hosszusag)

    @api.constrains('tikett', 'state')
    def _check_tikett_unique(self):
        for rec in self:
            if rec.state == 'cancel':
                continue
            duplicate = self.env['lamello.faronkline'].search([
                ('tikett', '=', rec.tikett),
                ('state', '!=', 'cancel'),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_("Egy rönk sorszám csak egyszer szerepelhet! (%s)", rec.tikett))

    def unlink(self):
        blocked = self.filtered(lambda l: l.state in ('received', 'processed'))
        if blocked:
            tikketek = ', '.join(blocked.mapped('tikett'))
            raise UserError(_(
                "Nem törölhető: %(tikketek)s — csak 'Rögzítve' állapotú tételek törölhetők.",
                tikketek=tikketek,
            ))
        return super().unlink()


class RonkAtvetelTransferLine(models.Model):
    _name = 'lamello.ronkatveteltransferline'
    _description = "Rönkátvétel tételek"

    ronkatvetel_id = fields.Many2one("lamello.ronkatvetel", string="Rönkátvétel", required=True, ondelete='cascade')
    source_faronkline_id = fields.Many2one('lamello.faronkline', string="Eredeti rönk sor", readonly=True, ondelete='set null')

    tikett = fields.Char("Sorszám")
    hosszusag = fields.Float("Hosszúság (cm)", digits=(16, 3))
    atmero = fields.Float("Átmérő (cm)", digits=(16, 3))
    m3 = fields.Float("Térfogat (m3)", digits=(16, 3))

    atvett_hosszusag = fields.Float(string="Átvett hosszúság (cm)", digits=(16, 3))
    atvett_atmero = fields.Float("Átvett átmérő (cm)", digits=(16, 3))
    atvett_m3 = fields.Float("Átvett térfogat (m3)", digits=(16, 3))
    received = fields.Boolean("Átvett", default=False)
    transfer_date = fields.Date("Beszállítás dátuma")

    @api.onchange('atvett_hosszusag', 'atvett_atmero')
    def _onchange_atvett_meretek(self):
        for rec in self:
            if rec.atvett_hosszusag and rec.atvett_atmero:
                rec.atvett_m3 = rec.ronkatvetel_id.ronkjegyzek_id.faronk_id.calculate_log_volume(rec.atvett_atmero, rec.atvett_hosszusag)
            else:
                rec.atvett_m3 = 0.0


class RonkAtvetel(models.Model):
    _name = 'lamello.ronkatvetel'
    _description = "Rönkátvétel"
    _order = 'id desc'

    state = fields.Selection([
        ("draft", "Vázlat"),
        ("approved", "Átvéve"),
        ("cancel", "Érvénytelenítve")
    ], string="Állapot", copy=False, default="draft")

    name = fields.Char("Sorszám", default="Új rönkátvétel")
    ronkjegyzek_id = fields.Many2one("lamello.ronkjegyzek", string="Rönkjegyzék", required=True, ondelete='cascade')
    date = fields.Date("Átvétel dátuma", required=True)
    timber_location_id = fields.Many2one("lamello.timberlocation", required=True, string="Tárhely", domain=[('location_type', '=', 'sawmill')], ondelete='restrict')
    delivery_note = fields.Char("Szállítólevél száma")

    transfer_line_ids = fields.One2many('lamello.ronkatveteltransferline', 'ronkatvetel_id', string="Átvett tételek")

    ronkjegyzek_name = fields.Char(related="ronkjegyzek_id.name")
    erdogazdasag_ids = fields.Many2many(related="ronkjegyzek_id.erdogazdasag_ids", readonly=True)
    faronk_id = fields.Many2one(related="ronkjegyzek_id.faronk_id")
    description = fields.Html(related="ronkjegyzek_id.description")

    total_received_quantity = fields.Integer(string="Átvett mennyiség (db)", compute="_compute_totals", store=True)
    total_received_volume = fields.Float(string="Átvett térfogat (m3)", digits=(16, 3), compute="_compute_totals", store=True)

    @api.depends('transfer_line_ids.atvett_m3', 'transfer_line_ids.received')
    def _compute_totals(self):
        for rec in self:
            lines = rec.transfer_line_ids
            rec.total_received_quantity = len(lines)
            rec.total_received_volume = sum(lines.mapped('atvett_m3'))

    @api.onchange('ronkjegyzek_id')
    def _onchange_ronkjegyzek_id(self):
        if self.state != 'draft':
            return

        if not self.ronkjegyzek_id:
            self.transfer_line_ids = [fields.Command.clear()]
            return

        source_lines = self.ronkjegyzek_id.faronk_line_ids.filtered(
            lambda l: l.state == 'recorded'
        )

        if not source_lines:
            self.ronkjegyzek_id = False
            return {
                'warning': {
                    'title': _("Nincs átvehető tétel!"),
                    'message': _(
                        "A kiválasztott rönkjegyzékben nincs olyan tétel, "
                        "amely 'Rögzítve' állapotban lenne."
                    ),
                    'type': 'notification',
                }
            }

        new_lines = [fields.Command.clear()]
        for line in source_lines:
            new_lines.append(fields.Command.create({
                'source_faronkline_id': line.id,
                'tikett': line.tikett,
                'hosszusag': line.hosszusag,
                'atmero': line.atmero,
                'm3': line.m3,
                'atvett_hosszusag': line.hosszusag,
                'atvett_atmero': line.atmero,
                'atvett_m3': line.m3,
                'received': True,
                'transfer_date': self.date or fields.Date.today(),
            }))
        self.transfer_line_ids = new_lines

    def action_confirm(self):
        self.ensure_one()
        for line in self.transfer_line_ids:
            _logger.info("Feldolgozott sor ID: %s", line.source_faronkline_id.id)
            if line.source_faronkline_id:
                line.source_faronkline_id.write({
                    'received': True,
                    'atvett_hosszusag': line.atvett_hosszusag,
                    'atvett_atmero': line.atvett_atmero,
                    'atvett_m3': line.atvett_m3,
                    'transfer_date': self.date,
                    'timber_location_id': self.timber_location_id.id,
                    'state': 'received',
                })
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_create_new(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.ronkatvetel',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_ronkjegyzek_id': self.ronkjegyzek_id.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új rönkátvétel') == 'Új rönkátvétel':
                vals['name'] = self.env['ir.sequence'].next_by_code('lamello.ronkatvetel')
        return super().create(vals_list)
    

class ProcessingLine(models.Model):
    _name = 'lamello.processingline'
    _description = "Feldolgozás tételek"

    ronkfeldolgozas_id = fields.Many2one("lamello.ronkfeldolgozas", string="Rönkfeldolgozás", required=True, ondelete='cascade')
    source_faronkline_id = fields.Many2one('lamello.faronkline', string="Eredeti rönk sor", readonly=True, ondelete='set null')

    tikett = fields.Char("Sorszám")
    atvett_hosszusag = fields.Float(string="Átvett hosszúság (cm)", digits=(16, 3))
    atvett_atmero = fields.Float("Átvett átmérő (cm)", digits=(16, 3))
    atvett_m3 = fields.Float("Átvett térfogat (m3)", digits=(16, 3))


class RonkFeldolgozas(models.Model):
    _name = 'lamello.ronkfeldolgozas'
    _description = "Rönkfeldolgozás"
    _order = 'id desc'

    state = fields.Selection([
        ("draft", "Vázlat"),
        ("approved", "Feldolgozva"),
        ("cancel", "Érvénytelenítve")
    ], string="Állapot", copy=False, default="draft")

    name = fields.Char("Sorszám", default="Új rönkfeldolgozás")
    ronkjegyzek_id = fields.Many2one("lamello.ronkjegyzek", string="Rönkjegyzék", required=True, ondelete='cascade')
    date = fields.Date("Feldolgozás dátuma", required=True)

    processing_line_ids = fields.One2many('lamello.processingline', 'ronkfeldolgozas_id', string="Feldolgozott tételek")

    ronkjegyzek_name = fields.Char(related="ronkjegyzek_id.name")
    erdogazdasag_ids = fields.Many2many(related="ronkjegyzek_id.erdogazdasag_ids", readonly=True)
    faronk_id = fields.Many2one(related="ronkjegyzek_id.faronk_id")
    description = fields.Html(related="ronkjegyzek_id.description")

    total_processed_quantity = fields.Integer(string="Feldolgozott mennyiség (db)", compute="_compute_totals", store=True)
    total_processed_volume = fields.Float(string="Feldolgozott térfogat (m3)", digits=(16, 3), compute="_compute_totals", store=True)

    @api.depends('processing_line_ids.atvett_m3')
    def _compute_totals(self):
        for rec in self:
            lines = rec.processing_line_ids
            rec.total_processed_quantity = len(lines)
            rec.total_processed_volume = sum(lines.mapped('atvett_m3'))

    @api.onchange('ronkjegyzek_id')
    def _onchange_ronkjegyzek_id(self):
        if self.state != 'draft':
            return

        if not self.ronkjegyzek_id:
            self.processing_line_ids = [fields.Command.clear()]
            return

        source_lines = self.ronkjegyzek_id.faronk_line_ids.filtered(lambda l: l.state == 'received')

        new_lines = [fields.Command.clear()]
        for line in source_lines:
            new_lines.append(fields.Command.create({
                'source_faronkline_id': line.id,
                'tikett': line.tikett,
                'atvett_hosszusag': line.atvett_hosszusag,
                'atvett_atmero': line.atvett_atmero,
                'atvett_m3': line.atvett_m3,
            }))
        self.processing_line_ids = new_lines

    def action_confirm(self):
        self.ensure_one()
        for line in self.processing_line_ids:
            _logger.info("Feldolgozott sor ID: %s", line.source_faronkline_id.id)
            if line.source_faronkline_id:
                line.source_faronkline_id.write({
                    'processed': True,
                    'processed_date': self.date,
                    'state': 'processed',
                })
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_create_new(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.ronkfeldolgozas',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_ronkjegyzek_id': self.ronkjegyzek_id.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új rönkfeldolgozás') == 'Új rönkfeldolgozás':
                vals['name'] = self.env['ir.sequence'].next_by_code('lamello.ronkfeldolgozas')
        return super().create(vals_list)


class TimberStack(models.Model):
    _name = 'lamello.timberstack'
    _description = "Fűrészárú rakat"
    _order = 'id'

    state = fields.Selection([
        ("draft", "Vázlat"),
        ("approved", "Jóváhagyva"),
        ("received", "Átvéve"),
        ("processing", "Szárítóban"),
        ("done", "Kezelt"),
        ("to_manufacture", "Gyártásba adva"),
        ("cancel", "Érvénytelenítve")
    ], string="Állapot", copy=False, default="draft")

    wood_type_id = fields.Many2one("lamello.woodtype", string="Fatípus", store=True, compute="_compute_wood_type")
    name = fields.Char("Sorszám", default="Új rakat", compute="_compute_name", store=True)
    stack_number = fields.Char("Rakat sorszáma", required=True)
    stack_list_id = fields.Many2one("lamello.timberstack.list", string="Rakatjegyzék")
    
    is_purchased = fields.Boolean("Vásárolt", compute="_compute_is_purchased", store=True, readonly=False)
    is_processed = fields.Boolean("Kezelt", default=False)
    is_received = fields.Boolean("Átvett", default=False)

    dryer_in_date = fields.Date("Szárítóba helyezés dátuma")
    dryer_out_date = fields.Date("Szárítóból kivétel dátuma")

    timber_location_id = fields.Many2one("lamello.timberlocation", string="Tárhely", ondelete='restrict')
    timber_stack_picking_id = fields.Many2one('lamello.timberstack.picking', string="Rakat mozgatás", ondelete='set null')
    
    total_volume = fields.Float("Teljes térfogat (m3)", digits=(16, 3), compute="_compute_total_volume", store=True)
    received_volume = fields.Float("Átvett térfogat (m3)", digits=(16, 3))
    
    thickness = fields.Float("Vastagság (cm)", aggregator=None)
    average_width = fields.Float("Átlagos szélesség (cm)", digits=(16, 1))
    length = fields.Float("Hosszúság (cm)", digits=(16, 1))
    quantity = fields.Integer("Darab")


    @api.depends('stack_number')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.stack_number or "Új rakat"

    def change_location(self, timber_location_id):
        loc_type = timber_location_id.location_type
        to_manufacture = timber_location_id.to_manufacture
        for rec in self:
            if to_manufacture:
                rec.state = 'to_manufacture'
            elif loc_type == 'dryer':
                rec.state = 'processing'
                rec.is_received = True
            elif rec.state == 'processing' and loc_type == 'store':
                rec.state = 'done'
                rec.is_processed = True
                rec.is_received = True
            elif rec.is_processed and rec.state == 'approved':
                rec.state = 'done'
                rec.is_received = True
            elif rec.is_processed and loc_type == 'store':
                rec.state = 'done'
            elif not rec.is_processed and loc_type == 'store':
                rec.state = 'received'
                rec.is_received = True
            rec.timber_location_id = timber_location_id

    @api.depends('stack_list_id.source_document')
    def _compute_is_purchased(self):
        for rec in self:
            if rec.stack_list_id.source_document:
                rec.is_purchased = rec.stack_list_id.source_document._name == 'purchase.order'
            else:
                rec.is_purchased = False

    @api.depends('stack_list_id.wood_type_id')
    def _compute_wood_type(self):
        for rec in self:
            rec.wood_type_id = rec.stack_list_id.wood_type_id

    @api.depends('length', 'thickness', 'average_width', 'quantity')
    def _compute_total_volume(self):
        for rec in self:
            l = rec.length or 0.0
            t = rec.thickness or 0.0
            w = rec.average_width or 0.0
            q = rec.quantity or 0
            rec.total_volume = (l * t * w * q) / 1_000_000

    def action_open_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_approve(self):
        self.write({'state': 'approved'})
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_delete(self):
        if any(r.state != 'cancel' for r in self):
            raise UserError(_("Csak érvénytelenített rakat törölhető."))
        self.unlink()

    # def action_approve(self):
    #     self.write({'state': 'approved'})
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'soft_reload',
    #     }

    # def action_cancel(self):
    #     self.write({'state': 'cancel'})
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'soft_reload',
    #     }

    # def action_draft(self):
    #     self.write({'state': 'draft'})
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'soft_reload',
    #     }

    @api.constrains('thickness')
    def _check_thickness(self):
        for rec in self:
            if rec.thickness <= 0:
                raise ValidationError("A rakat vastagságának nagyobbnak kell lennie 0-nál!")
    
    @api.constrains('stack_number', 'stack_list_id')
    def _check_stack_number_unique_in_list(self):
        for rec in self:
            if not rec.stack_number:
                raise ValidationError("A rakat sorszáma kötelező!")
            domain = [
                ('stack_number', '=', rec.stack_number),
                ('id', '!=', rec.id),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f"A(z) '{rec.stack_number}' sorszámú rakat már szerepel a nyilvántartásban!"
                )

    @api.onchange('stack_number')
    def _onchange_stack_number(self):
        _logger.info('*** _onchange_stack_number called with stack_number: %s', self.stack_number)
        if not self.stack_number:
            return
        
        domain = [('stack_number', '=', self.stack_number)]
        if self.id and not isinstance(self.id, models.NewId):
            domain.append(('id', '!=', self.id))
        
        if self.env['lamello.timberstack'].search_count(domain):
            raise UserError(
                f"A(z) '{self.stack_number}' sorszámú rakat már szerepel a nyilvántartásban!"
            )
        
    def write(self, vals):
        _logger.info('*** TimberStack write: %s', vals)
        return super().write(vals)

    _sql_constraints = [
        ("stack_number_unique", "unique(stack_number)", "Ez a rakat sorszám már létezik!")
    ]


# class TimberStackLine(models.Model):
#     _name = 'lamello.timberstack.line'
#     _description = "Rakat tétel"
#
#     timber_stack_id = fields.Many2one("lamello.timberstack", string="Rakat", required=True, ondelete='cascade')
#     length = fields.Float("Hosszúság (cm)")
#     stack_thickness = fields.Float(related="timber_stack_id.thickness", string="Vastagság (cm)")
#     width = fields.Float("Szélesség (cm)")
#     quantity = fields.Integer("Darab")
#     volume = fields.Float("Térfogat (m3)", digits=(16, 3), compute="_compute_volume", store=True)
#
#     @api.depends("length", "stack_thickness", "width", "quantity")
#     def _compute_volume(self):
#         for rec in self:
#             l = rec.length or 0.0
#             t = rec.stack_thickness or 0.0
#             w = rec.width or 0.0
#             q = rec.quantity or 0
#             rec.volume = (l * t * w * q) / 1_000_000


class TimberStackList(models.Model):
    _name = 'lamello.timberstack.list'
    _description = 'Rakatjegyzék'
    _order = 'id desc'

    name = fields.Char("Referencia", default="Új rakatjegyzék")
    state = fields.Selection([
        ("open", "Nyitva"),
        ("confirmed", "Megerősítve"),
        ("closed", "Lezárva"),
        ("cancel", "Érvénytelen")
    ], string="Állapot", copy=False, default="open")
    open_date = fields.Date("Nyitás dátuma", required=True, default=fields.Date.context_today)
    close_date = fields.Date("Zárás dátuma")
    source_document = fields.Reference(
        selection=[
            ('lamello.ronkjegyzek', 'Rönkjegyzék'),
            ('purchase.order', 'Beszerzési megrendelés')
        ],
        string="Forrás dokumentum", required=True
    )
    timber_stack_ids = fields.One2many('lamello.timberstack', 'stack_list_id', string="Rakatok")
    wood_type_id = fields.Many2one("lamello.woodtype", string="Fatípus", ondelete='restrict')
    total_volume = fields.Float(string="Összes térfogat (m3)", digits=(16, 3), compute="_compute_totals", store=True)
    total_quantity = fields.Integer(string="Összes rakat (db)", compute="_compute_totals", store=True)
    description = fields.Text(string="Megjegyzés")

    erdogazdasag_ids = fields.Many2many('res.partner', compute='_compute_erdogazdasag_ids', string='Beszállítók')
    single_erdogazdasag_id = fields.Many2one('res.partner', compute='_compute_erdogazdasag_ids', string='Beszállító')
    has_multiple_partners = fields.Boolean(compute='_compute_erdogazdasag_ids')

    @api.depends('source_document')
    def _compute_erdogazdasag_ids(self):
        for rec in self:
            partners = self.env['res.partner']
            if rec.source_document:
                if rec.source_document._name == 'lamello.ronkjegyzek':
                    partners = rec.source_document.purchase_order_ids.mapped('partner_id')
                elif rec.source_document._name == 'purchase.order':
                    partners = rec.source_document.partner_id
            rec.erdogazdasag_ids = partners
            rec.has_multiple_partners = len(partners) > 1
            rec.single_erdogazdasag_id = partners[0] if len(partners) == 1 else False

    @api.depends('timber_stack_ids.total_volume')
    def _compute_totals(self):
        for rec in self:
            rec.total_volume = sum(rec.timber_stack_ids.mapped('total_volume'))
            rec.total_quantity = len(rec.timber_stack_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új rakatjegyzék') == 'Új rakatjegyzék':
                vals['name'] = self.env['ir.sequence'].next_by_code('lamello.timberstack.list')
        return super().create(vals_list)

    def action_close(self):
        self.write({
            'state': 'closed',
            'close_date': fields.Date.context_today(self),
        })
        return True

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        return True

    def action_new(self):
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True

    def write(self, vals):
        _logger.info('*** TimberStackList write')
        _logger.info(vals)
        return super().write(vals)

    @api.onchange('source_document')
    def _onchange_source_document(self):
        if not self.source_document:
            return
        if self.source_document._name == 'lamello.ronkjegyzek':
            if self.source_document.faronk_id:
                self.wood_type_id = self.source_document.faronk_id


# class TimberStackPickingLine(models.Model):
#     _name = 'lamello.timberstack.picking.line'
#     _description = "Rakat mozgatás tétel"

#     timber_stack_picking_id = fields.Many2one('lamello.timberstack.picking', string="Rakat mozgatás", required=True, ondelete='cascade')
#     timber_stack_id = fields.Many2one('lamello.timberstack', string="Rakat", required=True, ondelete='restrict')
#     total_volume = fields.Float("Teljes térfogat (m3)", digits=(16, 3), related="timber_stack_id.total_volume", readonly=True)
#     quantity = fields.Float("Mennyiség (m3)", digits=(16, 3), required=True)


class TimberStackPickingLine(models.Model):
    _name = 'lamello.timberstack.picking.line'
    _description = "Rakat mozgatás tétel"

    timber_stack_picking_id = fields.Many2one('lamello.timberstack.picking', string="Rakat mozgatás", required=True, ondelete='cascade')
    timber_stack_id = fields.Many2one('lamello.timberstack', string="Rakat", required=True, ondelete='restrict')
    wood_type_id = fields.Many2one("lamello.woodtype", string="Fatípus", related="timber_stack_id.wood_type_id", readonly=True)
    total_volume = fields.Float("Teljes térfogat (m3)", digits=(16, 3), related="timber_stack_id.total_volume", readonly=True)
    quantity = fields.Float("Mennyiség (m3)", digits=(16, 3), required=True)

    @api.onchange('timber_stack_id')
    def _onchange_timber_stack_id(self):
        if self.timber_stack_id:
            self.quantity = self.timber_stack_id.total_volume

    @api.constrains('timber_stack_id', 'timber_stack_picking_id')
    def _check_unique_stack_in_picking(self):
        for rec in self:
            domain = [
                ('timber_stack_id', '=', rec.timber_stack_id.id),
                ('timber_stack_picking_id', '=', rec.timber_stack_picking_id.id),
                ('id', '!=', rec.id),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f"A(z) '{rec.timber_stack_id.name}' rakat már szerepel ebben a mozgatásban!"
                )


class TimberStackPicking(models.Model):
    _name = 'lamello.timberstack.picking'
    _description = 'Rakat mozgatás'
    _order = 'id desc'

    picking_type = fields.Selection([
        ('receipt', 'Átvétel'),
        ('internal', 'Átmozgatás'),
        ('dryer-in', 'Szárítóba be'),
        ('dryer-out', 'Szárítóból ki'),
        ('to_manufacture', 'Gyártásba adás'),
    ], string='Művelet típusa', required=True, compute="_compute_picking_type", store=True)

    state = fields.Selection([
        ('draft', 'Vázlat'),
        ('done', 'Kész'),
        ('cancel', 'Érvénytelenítve'),
    ], default='draft', string='Állapot', copy=False)


    name = fields.Char("Sorszám", default="Új rakat mozgatás")
    picking_date = fields.Date("Dátum", required=True, default=fields.Date.context_today)
    source_location_id = fields.Many2one('lamello.timberlocation', domain=[('location_type', 'in', ['store', 'dryer'])], string="Forrás hely")
    dest_location_id = fields.Many2one('lamello.timberlocation', domain=[('location_type', 'in', ['store', 'dryer'])], string="Cél hely")

    # timber_stack_ids helyett picking_line_ids
    picking_line_ids = fields.One2many('lamello.timberstack.picking.line', 'timber_stack_picking_id', string="Tételek")

    delivery_note = fields.Char("Szállítólevél száma")

    source_location_type = fields.Selection(related='source_location_id.location_type', string="Forrás hely típusa", readonly=True)
    dest_location_type = fields.Selection(related='dest_location_id.location_type', string="Cél hely típusa", readonly=True)

    processing_type = fields.Selection([
        ('drying', 'Szárítás'),
        ('steaming', 'Gőzölés'),
    ], string='Technológia')
    expected_date = fields.Date("Várható kiszedés")

    timber_stack_domain = fields.Json(
        compute='_compute_timber_stack_domain',
        store=False,
    )


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Új rakat mozgatás') == 'Új rakat mozgatás':
                vals['name'] = self.env['ir.sequence'].next_by_code('lamello.timberstack.picking') or 'Új rakat mozgatás'
        return super().create(vals_list)

    def action_confirm(self):
        _logger.info("*** Rakat mozgatás megerősítése: %s", self.name)
        
        for line in self.picking_line_ids:
            stack = line.timber_stack_id
            stack.change_location(self.dest_location_id)
            stack.received_volume = line.quantity

        self.write({'state': 'done'})

        # stock.picking létrehozása
        for rec in self:
            # Szárítóba/ki dátum beállítása
            for line in rec.picking_line_ids:
                if rec.picking_type == 'dryer-in':
                    line.timber_stack_id.dryer_in_date = rec.picking_date
                elif rec.picking_type == 'dryer-out' or (rec.picking_type == 'to_manufacture' and rec.source_location_type == 'dryer'):
                    line.timber_stack_id.dryer_out_date = rec.picking_date

            # Forrás location meghatározása
            if rec.source_location_id and rec.source_location_id.stock_location_id:
                source_stock_location = rec.source_location_id.stock_location_id
            else:
                # Ha nincs forrás, a Vendors (supplier) location legyen
                source_stock_location = self.env.ref('stock.stock_location_suppliers')

            # Cél location meghatározása
            dest_stock_location = rec.dest_location_id.stock_location_id

            if not dest_stock_location:
                raise ValidationError(
                    f"A(z) '{rec.dest_location_id.name}' célhelyszínhez nincs kapcsolódó raktári hely beállítva!"
                )

            # picking_type_id meghatározása
            # receiptnél: Receipts, egyébként: Internal Transfers
            if rec.picking_type == 'receipt':
                stock_picking_type = self.env.ref('stock.picking_type_in')
            else:
                stock_picking_type = self.env.ref('stock.picking_type_internal')

            _logger.info("Forrás stock location: %s, Cél stock location: %s, Picking type: %s", source_stock_location.name, dest_stock_location.name, stock_picking_type.name)

            # stock.picking létrehozása
            stock_picking = self.env['stock.picking'].create({
                'picking_type_id': stock_picking_type.id,
                'location_id': source_stock_location.id,
                'location_dest_id': dest_stock_location.id,
                'origin': rec.name,
                'state': 'draft',
            })

            _logger.info("Létrehozott stock.picking: %s", stock_picking.name)
            _logger.info(stock_picking)

            # stock.move létrehozása soronként
            for line in rec.picking_line_ids:
                stack = line.timber_stack_id
                product = stack.stack_list_id.wood_type_id.timber_stack_product_id

                if not product:
                    raise ValidationError(
                        f"A(z) '{stack.name}' rakathoz tartozó fatípushoz nincs termék beállítva!"
                    )

                self.env['stock.move'].create({
                    'description_picking': stack.name,
                    'picking_id': stock_picking.id,
                    'product_id': product.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': product.uom_id.id,
                    'location_id': source_stock_location.id,
                    'location_dest_id': dest_stock_location.id,
                })

            # stock.picking véglegesítése (done státusz)
            stock_picking.action_confirm()
            stock_picking.action_assign()
            
            for move in stock_picking.move_ids:
                if not move.move_line_ids:
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'picking_id': stock_picking.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'quantity': move.product_uom_qty,
                        'location_id': source_stock_location.id,
                        'location_dest_id': dest_stock_location.id,
                    })
                else:
                    for move_line in move.move_line_ids:
                        move_line.quantity = move_line.quantity_product_uom

            stock_picking.button_validate()

        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True

    @api.depends('source_location_id', 'dest_location_id', 'state')
    def _compute_picking_type(self):
        for rec in self:
            if rec.state != 'done':
                continue
            if rec.source_location_id.location_scope == 'external' and rec.dest_location_id.location_scope == 'internal':
                rec.picking_type = 'receipt'
            elif rec.source_location_id and rec.dest_location_id:
                if rec.dest_location_id.to_manufacture:
                    rec.picking_type = 'to_manufacture'
                elif rec.source_location_type == 'store' and rec.dest_location_type == 'dryer':
                    rec.picking_type = 'dryer-in'
                elif rec.source_location_type == 'dryer' and rec.dest_location_type == 'store':
                    rec.picking_type = 'dryer-out'
                else:
                    rec.picking_type = 'internal'


    @api.model
    def action_open_from_stacks(self, stack_ids, picking_type):
        context_extra = {}
        if picking_type == 'receipt':
            context_extra['default_is_receipt_action'] = True

        # stack_ids alapján picking line-ok létrehozása
        lines = [(0, 0, {'timber_stack_id': sid}) for sid in stack_ids]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lamello.timberstack.picking',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_picking_type': picking_type,
                'default_picking_line_ids': lines,
                **context_extra,
            },
        }

    @api.constrains('dest_location_id', 'processing_type', 'expected_date')
    def _check_dryer_fields(self):
        for rec in self:
            if rec.dest_location_type == 'dryer':
                if not rec.processing_type:
                    raise ValidationError("Szárítóba mozgatás esetén a technológia megadása kötelező!")
                if not rec.expected_date:
                    raise ValidationError("Szárítóba mozgatás esetén a várható kiszedési dátum megadása kötelező!")


class ReportRonkStatisztika(models.Model):
    _name = 'report.ronk.statisztika'
    _description = "Rönk Folyamat Statisztika"
    _auto = False
    _order = 'id desc'

    name = fields.Char('Rönkjegyzék', readonly=True)
    erdogazdasag_id = fields.Many2one('res.partner', string='Beszállító', readonly=True)
    faronk_id = fields.Many2one('lamello.woodtype', string='Fatípus', readonly=True)
    purchase_year = fields.Integer('Felvásárlási szezon')
    state = fields.Selection([
        ('open', 'Nyitva'),
        ('confirmed', 'Megerősítve'),
        ('closed', 'Lezárva')
    ], string='Állapot', readonly=True)

    tervezett_m3 = fields.Float('Névleges (m3)', readonly=True)
    atvett_m3 = fields.Float('Átvett (m3)', readonly=True)
    feldolgozott_m3 = fields.Float('Feldolgozott (m3)', readonly=True)
    stack_volume = fields.Float('Rakat (m3)', readonly=True)

    processed_percentage = fields.Float('Feldolgozott rönk %', readonly=True)
    atvett_feldolgozott = fields.Float('Átvett rönk - feldolgozott rönk (m3)', readonly=True)
    stack_received = fields.Float('Átvett rönk - rakat (m3)', readonly=True)
    performance = fields.Float('Rakat / átvett rönk %', readonly=True)

    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS %s CASCADE;
            DROP TABLE IF EXISTS %s CASCADE;
        """ % (self._table, self._table))
        
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    r.id                                                            AS id,
                    r.name                                                          AS name,
                    po_partner.partner_id                                           AS erdogazdasag_id,
                    r.faronk_id                                                     AS faronk_id,
                    DATE_PART('year', r.purchase_date)::integer                     AS purchase_year,
                    r.state                                                         AS state,
                    r.m3                                                            AS tervezett_m3,
                    r.total_received_volume                                         AS atvett_m3,
                    r.total_processed_volume                                        AS feldolgozott_m3,
                    COALESCE(SUM(lt.total_volume), 0)                               AS stack_volume,
                    CASE
                        WHEN r.total_received_volume = 0 THEN 0
                        ELSE (r.total_processed_volume / r.total_received_volume) * 100
                    END                                                             AS processed_percentage,
                    r.total_received_volume - r.total_processed_volume              AS atvett_feldolgozott,
                    CASE
                        WHEN r.m3 = 0 THEN 0
                        ELSE (COALESCE(SUM(lt.total_volume), 0) / r.m3) * 100
                    END                                                             AS stack_percentage,
                    r.total_received_volume - COALESCE(SUM(lt.total_volume), 0)     AS stack_received,
                    CASE
                        WHEN r.total_received_volume = 0 THEN 0
                        ELSE (COALESCE(SUM(lt.total_volume), 0) / r.total_received_volume) * 100
                    END                                                             AS performance
                FROM lamello_ronkjegyzek r
                JOIN lamello_faronkline l
                    ON r.id = l.ronkjegyzek_id
                LEFT JOIN LATERAL (
                    SELECT po.partner_id
                    FROM purchase_order po
                    WHERE po.ronkjegyzek_id = r.id
                    LIMIT 1
                ) po_partner ON TRUE
                LEFT JOIN lamello_timberstack_list ltl
                    ON SPLIT_PART(ltl.source_document, ',', 1) = 'lamello.ronkjegyzek'
                    AND SPLIT_PART(ltl.source_document, ',', 2)::integer = r.id
                LEFT JOIN lamello_timberstack lt
                    ON lt.stack_list_id = ltl.id
                WHERE r.state IN ('confirmed', 'closed')
                GROUP BY
                    r.id,
                    r.name,
                    po_partner.partner_id,
                    r.faronk_id,
                    r.state,
                    r.m3,
                    r.total_received_volume,
                    r.total_processed_volume
            )
        """ % self._table)