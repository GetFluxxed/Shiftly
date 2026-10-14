"""Shelf stock is storewide; count progress measures completed unique products."""
from uuid import uuid4

import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService
from tests.inventory_services.test_counts import fields, setup_stock, start, post
from tests.inventory_services.test_production import recipe, submission


def test_progress_requires_all_locations_and_shelves_show_posted_store_total(inventory):
    i = inventory
    product, shelves = setup_stock(i, shelves=2)
    count = start(i)
    assert (count['countedProducts'], count['totalProducts'], count['totalLines']) == (0, 1, 2)
    for shelf in shelves:
        assert i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items'][0]['storeQuantity'] is None
    lines = i.counts.lines(i.tokens['owner'], count['id'])['items']
    first = i.counts.save(i.tokens['owner'], count['id'], lines[0]['id'], fields(i, version=1, entry={'mode':'total','amount':'3','unit':'kg'}))
    assert first['count']['countedLines'] == 1 and first['count']['countedProducts'] == 0
    second = i.counts.save(i.tokens['owner'], count['id'], lines[1]['id'], fields(i, version=1, entry={'mode':'total','amount':'0','unit':'kg'}))
    assert second['count']['countedProducts'] == 1
    assert i.service.shelf(i.tokens['owner'], shelves[0]['id'])['products']['items'][0]['storeQuantity'] is None
    post(i, second['count'])
    for shelf in shelves:
        assert i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items'][0]['storeQuantity'] == '3'
    # Production changes the store balance; a shelf must not show its old location observation.
    service = ProductionService(i.connect, i.accounts)
    made = recipe(i, service, product, amount='0.5')
    service.confirm(i.tokens['owner'], submission(i, made))
    assert i.service.shelf(i.tokens['owner'], shelves[1]['id'])['products']['items'][0]['storeQuantity'] == '1.99'


def test_shelf_unknown_zero_and_other_store_stock_are_distinct(inventory):
    i = inventory
    product, shelves = setup_stock(i)
    count = start(i)
    line = i.counts.lines(i.tokens['owner'], count['id'])['items'][0]
    saved = i.counts.save(i.tokens['owner'], count['id'], line['id'], fields(i, version=1, entry={'mode':'total','amount':'0','unit':'kg'}))
    post(i, saved['count'])
    assert i.service.shelf(i.tokens['crew'], shelves[0]['id'])['products']['items'][0]['storeQuantity'] == '0'
    body = {'requestId':str(uuid4()), 'expectedStoreId':i.stores[1], 'name':'Other store shelf'}
    other = i.service.create_shelf(i.second, body)
    i.service.place(i.second, other['id'], product['id'], {**body,'requestId':str(uuid4()),'version':other['version'],'active':True})
    assert i.service.shelf(i.second, other['id'])['products']['items'][0]['storeQuantity'] is None
    with pytest.raises(IdentityError):
        i.service.shelf(i.tokens['manager'], other['id'])
    with pytest.raises(IdentityError):
        i.service.shelf(i.tokens['foreign'], shelves[0]['id'])
