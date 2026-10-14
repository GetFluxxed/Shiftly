"""Rendered Reports inbox and production forecast journeys with a fake forecast provider."""
from uuid import uuid4

from playwright.sync_api import expect

from tests.inventory_services.test_production import submission
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_rendered_production import production, recipe, stocked_product


def test_reports_inbox_production_detail_and_advisory_forecast(page, native_inventory):
    url, i = native_inventory
    made = recipe(i, stocked_product(i), name='Pistachio base', amount='1')
    log = production(i).confirm(i.tokens['owner'], submission(i, made))
    requests = []

    def forecast(route):
        requests.append(route.request.method)
        route.fulfill(status=200, content_type='application/json', json={
            'storeId': i.stores[0],
            'status': 'ready',
            'forecast': {
                'id': str(uuid4()), 'logId': log['id'], 'asOf': '2026-09-30',
                'generatedAt': None, 'model': 'fake-provider', 'stale': False,
                'coverage': {'windowDays': 28, 'productionReports': 1, 'productionDays': 1,
                             'shiftReports': 0, 'truncated': False},
                'facts': {
                    'daily': [{'date': '2026-09-30', 'recipeId': made['id'],
                               'name': 'Pistachio base', 'batches': 2}],
                    'ingredients': [{'productId': log['ingredients'][0]['productId'],
                                     'name': log['ingredients'][0]['name'], 'baseUnit': 'kg',
                                     'quantity': log['ingredients'][0]['quantity'], 'usedAmount': '2.02'}],
                },
                'analysis': None,
            },
            'error': None,
        })

    page.route('**/api/mobile/production/forecast*', forecast)
    page.set_viewport_size({'width': 320, 'height': 760})
    page.goto(url + '/reports')
    expect(page.get_by_role('heading', name='Reports', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Report inbox', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Write a report', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Shift reports', exact=True)).to_be_visible()

    page.get_by_role('button', name='Write a report', exact=True).click()
    expect(page.get_by_role('button', name='Back to reports', exact=True)).to_be_visible()
    page.get_by_role('button', name='Back to reports', exact=True).click()
    page.get_by_role('button', name='Production reports', exact=True).click()
    expect(page.get_by_role('heading', name='Production forecast', exact=True)).to_be_visible()
    page.get_by_role('button', name='Show forecast', exact=True).click()
    expect(page.get_by_text('Forecasts need at least 7 production days.', exact=False)).to_be_visible()
    expect(page.get_by_text('2026-09-30 · Pistachio base · 2 batches', exact=True)).to_be_visible()
    expect(page.get_by_text('Cocoa powder · used 2.02 kg · available 2.02 kg', exact=True)).to_be_visible()
    assert requests == ['GET']  # Opening the view must never enqueue paid work.

    row = page.get_by_role('button', name='2026-09-29, 1 flavors, 2 batches', exact=False)
    expect(row).to_be_visible()
    row.click()
    expect(page.get_by_role('heading', name='Flavors and batches', exact=True)).to_be_visible()
    expect(page.get_by_text('Pistachio base', exact=True)).to_be_visible()
    expect(page.get_by_text('2 batches', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Ingredient deductions', exact=True)).to_be_visible()

    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        expect(page.get_by_role('heading', name='Production forecast', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_reports_accepts_real_read_only_forecast_envelope(page, native_inventory):
    url, _ = native_inventory
    page.goto(url + '/reports')
    page.get_by_role('button', name='Production reports', exact=True).click()
    page.get_by_role('button', name='Show forecast', exact=True).click()
    expect(page.get_by_role('button', name='Refresh forecast', exact=True)).to_be_visible()
    expect(page.get_by_text('response could not be verified', exact=False)).to_have_count(0)
