"""Real native counting screens, service permissions and durable PostgreSQL data."""
import os
from pathlib import Path
from playwright.sync_api import expect

from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_counts import setup_stock, fields, start, observe_all, post


def screenshot(page, name):
    if os.environ.get('INVENTORY_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(os.environ['INVENTORY_SCREENSHOT_DIR'])/name),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def _same_node(first, second):
    return first.evaluate('(node, current) => node.isSameNode(current)', second)


def test_count_entry_keeps_dirty_editor_mounted_through_sync_ack_and_reopen(page, native_inventory):
    url, i = native_inventory
    setup_stock(i)
    count = start(i)
    line = i.counts.lines(i.tokens['owner'], count['id'])['items'][0]
    page.set_viewport_size({'width': 390, 'height': 844})
    held = []
    page.route('**/api/mobile/inventory/counts/*/lines/*', lambda route: held.append(route), times=1)
    page.goto(url + f'/counts/{count["id"]}/line/{line["id"]}')
    expect(page.get_by_label('Container count', exact=True)).to_be_visible()
    page.get_by_label('Container count', exact=True).fill('1')
    with page.expect_request(lambda request: request.method == 'POST' and '/api/mobile/inventory/counts/' in request.url and '/lines/' in request.url):
        page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_test_id('count-entry-modal')).to_have_count(0)
    assert len(held) == 1
    page.get_by_role('button', name='All', exact=True).click()
    row = page.get_by_role('button', name='Count White Quella · Shelf 1', exact=True)
    expect(row).to_be_visible()
    row.click()
    expect(page.get_by_label('Waiting to sync', exact=True)).to_be_visible()
    pending_modal = page.get_by_test_id('count-entry-modal').element_handle()
    assert pending_modal is not None
    page.get_by_label('Container count', exact=True).fill('2')

    held.pop().continue_()
    expect(page.get_by_role('button', name='All saved entries synced', exact=True)).to_be_visible()
    expect(page.get_by_label('Container count', exact=True)).to_have_value('2')
    acknowledged_modal = page.get_by_test_id('count-entry-modal').element_handle()
    assert acknowledged_modal is not None and _same_node(pending_modal, acknowledged_modal)

    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Close count entry', exact=True).click()
    expect(row).to_be_visible()
    row.click()
    expect(page.get_by_label('Container count', exact=True)).to_have_value('1')
    reopened_modal = page.get_by_test_id('count-entry-modal').element_handle()
    assert reopened_modal is not None and not _same_node(acknowledged_modal, reopened_modal)
    with i.connect() as db:
        assert db.execute('SELECT version,quantity FROM inventory_count_lines').fetchone() == (2, 6)


def test_native_count_resume_partial_review_post_history(page,native_inventory):
    url,i=native_inventory;product,_=setup_stock(i)
    post(i,observe_all(i,start(i),amount='18'))
    page.set_viewport_size({'width':390,'height':844});page.goto(url)
    page.get_by_role('button',name='View current inventory',exact=True).click()
    expect(page.get_by_role('button',name='View stock: White Quella. 18 kg',exact=True).get_by_text('18',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='View stock: White Quella. 18 kg',exact=True).get_by_text('kg',exact=True)).to_be_visible()
    expect(page.get_by_text('SKU 000184',exact=False)).to_have_count(0)
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_role('button',name='Back to current inventory',exact=True).click()
    expect(page.get_by_role('button',name='View stock: White Quella. 18 kg',exact=True).get_by_text('18',exact=True)).to_be_visible()
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_label('Count date (YYYY-MM-DD)',exact=True).fill('2026-09-25')
    page.get_by_role('button',name='Start store count',exact=True).click()
    expect(page.get_by_role('button',name='Not counted',exact=True)).to_be_visible()
    expect(page.get_by_text('1 left to count',exact=True)).to_be_visible()
    review = page.get_by_role('button',name='Review count',exact=True)
    expect(review).to_contain_text('Review')
    review.click()
    expect(page.get_by_role('button',name='Submit for review',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Back to count entries',exact=True).click()
    page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).click()
    page.get_by_label('Container count',exact=True).fill('2')
    page.get_by_role('button',name='Add loose or partial',exact=True).click()
    page.get_by_label('Loose or partial',exact=True).fill('1250')
    page.get_by_role('radio',name='Grams',exact=True).click()
    expect(page.get_by_text('13.25 kg',exact=True)).to_be_visible()
    screenshot(page,'count-entry-phone.png')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.get_by_text('All products counted',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True)).to_have_count(0)
    page.get_by_role('button',name='All',exact=True).click()
    expect(page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).get_by_text('13.25 kg',exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='18'
    page.get_by_role('button',name='Back to count inventory',exact=True).click()
    page.get_by_role('button',name='Back to current inventory',exact=True).click()
    expect(page.get_by_role('button',name='View stock: White Quella. 18 kg',exact=True).get_by_text('18',exact=True)).to_be_visible()
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_role('button',name='Resume count',exact=True).click()
    page.get_by_role('button',name='All',exact=True).click()
    page.get_by_role('button',name='Review count',exact=True).click()
    expect(page.get_by_role('button',name='Back to count entries',exact=True)).to_be_visible()
    expect(page.get_by_text('SKU 000184',exact=False)).to_have_count(0)
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    page.get_by_role('button',name='Back to count entries',exact=True).click()
    expect(page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).get_by_text('13.25 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Review count',exact=True).click()
    expect(page.get_by_text('Change: -4.75 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Submit for review',exact=True).click()
    expect(page.get_by_role('button',name='Finalize inventory count',exact=True)).to_be_visible()
    screenshot(page,'count-review-phone.png')
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Finalize inventory count',exact=True).click()
    expect(page.get_by_text('Count finalized. Current inventory now shows these totals.',exact=True)).to_be_visible()
    page.get_by_role('button',name='View current inventory',exact=True).click()
    expect(page.get_by_role('button',name='View stock: White Quella. 13.25 kg',exact=True).get_by_text('13.25',exact=True)).to_be_visible()
    screenshot(page,'current-inventory-phone.png')
    page.get_by_role('button',name='View stock: White Quella. 13.25 kg',exact=True).click()
    expect(page.get_by_text('2 × Container [6 kg] + 1250 g loose',exact=True)).to_be_visible()
    page.get_by_role('button',name='Back to current inventory',exact=True).click()
    page.get_by_role('button',name='Count history',exact=True).click()
    expect(page.get_by_role('button',name='Open count 2026-09-25',exact=True)).to_have_count(2)
    expect(page.get_by_role('button',name='Back to current inventory',exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='13.25'


def test_native_crew_saves_zero_but_cannot_finalize(page,native_inventory):
    url,i=native_inventory;setup_stock(i)
    with i.connect() as db:db.execute("UPDATE account_store_memberships SET capabilities=ARRAY['inventory.view','counts.submit'] WHERE user_id=%s",(i.users['crew'],))
    page.set_viewport_size({'width':1024,'height':900});page.goto(url+'/?crew')
    page.get_by_role('button',name='Begin Count',exact=True).click()
    page.get_by_role('button',name='Start store count',exact=True).click()
    page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).click()
    page.get_by_role('button',name='Set count to zero',exact=True).click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_role('button',name='All',exact=True).click()
    expect(page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).get_by_text('0 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Review count',exact=True).click()
    page.get_by_role('button',name='Submit for review',exact=True).click()
    expect(page.get_by_text('An account with count-approval permission must finalize this count.',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='Finalize inventory count',exact=True)).to_have_count(0)
    screenshot(page,'count-review-tablet.png')
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None
    page.evaluate('window.__inventoryTest.lock()')
    expect(page.get_by_text('Workspace locked',exact=True)).to_be_visible()
    expect(page.get_by_text('White Quella',exact=True)).to_have_count(0)


def test_native_uncertain_save_can_recover_without_duplicate_observation(page,native_inventory):
    url,i=native_inventory;setup_stock(i);page.goto(url)
    page.get_by_role('button',name='Begin Count',exact=True).click()
    page.get_by_role('button',name='Start store count',exact=True).click()
    page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).click()
    page.get_by_label('Container count',exact=True).fill('1')
    def lose_response(route):
        if route.request.method=='POST':
            response=route.fetch()
            assert response.status==200
            route.abort()
        else:route.continue_()
    page.route('**/api/mobile/inventory/counts/*/lines/*',lose_response,times=1)
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.get_by_test_id('count-entry-modal')).to_have_count(0)
    page.get_by_role('button',name='Counts waiting to sync',exact=True).click()
    expect(page.get_by_text('Your entries are saved on this device. Keep Shiftly open with a connection to sync them before review.',exact=True)).to_be_visible()
    page.get_by_role('button',name='Sync now',exact=True).click()
    expect(page.get_by_role('button',name='Close saved counts',exact=True)).to_be_visible()
    page.get_by_role('button',name='Close saved counts',exact=True).click()
    expect(page.get_by_role('button',name='All saved entries synced',exact=True)).to_be_visible()
    page.get_by_role('button',name='All',exact=True).click()
    expect(page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).get_by_text('6 kg',exact=True)).to_be_visible()
    with i.connect() as db:
        assert db.execute('SELECT version,quantity FROM inventory_count_lines').fetchone()==(2,6)
