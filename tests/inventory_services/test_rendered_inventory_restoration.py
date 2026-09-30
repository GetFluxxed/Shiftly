"""Rendered native restoration checks backed by real inventory services.

The browser harness models app backgrounding and a cold process reload. Physical
device scroll restoration remains a separate acceptance check.
"""
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, setup_stock, start
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def resume_workspace(page):
    page.evaluate("window.__inventoryTest.lock()")
    expect(page.get_by_text("Workspace locked", exact=True)).to_be_visible()
    page.evaluate("window.__inventoryTest.retry()")


def test_new_product_draft_survives_warm_and_cold_resume_until_discard_or_create(page, native_inventory):
    url, inventory = native_inventory
    page.goto(url)
    page.get_by_role("button", name="Open company catalog", exact=True).click()
    page.get_by_role("button", name="Add product", exact=True).click()
    page.get_by_label("Product name", exact=True).fill("Restored cocoa")
    page.get_by_label("SKU", exact=True).fill("RESTORE-001")
    page.get_by_role("button", name="Kilograms", exact=True).click()
    page.get_by_label("Full container amount (kg)", exact=True).fill("6")

    resume_workspace(page)
    expect(page.get_by_label("Product name", exact=True)).to_have_value("Restored cocoa")
    expect(page.get_by_label("SKU", exact=True)).to_have_value("RESTORE-001")
    expect(page.get_by_label("Full container amount (kg)", exact=True)).to_have_value("6")

    page.evaluate("window.__workspaceTest.flush()")
    page.reload()
    expect(page.get_by_label("Product name", exact=True)).to_have_value("Restored cocoa")
    expect(page.get_by_label("SKU", exact=True)).to_have_value("RESTORE-001")
    with inventory.connect() as db:
        assert db.execute("SELECT count(*) FROM inventory_products").fetchone()[0] == 0

    page.get_by_role("button", name="Cancel and discard draft", exact=True).click()
    page.get_by_role("button", name="Add product", exact=True).click()
    expect(page.get_by_label("Product name", exact=True)).to_have_value("")
    expect(page.get_by_label("SKU", exact=True)).to_have_value("")

    page.get_by_label("Product name", exact=True).fill("Confirmed cocoa")
    page.get_by_label("SKU", exact=True).fill("RESTORE-002")
    page.get_by_role("button", name="Create product", exact=True).click()
    expect(page.get_by_role("button", name="Save company product", exact=True)).to_be_visible()
    with inventory.connect() as db:
        assert db.execute("SELECT name, sku FROM inventory_products").fetchone() == ("Confirmed cocoa", "RESTORE-002")


def test_count_entry_draft_survives_resume_and_new_server_line_discards_it(page, native_inventory):
    url, inventory = native_inventory
    setup_stock(inventory)
    count = start(inventory)
    line = inventory.counts.lines(inventory.tokens["owner"], count["id"])["items"][0]

    page.goto(url)
    page.get_by_role("button", name="Begin Count", exact=True).click()
    page.get_by_role("button", name="Resume count", exact=True).click()
    page.get_by_role("button", name="Count White Quella · Shelf 1", exact=True).click()
    page.get_by_label("Full containers", exact=True).fill("2")
    page.get_by_label("Combined net partial amount", exact=True).fill("1250")
    page.get_by_role("button", name="Grams", exact=True).click()
    expect(page.get_by_role("heading", name="This location: 13.25 kg", exact=True)).to_be_visible()

    resume_workspace(page)
    expect(page.get_by_label("Full containers", exact=True)).to_have_value("2")
    expect(page.get_by_label("Combined net partial amount", exact=True)).to_have_value("1250")
    expect(page.get_by_role("heading", name="This location: 13.25 kg", exact=True)).to_be_visible()

    page.evaluate("window.__workspaceTest.flush()")
    page.reload()
    expect(page.get_by_label("Full containers", exact=True)).to_have_value("2")
    expect(page.get_by_label("Combined net partial amount", exact=True)).to_have_value("1250")
    expect(page.get_by_role("heading", name="This location: 13.25 kg", exact=True)).to_be_visible()
    assert inventory.counts.stock(inventory.tokens["owner"])["items"][0]["quantity"] is None
    assert inventory.counts.line(inventory.tokens["owner"], count["id"], line["id"])["quantity"] is None

    inventory.counts.save(inventory.tokens["owner"], count["id"], line["id"], fields(
        inventory, version=line["version"], entry={"mode": "total", "amount": "4", "unit": "kg"}))
    resume_workspace(page)
    expect(page.get_by_label("Measured total", exact=True)).to_have_value("4")
    expect(page.get_by_text("Saved quantity: 4 kg", exact=True)).to_be_visible()
    expect(page.get_by_label("Full containers", exact=True)).to_have_count(0)
    assert inventory.counts.stock(inventory.tokens["owner"])["items"][0]["quantity"] is None


def test_catalog_search_and_state_filter_survive_detail_return_and_reload(page, native_inventory):
    url, inventory = native_inventory
    inventory.service.create_product(inventory.tokens["owner"], fields(
        inventory, name="Active cocoa", sku="ACTIVE-001", baseUnit="kg"))
    archived = inventory.service.create_product(inventory.tokens["owner"], fields(
        inventory, name="Archived cocoa", sku="ARCHIVE-001", baseUnit="kg"))
    inventory.service.product_state(inventory.tokens["owner"], archived["id"], fields(
        inventory, version=archived["version"], active=False))

    page.goto(url)
    page.get_by_role("button", name="Open company catalog", exact=True).click()
    page.get_by_role("button", name="Archived", exact=True).click()
    page.get_by_label("Find a product or SKU", exact=True).fill("Archived cocoa")
    page.get_by_role("button", name="Search catalog", exact=True).click()
    expect(page.get_by_role("button", name="View product: Archived cocoa", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="View product: Active cocoa", exact=True)).to_have_count(0)

    page.get_by_role("button", name="View product: Archived cocoa", exact=True).click()
    page.get_by_role("button", name="Back to catalog", exact=True).click()
    expect(page.get_by_label("Find a product or SKU", exact=True)).to_have_value("Archived cocoa")
    expect(page.get_by_role("button", name="✓ Archived", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="View product: Archived cocoa", exact=True)).to_be_visible()

    page.evaluate("window.__workspaceTest.flush()")
    page.reload()
    expect(page.get_by_label("Find a product or SKU", exact=True)).to_have_value("Archived cocoa")
    expect(page.get_by_role("button", name="✓ Archived", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="View product: Archived cocoa", exact=True)).to_be_visible()


def test_screen_scroll_position_survives_background_after_content_reload(page, native_inventory):
    url, _ = native_inventory
    page.set_viewport_size({'width': 390, 'height': 500})
    page.goto(url)
    page.add_style_tag(content='html,body{height:100%;margin:0}#root{height:100vh;display:flex}')
    page.get_by_role('button', name='Open company catalog', exact=True).click()
    page.get_by_role('button', name='Add product', exact=True).click()
    scroll = page.get_by_test_id('workspace-scroll')
    scroll.evaluate('(element) => { element.scrollTop = 300; element.dispatchEvent(new Event("scroll")); }')
    page.wait_for_function('JSON.parse(localStorage.getItem("test.workspace") || "{}")?.entries && Object.entries(JSON.parse(localStorage.getItem("test.workspace")).entries).some(([key, entry]) => key.startsWith("scroll:Add a company product.") && entry.value >= 290)')
    resume_workspace(page)
    expect(page.get_by_label('Product name', exact=True)).to_be_attached()
    page.wait_for_function('document.querySelector("[data-testid=workspace-scroll]")?.scrollTop >= 290')
