from openerp.osv import osv, fields
from pprint import pprint as pp
from openerp.tools.translate import _
from datetime import datetime

DEFAULT_STATUS_FILTERS = ['processing']

class MageIntegrator(osv.osv_memory):

    _inherit = 'mage.integrator'

    def import_quotes(self, cr, uid, job, context=None):
        mappinglines = self._get_mappinglines(cr, uid, job.mapping.id)
        defaults = {}

        storeview_obj = self.pool.get('mage.store.view')
        store_ids = storeview_obj.search(cr, uid, [('do_not_import', '=', False)])
	for storeview in storeview_obj.browse(cr, uid, store_ids):
	    self.import_one_storeview_quotes(cr, uid, job, storeview, defaults, mappinglines)
	    storeview_obj.write(cr, uid, storeview.id, {'last_quote_import_datetime': datetime.utcnow()})
	    cr.commit()

	return True


    def import_one_storeview_quotes(self, cr, uid, job, storeview, defaults, mappinglines=False, context=None):

        filters = {
                'store_id': {'=':storeview.external_id},
#                'status': {'in': statuses}
        }

	sale_obj = self.pool.get('sale.order')

	order_data = self._get_job_data(cr, uid, job, 'oo_catalog_product.test', [])
#	quote_ids = [x['quote_id'] for x in order_data]

	for quote in order_data:
	    print quote
	    continue
#	    if quote['quote_id'] != '4215364':
#		continue

	    items = []
	    #Once we have the quote ids, we can call the built in Magento cart call
	    #The Cart2Quote api call is a joke and returns no useful information
	    #All the Cart2Quote is, is an simple Magento Cart in sales_flat_quote
#	    quote_info = self._get_job_data(cr, uid, job, 'cart.info', [quote['quote_id']])

	    #Combine the quote data with the custom data
#	    quote.update(quote_info)
	    pp(quote)


	    quote_ids = sale_obj.search(cr, uid, [('name', '=', quote['increment_id'])])
	    if quote_ids:
		print 'Found Already'
		continue

	    odoo_quote = self.process_one_order(cr, uid, job, \
		quote, storeview, defaults, mappinglines
	    )


