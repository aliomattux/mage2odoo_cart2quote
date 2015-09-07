from openerp.osv import osv, fields



    def prepare_odoo_record_vals(self, cr, uid, job, record, storeview=False):
	partner_obj = self.pool.get('res.partner')

        if record['customer_id']:
            partner = partner_obj.get_or_create_order_customer(cr, uid, record)

	else:
	    record['customer_id'] = 0
	    partner = partner_obj.get_or_create_order_customer(cr, uid, record)

        invoice_address = partner_obj.get_or_create_partner_address(cr, uid, \
                record['billing_address'], partner,
        )

        if type(record['payment']) != dict:
	    raise osv.except_osv(_('Error!'),_(""))

        payment_method = self.get_mage_payment_method(cr, \
                uid, record['payment']
        )
        vals = {
                'mage_order_number': record['increment_id'],
#               'order_policy':
#               'note':
                'partner_invoice_id': invoice_address.id,
                'order_email': record['customer_email'],
                'partner_id': partner.id,
                'date_order': record['created_at'],
                'payment_method': payment_method.id,
#               'state':
#               'pricelist_id':
                'ip_address': record['x_forwarded_for'],
		'order_line': self.prepare_odoo_line_record_vals(cr, uid, job, record),
                'mage_order_total': record['grand_total'],
                'external_id': record['order_id'],
        }

	if storeview:
            if storeview.order_prefix:
                ordernumber = storeview.order_prefix + record['increment_id']

            else:
                ordernumber = record['increment_id']

            vals.update({'name': ordernumber,
                         'mage_store': storeview.id,
                         'warehouse_id': storeview.warehouse.id,
            })


        if record['shipping_method']:
	    shipping_record = {'code': record['shipping_method'],
				'label': record['shipping_description']
	    }
            delivery_method = self.get_mage_shipping_method( \
                    cr, uid, job, shipping_record
            )
            vals.update({'carrier_id': delivery_method.id})

        if record.get('shipping_address'):
            shipping_address = partner_obj.get_or_create_partner_address(cr, uid, \
                    record['shipping_address'], partner,
            )
            vals.update({'partner_shipping_id': shipping_address.id})

        if float(record.get('shipping_amount')):
            vals['order_line'].append(
                self.get_shipping_line_data_using_magento_data(
                cr, uid, record
                )
            )

        if float(record.get('discount_amount')):
            vals['order_line'].append(
                self.get_discount_line_data_using_magento_data(
                cr, uid, record
                )
            )
	return vals


    def prepare_odoo_line_record_vals(
        self, cr, uid, job, order, context=None
    ):
        """Make data for an item line from the magento data.
        This method decides the actions to be taken on different product types
        :return: List of data of order lines in required format
        """
        product_obj = self.pool.get('product.product')

        line_data = []
        for item in order['items']:
            if not item['parent_item_id']:

                # If its a top level product, create it
                values = {
                    'name': item['name'] or item['sku'],
                    'price_unit': float(item['price']),
   #                 'product_uom':
    #                    website_obj.get_default_uom(
     #                       cursor, user, context
      #              ).id,
                    'product_uom_qty': float(item['qty_ordered']),
                  #  'magento_notes': item['product_options'],
#                    'type': 'make_to_order',
                    'product_id': product_obj.get_or_create_odoo_record(
                                cr, uid, job, item['product_id'], item=item,
                    ).id
                }

		tax_percent = item['tax_percent']
                if order['tax_identification'] and tax_percent and float(tax_percent) > 0.001:
                    taxes = self.get_mage_taxes(cr, uid, order['tax_identification'], item)
                    values['tax_id'] = [(6, 0, taxes)]

                line_data.append((0, 0, values))

            # If the product is a child product of a bundle product, do not
            # create a separate line for this.
            if item['product_options'] and 'bundle_option' in item['product_options'] and \
                    item['parent_item_id']:
                continue

        return line_data
