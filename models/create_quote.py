from openerp.osv import osv, fields
from phpserialize import serialize
from pprint import pprint as pp
from magento import API, Customer
from openerp.tools.translate import _


class SaleOrder(osv.osv):
    _inherit = 'sale.order'
    _columns = {
	'mage_quote_id': fields.integer('Cart2Quote ID'),
        'state': fields.selection([
	    ('quote', 'Quote'),
            ('sent', 'Quotation Sent'),
            ('draft', 'Draft'),
            ('cancel', 'Cancelled'),
            ('waiting_date', 'Waiting Schedule'),
            ('progress', 'Sales Order'),
            ('manual', 'Sale to Invoice'),
            ('shipping_except', 'Shipping Exception'),
            ('invoice_except', 'Invoice Exception'),
            ('done', 'Done'),
            ], 'Status', readonly=True, copy=False, help="Gives the status of the quotation or sales order.\
              \nThe exception status is automatically set when a cancel operation occurs \
              in the invoice validation (Invoice Exception) or in the picking list process (Shipping Exception).\
		\nThe 'Waiting Schedule' status is set when the invoice is confirmed\
               but waiting for the scheduler to run on the order date.", select=True),
	'related_phone': fields.related('partner_id', 'phone', type="char", string='Phone'),
	'quote_status': fields.selection([
		('1', 'Starting'),
		('10', 'Proposal created, not sent'),
		('20', 'Processing'),
		('21', 'Request Expired'),
		('50', 'Proposal Sent'),
		('50.100', 'Proposal Sent, created by Salesrep'),
		('50.200', 'Proposal Sent, Contact customer by Salesrep'),
		('50.300', 'Proposal Sent, Payment Pending'),
		('51', 'Proposal Expired'),
		('52', 'Proposal On Hold'),
		('52.100', 'Proposal on Hold - Quote is on hold'),
		('52.200', 'Proposal on Hold - Waiting on Supplier'),
		('53', 'Proposal Sent'),
		('40', 'Proposal Canceled'),
		('40.100', 'Proposal Canceled - Out of Stock'),
		('60', 'Proposal rejected'),
		('70', 'Proposal Accepted'),
		('71', 'Ordered'),
	], 'Quote Request Status'),
    }

    _defaults = {
	'quote_status': '10',
    }


    def send_quote_proposal(self, cr, uid, ids, context=None):
        integrator_obj = self.pool.get('mage.integrator')
        credentials = integrator_obj.get_external_credentials(cr, uid)

	sale = self.browse(cr, uid, ids[0])
	try:
	    with API(credentials['url'], credentials['username'], credentials['password']) as quote_api:
	        quote_api.call('c2q_quotation.send_proposal', [sale.mage_quote_id])

	    sale.quote_status = '50'
	except Exception, e:
	    raise osv.except_osv(_('Magento API Error!'),_(str(e)))

	return True

    
    def create_mage_customer(self, cr, uid, credentials, sale, partner, store_id, context=None):

	firstname, lastname = self.get_name_field(cr, uid, partner)
	try:
            with Customer(credentials['url'], credentials['username'], credentials['password']) as customer_api:
                customer = customer_api.create({'email': sale.order_email or partner.email or partner_id.partner_shipping_address.email,
					'firstname': firstname,
					'lastname': lastname,
					'website_id': store_id,
	        })
	        partner.external_id = customer
	        print 'Created Customer in Magento with ID: %s' % customer
		#This must be committed beause the email has already been pushed to Magento
		#If the process errors out at another step, the quote/customer will be stuck
		#Because the email was pushed to Magento but the ID is not known by Odoo

		#A quote must already be saved for this action to execute, so I see no harm here
		cr.commit()
	        return partner

	except Exception, e:
	    raise osv.except_osv(_('Magento API Error!'),_(str(e)))


    def get_shipping(self, cr, uid, sale):
        obj = self.pool.get('sale.order.line')
        line_ids = obj.search(cr, uid, [('order_id', '=', sale.id), '|',('product_id.product_tmpl_id.shipping_product', '=', True),('name', '=', 'Magento Shipping')])
        if not line_ids:
            return False
        line = obj.browse(cr, uid, line_ids[0])
        return line.price_subtotal


    def get_subtotal(self, cr, uid, sale):
        subtotal = sale.amount_untaxed
        shipping_amount = self.get_shipping(cr, uid, sale)
        if shipping_amount:
            subtotal -= shipping_amount

        return subtotal


    def get_shipping_cost(self, cr, uid, sale):
        shipping_amount = self.get_shipping(cr, uid, sale)
        if not shipping_amount:
            return 0.00

        return shipping_amount


    def prepare_mage_cart_quote_address(self, cr, uid, sale, address, address_type, partner, context=None):

	shipping_cost = self.get_shipping_cost(cr, uid, sale)
	subtotal = self.get_subtotal(cr, uid, sale)

	firstname, lastname = self.get_name_field(cr, uid, address)

	if not address.street2:
	    street = address.street
	else:
	    street = address.street + '\n' + address.street2

	vals = {
            'updated_at': sale.write_date,
            'created_at': sale.create_date,
            'save_in_address_book': '',
            'customer_id': partner.external_id,
            'customer_address_id': False,
            'address_type': address_type,
	    'company': address.parent_id.name if address.parent_id.is_company else address.company,
            'email': address.email,
            'firstname': firstname,
            'lastname': lastname,
            'street': street,
            'city': address.city,
	    'region': address.state_id.name,
	   # 'region_id': 18,
	    'postcode': address.zip,
            'country_id': address.country_id.code,
            'telephone':  address.phone,
            'same_as_billing':  '0',
            'shipping_method': '',
            'subtotal': subtotal,
            'base_subtotal': subtotal,
            'subtotal_with_discount': 0,
            'base_subtotal_with_discount': 0,
            'tax_amount': sale.amount_tax,
            'base_tax_amount': sale.amount_tax,
            'shipping_amount': shipping_cost,
            'base_shipping_amount': shipping_cost,
            'shipping_tax_amount': 0,
            'base_shipping_tax_amount': 0,
            'discount_amount': 0,
            'base_discount_amount': 0,
            'grand_total': sale.amount_total,
            'base_grand_total': sale.amount_total,
            'customer_notes': False,
	}

	return vals


    def prepare_mage_cart_quote_items(self, cr, uid, sale, context=None):
	items = []
	for sale_line in sale.order_line:
	    if not sale_line.product_id or sale_line.product_id.default_code == 'mage_shipping':
		continue

	    item = sale_line.product_id
	    if not item.external_id or item.external_id == 0:
	        raise osv.except_osv(_('User Error!'),_("You are adding product %s to a Magento Quote. This product is not Mapped!")%item.default_code)

	    d = {'product_id': item.external_id, 'qty': str(int(sale_line.product_uom_qty))}

	    vals = {
                'store_id': sale.mage_store.external_id,
                'product_id': item.external_id,
                'qty': int(sale_line.product_uom_qty),
		'attribute': serialize(d),
#                'attribute': 'a:2:{s:10:"product_id";i:1880;s:3:"qty";s:1:"8";}',
                'has_options': 0,
                'request_qty': int(sale_line.product_uom_qty),
                'owner_base_price': sale_line.price_unit,
                'original_price': sale_line.price_unit,
                'original_cur_price': sale_line.price_unit,
                'owner_cur_price': sale_line.price_unit,
	    }

	    items.append(vals)

	return items

    def get_name_field(self, cr, uid, address, context=None):
        if not address.firstname:
            name_data = address.name.split(' ')
            firstname = name_data[0]
            lastname = name_data[1] if len(name_data) > 1 else False
        else:
            firstname = address.firstname
            lastname = address.lastname

	return (firstname, lastname)


    def prepare_mage_cart_quote(self, cr, uid, credentials, sale):

	if not sale.mage_store:
	    raise osv.except_osv(_('User Error!'),_("You must specify a Magento Storeview in order to submit this quote!"))

	if not sale.partner_id.external_id or sale.partner_id.external_id == 0:

	    partner = self.create_mage_customer(cr, uid, credentials, sale, sale.partner_id, sale.mage_store.external_id)
	else:
	    partner = sale.partner_id

	shipping_address = sale.partner_shipping_id
	billing_address = sale.partner_invoice_id

	shipping_firstname, shipping_lastname = self.get_name_field(cr, uid, shipping_address)
	billing_firstname, billing_lastname = self.get_name_field(cr, uid, billing_address)

        shipping_cost = self.get_shipping_cost(cr, uid, sale)
        subtotal = self.get_subtotal(cr, uid, sale)

	vals = {
	    'updated_at': sale.write_date,
	    'created_at': sale.create_date,
            'increment_id': sale.name,
	    'company': sale.partner_id.name if sale.partner_id.is_company else billing_address.company or None,
            'is_quote': '1',
            'status': sale.quote_status,
	    'client_request': sale.note,
            'firstname': billing_firstname,
            'lastname': billing_lastname,
            'email': sale.order_email or sale.partner_id.email or sale.partner_shipping_id.email,
            'country_id': shipping_address.country_id.code,
            'telephone': billing_address.phone,
            'store_id': sale.mage_store.external_id,
	    'region':  billing_address.country_id.name,
	    'city': billing_address.city,
	    'postcode': billing_address.zip,
            'shipping_firstname': shipping_firstname,
            'shipping_lastname': shipping_lastname,
            'shipping_country_id': shipping_address.country_id.code,
            'shipping_telephone': shipping_address.phone or '',
	    'shipping_postcode': shipping_address.zip,
            'admin_user_id': sale.user_id.external_id,
            'imported': '0',
	    'shipping_base_price': '-1.000',
	    'currency': 'USD',
            'base_to_quote_rate': False,
            'expiry': False,
            'itemprice': '1',
            'base_subtotal': subtotal,
            'base_grand_total': sale.amount_total,
            'base_shipping_amount': shipping_cost,
            'base_tax_amount': sale.amount_tax,
            'shipping_amount': shipping_cost,
            'grand_total': sale.amount_total,
            'tax_amount': sale.amount_tax,
            'subtotal': subtotal,
            'subtotal_incl_tax': 0,
            'shipping_incl_tax': 0,
            'customer_id': partner.external_id,
	}

	vals['billing_address'] = self.prepare_mage_cart_quote_address(cr, uid, \
                sale, billing_address, 'billing', partner)

	vals['shipping_address'] = self.prepare_mage_cart_quote_address(cr, uid, \
		sale, shipping_address, 'shipping', partner)

	vals['items'] = self.prepare_mage_cart_quote_items(cr, uid, sale)

	vals.update(self.get_shipping_vals(cr, uid, sale))

	return vals


    def get_shipping_vals(self, cr, uid, sale):
	if not sale.carrier_id:
	    return {}
	carrier = sale.carrier_id
	vals = {
		'shipping_method_title': carrier.name,
		'shipping_carrier': carrier.mage_carrier_code,
		'shipping_description': carrier.mage_carrier_code + '-' + carrier.name,
		'shipping_carrier_title': carrier.mage_carrier_code,
		'shipping_code': carrier.mage_code,
	}
	return vals


    def convert_odoo_to_mage_quote(self, cr, uid, ids, context=None):
        integrator_obj = self.pool.get('mage.integrator')
        credentials = integrator_obj.get_external_credentials(cr, uid)

        sale = self.browse(cr, uid, ids[0])
	vals = self.prepare_mage_cart_quote(cr, uid, credentials, sale)
	self.send_mage_cart_quote(cr, uid, credentials, vals, sale)
	return True


    def send_mage_cart_quote(self, cr, uid, credentials, quote_vals, quote, context=None):
	try:
            with API(credentials['url'], credentials['username'], credentials['password']) as quote_api:
	        response = quote_api.call('sales_order.createquote', [quote_vals])

	    quote.name = response['quote_name']
	    quote.mage_quote_id = response['quote_id']
	except Exception, e:
	    raise osv.except_osv(_('Magento API Error!'),_(str(e)))

	return True
