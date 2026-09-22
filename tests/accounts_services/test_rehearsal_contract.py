"""Additive schema must never dilute historical-data recovery assertions."""
import copy
import json

import pytest

from scripts import rehearse_release


def snapshot():
    return {'rows': {'reports': [(json.dumps({'id': 'r', 'notes': 'Keep original'}),)],
                     'schema_migrations': [('001',)]},
            'sequences': {'existing_id_seq': (4, True)},
            'foreign_keys': [('original_fk', 'FOREIGN KEY (store_id) REFERENCES stores(id)')]}


def test_upgrade_allows_additions_but_preserves_every_old_value(monkeypatch):
    before = snapshot()
    after = copy.deepcopy(before)
    after['rows']['reports'] = [(json.dumps({'id': 'r', 'notes': 'Keep original', 'actor_user_id': None}),)]
    after['rows']['account_users'] = [(json.dumps({'id': 1}),)]
    after['sequences']['account_users_id_seq'] = (1, True)
    after['foreign_keys'].append(('new_fk', 'FOREIGN KEY (actor_user_id) REFERENCES account_users(id)'))
    monkeypatch.setattr(rehearse_release, 'snapshot', lambda _: after)
    rehearse_release.verify_upgrade(before, 'synthetic')


@pytest.mark.parametrize('defect', ['changed_value', 'removed_field', 'deleted_row', 'added_row', 'removed_table',
                                    'changed_sequence', 'removed_sequence', 'changed_fk'])
def test_upgrade_still_rejects_historical_data_or_constraint_loss(monkeypatch, defect):
    before = snapshot()
    after = copy.deepcopy(before)
    if defect == 'changed_value':
        after['rows']['reports'] = [(json.dumps({'id': 'r', 'notes': 'Changed'}),)]
    elif defect == 'removed_field':
        after['rows']['reports'] = [(json.dumps({'id': 'r'}),)]
    elif defect == 'deleted_row':
        after['rows']['reports'] = []
    elif defect == 'added_row':
        after['rows']['reports'] *= 2
    elif defect == 'removed_table':
        del after['rows']['reports']
    elif defect == 'changed_sequence':
        after['sequences']['existing_id_seq'] = (1, True)
    elif defect == 'removed_sequence':
        after['sequences'].clear()
    else:
        after['foreign_keys'] = [('original_fk', 'FOREIGN KEY (other_id) REFERENCES stores(id)')]
    monkeypatch.setattr(rehearse_release, 'snapshot', lambda _: after)
    with pytest.raises(RuntimeError):
        rehearse_release.verify_upgrade(before, 'synthetic')
