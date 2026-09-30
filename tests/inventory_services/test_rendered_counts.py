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


def test_native_count_resume_partial_review_post_history(page,native_inventory):
    url,i=native_inventory;product,_=setup_stock(i)
    post(i,observe_all(i,start(i),amount='18'))
    page.set_viewport_size({'width':390,'height':844});page.goto(url)
    page.get_by_role('button',name='View current inventory',exact=True).click()
    expect(page.get_by_text('18 kg',exact=True)).to_be_visible()
    expect(page.get_by_text('SKU 000184',exact=False)).to_have_count(0)
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_role('button',name='Back to current inventory',exact=True).click()
    expect(page.get_by_text('18 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_label('Count date (YYYY-MM-DD)',exact=True).fill('2026-09-25')
    page.get_by_role('button',name='Start store count',exact=True).click()
    expect(page.get_by_text('Not counted',exact=True)).to_be_visible()
    page.get_by_role('button',name='Review count',exact=True).click()
    expect(page.get_by_role('button',name='Submit for review',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Back to count entries',exact=True).click()
    page.get_by_role('button',name='Count White Quella · Shelf 1',exact=True).click()
    page.get_by_label('Full containers',exact=True).fill('2')
    page.get_by_label('Combined net partial amount',exact=True).fill('1250')
    page.get_by_role('button',name='Grams',exact=True).click()
    expect(page.get_by_role('heading',name='This location: 13.25 kg',exact=True)).to_be_visible()
    screenshot(page,'count-entry-phone.png')
    page.get_by_role('button',name='Save count entry',exact=True).click()
    expect(page.get_by_text('Saved: 13.25 kg',exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='18'
    page.get_by_role('button',name='Back to current inventory',exact=True).click()
    expect(page.get_by_text('18 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Count inventory',exact=True).click()
    page.get_by_role('button',name='Resume count',exact=True).click()
    page.get_by_role('button',name='Review count',exact=True).click()
    expect(page.get_by_role('button',name='Back to current inventory',exact=True)).to_be_visible()
    expect(page.get_by_text('SKU 000184',exact=False)).to_have_count(0)
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    page.get_by_role('button',name='Back to count entries',exact=True).click()
    expect(page.get_by_text('Saved: 13.25 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Review count',exact=True).click()
    expect(page.get_by_text('Change: -4.75 kg',exact=True)).to_be_visible()
    page.get_by_role('button',name='Submit for review',exact=True).click()
    expect(page.get_by_role('button',name='Finalize inventory count',exact=True)).to_be_visible()
    screenshot(page,'count-review-phone.png')
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Finalize inventory count',exact=True).click()
    expect(page.get_by_text('Count finalized. Current inventory now shows these totals.',exact=True)).to_be_visible()
    page.get_by_role('button',name='View current inventory',exact=True).click()
    expect(page.get_by_text('13.25 kg',exact=True)).to_be_visible()
    screenshot(page,'current-inventory-phone.png')
    page.get_by_role('button',name='View stock: White Quella',exact=True).click()
    expect(page.get_by_text('2 full × 6 kg + 1250 g net partial',exact=True)).to_be_visible()
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
    page.get_by_role('button',name='None remaining — save zero',exact=True).click()
    expect(page.get_by_text('Saved: 0 kg',exact=True)).to_be_visible()
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
    page.get_by_label('Full containers',exact=True).fill('1')
    def lose_response(route):
        if route.request.method=='POST':
            response=route.fetch()
            assert response.status==200
            route.abort()
        else:route.continue_()
    page.route('**/api/mobile/inventory/counts/*/lines/*',lose_response,times=1)
    page.get_by_role('button',name='Save count entry',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('could not confirm')
    expect(page.get_by_label('Full containers',exact=True)).to_have_value('1')
    page.get_by_role('button',name='Save count entry',exact=True).click()
    expect(page.get_by_text('Saved: 6 kg',exact=True)).to_be_visible()
    with i.connect() as db:
        assert db.execute('SELECT version,quantity FROM inventory_count_lines').fetchone()==(2,6)
