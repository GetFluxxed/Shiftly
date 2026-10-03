"""Inventory journeys keep their immediate origin, including a cold checkpoint.

Real native screens/API/database; navigation and dialogs use the browser adapter.
"""
from playwright.sync_api import expect
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_counts import setup_stock, start, observe_all, post


def click(page, label):
    page.get_by_role('button', name=label, exact=True).first.click()


def cold_resume(page):
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()


def test_stock_count_review_and_history_backtrack_without_skipping(page, native_inventory):
    url, i = native_inventory; setup_stock(i); post(i, observe_all(i, start(i)))
    page.goto(url); click(page, 'View current inventory')
    click(page, 'View stock: White Quella. 13.25 kg'); click(page, 'Open last physical count')
    cold_resume(page)
    expect(page.get_by_role('button', name='Back to stock details', exact=True)).to_be_visible()
    click(page, 'View count entries')
    expect(page.get_by_role('button', name='Back to count review', exact=True)).to_be_visible()
    click(page, 'View White Quella · Shelf 1')
    click(page, 'Back to count entries')
    expect(page.get_by_role('heading', name='Count', exact=True)).to_be_visible()
    click(page, 'Back to count review')
    click(page, 'Back to stock details')
    expect(page.get_by_role('heading', name='Product stock.', exact=True)).to_be_visible()
    click(page, 'Back to current inventory'); click(page, 'Back to inventory')
    click(page, 'Begin Count'); click(page, 'Count history'); click(page, 'Open count 2026-09-25')
    click(page, 'View count entries'); click(page, 'View count comparison')
    # Reopening review from entries must return to entries, even though review
    # appeared earlier in this journey.
    click(page, 'Back to count entries'); click(page, 'Back to count review')
    click(page, 'Back to count history'); click(page, 'Back to count inventory')
    click(page, 'Back to inventory')
    click(page, 'Count history'); click(page, 'Open count 2026-09-25')
    click(page, 'Back to count history'); click(page, 'Back to inventory')
    expect(page.get_by_role('button', name='Open company catalog', exact=True)).to_be_visible()


def test_count_header_back_protects_draft_and_returns_to_start(page, native_inventory):
    url, i = native_inventory; setup_stock(i)
    page.goto(url); click(page, 'Begin Count'); click(page, 'Start store count')
    click(page, 'Count White Quella · Shelf 1')
    page.get_by_label('Container count', exact=True).fill('2')
    page.once('dialog', lambda dialog: dialog.dismiss())
    click(page, 'Back to count entries')
    expect(page.get_by_label('Container count', exact=True)).to_have_value('2')
    page.once('dialog', lambda dialog: dialog.accept())
    click(page, 'Back to count entries')
    expect(page.get_by_text('Not counted', exact=True)).to_be_visible()
    click(page, 'Count White Quella · Shelf 1')
    expect(page.get_by_label('Container count', exact=True)).to_have_value('0')
    page.get_by_label('Container count', exact=True).fill('1')
    click(page, 'Save count entry'); click(page, 'Review count')
    expect(page.get_by_role('button', name='View count entries', exact=True)).to_have_count(0)
    click(page, 'Submit for review')
    expect(page.get_by_role('button', name='Finalize inventory count', exact=True)).to_be_visible()
    click(page, 'Back to count entries'); click(page, 'Back to count inventory')
    click(page, 'Review open count')
    expect(page.get_by_role('button', name='View count entries', exact=True)).to_be_visible()
    click(page, 'Return to counting')
    expect(page.get_by_role('button', name='Count White Quella · Shelf 1', exact=True)).to_be_visible()
    click(page, 'Back to count review'); click(page, 'Back to count inventory')
    click(page, 'Back to inventory')
    expect(page.get_by_role('button', name='Begin Count', exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None


def test_shelf_create_and_product_create_cancel_keep_shelf_origin(page, native_inventory):
    url, i = native_inventory
    page.goto(url); click(page, 'Open shelves')
    page.get_by_label('New shelf name', exact=True).fill('Top shelf'); click(page, 'Create shelf')
    click(page, 'Create a company product'); click(page, 'Cancel and discard draft')
    expect(page.get_by_role('heading', name='Shelf details.', exact=True)).to_be_visible()
    click(page, 'Create a company product')
    page.get_by_label('Product name', exact=True).fill('Spoon')
    page.get_by_label('SKU', exact=True).fill('SPOON')
    click(page, 'Create product')
    expect(page.get_by_role('button', name='Save company product', exact=True)).to_be_visible()
    cold_resume(page)
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Spoon')
    click(page, 'Manage packages & barcodes'); click(page, 'Back to product')
    click(page, 'Back to shelf')
    expect(page.get_by_role('button', name='Assign Spoon', exact=True)).to_be_visible()
    click(page, 'Back to Open Shelves')
    expect(page.get_by_role('button', name='Open Top shelf', exact=True)).to_be_visible()
    click(page, 'Back to inventory')
    with i.connect() as db:
        assert db.execute('SELECT count(*) FROM inventory_shelf_products').fetchone()[0] == 0


def test_catalog_packages_and_scanned_product_keep_search_and_origin(page, native_inventory):
    url, i = native_inventory; setup_stock(i)
    page.goto(url); click(page, 'Open company catalog')
    page.get_by_label('Find a product or SKU', exact=True).fill('Quella'); click(page, 'Search catalog')
    click(page, 'View product: White Quella'); click(page, 'Manage packages & barcodes')
    cold_resume(page); click(page, 'Back to product'); click(page, 'Back to catalog')
    expect(page.get_by_label('Find a product or SKU', exact=True)).to_have_value('Quella')
    click(page, 'Scan product')
    page.get_by_label('Barcode or SKU', exact=True).fill('000184'); click(page, 'Look up code')
    click(page, 'View product'); click(page, 'Manage packages & barcodes')
    click(page, 'Back to product'); click(page, 'Back to scanner')
    expect(page.get_by_role('button', name='View product', exact=True)).to_be_visible()
    click(page, 'Back to scanner')
    expect(page.get_by_label('Barcode or SKU', exact=True)).to_have_value('000184')
    click(page, 'Back to catalog'); click(page, 'Back to inventory')


def test_unknown_scan_choices_and_unsaved_package_return_one_step(page, native_inventory):
    url, i = native_inventory; setup_stock(i)
    page.goto(url); click(page, 'Open company catalog'); click(page, 'Scan product')
    page.get_by_label('Barcode or SKU', exact=True).fill('NEW-CASE'); click(page, 'Look up code')
    click(page, 'Create new item')
    page.get_by_label('Product name', exact=True).fill('Unfinished ingredient')
    click(page, 'Back to code choices')
    expect(page.get_by_role('button', name='Create new item', exact=True)).to_be_visible()
    click(page, 'Create new item')
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Unfinished ingredient')
    click(page, 'Back to choices'); click(page, 'Create new item')
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Unfinished ingredient')
    click(page, 'Back to code choices')
    click(page, 'Add package to existing item'); click(page, 'Add package to White Quella')
    expect(page.get_by_label('Barcode (optional)', exact=True)).to_have_value('NEW-CASE')
    page.get_by_label('Package name', exact=True).fill('Unfinished case')
    cold_resume(page); click(page, 'Back to scanner')
    expect(page.get_by_role('heading', name='Add package to an existing item', exact=True)).to_be_visible()
    click(page, 'Add package to White Quella')
    expect(page.get_by_label('Package name', exact=True)).to_have_value('Unfinished case')
    click(page, 'Back to scanner'); click(page, 'Back to code choices'); click(page, 'Back to scanner')
    expect(page.get_by_label('Barcode or SKU', exact=True)).to_have_value('NEW-CASE')
    click(page, 'Back to catalog')
    with i.connect() as db:
        assert db.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1
