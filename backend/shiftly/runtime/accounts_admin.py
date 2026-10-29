"""Explicit operator tools for initial mapping and verified account recovery.

This command never loads .env and never derives ownership from shared managers,
store names or email. Mapping defaults to validation/dry-run. A reset token is
printed only after explicit --apply and --reveal-token acknowledgement.
"""

import argparse
import json
from pathlib import Path

import psycopg

from backend.shiftly.identity.service import IdentityError


def _positive_id(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise IdentityError('invalid', f'{label} must be a positive integer.')
    return value


def bootstrap_mapping(connect, manifest, *, apply=False):
    """Validate every explicit identity first; apply the whole mapping atomically."""
    if not isinstance(manifest,dict) or set(manifest)-{'reason','businesses','stores'}:
        raise IdentityError('invalid','Mapping must contain only reason, businesses and stores.')
    reason=manifest.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500:
        raise IdentityError('invalid','A nonempty audit reason of at most 500 characters is required.')
    business_specs,store_specs=manifest.get('businesses'),manifest.get('stores')
    if not isinstance(business_specs,list) or not business_specs or not isinstance(store_specs,list) or not store_specs:
        raise IdentityError('invalid','Explicit nonempty businesses and stores lists are required.')
    businesses={}
    for item in business_specs:
        if not isinstance(item,dict) or set(item)!={'id','name','owner_user_ids'}:
            raise IdentityError('invalid','Each business requires exactly id, name and owner_user_ids.')
        business_id=_positive_id(item['id'],'Business ID')
        if business_id in businesses:
            raise IdentityError('invalid','Business IDs must be unique in the mapping.')
        name=item['name']
        owners=item['owner_user_ids']
        if not isinstance(name,str) or not name.strip() or len(name)>120 or not isinstance(owners,list) or not owners:
            raise IdentityError('invalid','Each business needs a name and explicit verified owner account IDs.')
        owners=[_positive_id(value,'Owner account ID') for value in owners]
        if len(owners)!=len(set(owners)):
            raise IdentityError('invalid','Owner account IDs cannot be repeated.')
        businesses[business_id]={'name':name.strip(),'owners':owners}
    stores={}
    for item in store_specs:
        if not isinstance(item,dict) or set(item)!={'store_id','business_id','accounts_enabled'}:
            raise IdentityError('invalid','Each store requires exactly store_id, business_id and accounts_enabled.')
        store_id=_positive_id(item['store_id'],'Store ID')
        business_id=_positive_id(item['business_id'],'Business ID')
        if store_id in stores or business_id not in businesses or not isinstance(item['accounts_enabled'],bool):
            raise IdentityError('invalid','Store IDs must be unique, mapped to listed businesses, with explicit accounts_enabled.')
        stores[store_id]=(business_id,item['accounts_enabled'])
    with connect() as connection:
        from backend.shiftly.identity.accounts_core import AccountCore
        service=AccountCore(connect)
        service._lock(connection)
        for business_id,spec in businesses.items():
            old=connection.execute('SELECT name,active FROM businesses WHERE id=%s',(business_id,)).fetchone()
            if old and old!=(spec['name'],True):
                raise IdentityError('conflict','Existing business identity does not match the explicit mapping.')
            current_owners={r[0] for r in connection.execute(
                "SELECT user_id FROM business_memberships WHERE business_id=%s AND role='owner' AND state='active'",(business_id,),
            ).fetchall()}
            if current_owners and current_owners!=set(spec['owners']):
                raise IdentityError('conflict','Existing ownership must be changed through the owner workflow.')
            for user_id in spec['owners']:
                if not connection.execute("SELECT 1 FROM account_users u LEFT JOIN manager_users m ON m.id=u.legacy_manager_id WHERE u.id=%s AND u.state='active' AND (u.legacy_manager_id IS NULL OR m.active)",(user_id,)).fetchone():
                    raise IdentityError('invalid','Every explicit owner must be an existing active verified account.')
        for store_id,(business_id,enabled) in stores.items():
            row=connection.execute('SELECT business_id,active,accounts_enabled FROM stores WHERE id=%s FOR UPDATE',(store_id,)).fetchone()
            if not row or not row[1] or row[0] not in {None,business_id}:
                raise IdentityError('conflict','Every store must exist, be active and be unassigned or already mapped to this business.')
            if row[2] and not enabled:
                raise IdentityError('conflict','Bootstrap cannot disable an already enabled account boundary.')
        result={'mode':'applied' if apply else 'dry-run','businessCount':len(businesses),'storeCount':len(stores),
                'ownerUserIds':sorted({user for spec in businesses.values() for user in spec['owners']}),
                'accountsEnabledStoreIds':sorted(store_id for store_id,(_,enabled) in stores.items() if enabled)}
        if not apply:
            connection.rollback()
            return result
        for business_id,spec in businesses.items():
            connection.execute('INSERT INTO businesses(id,name) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING',(business_id,spec['name']))
            for user_id in spec['owners']:
                connection.execute(
                    """INSERT INTO business_memberships(user_id,business_id,role,state,capabilities)
                       VALUES(%s,%s,'owner','active','{}') ON CONFLICT(user_id,business_id)
                       DO UPDATE SET role='owner',state='active',capabilities='{}'""",(user_id,business_id),
                )
                service._audit(connection,None,'bootstrap.owner_mapped',subject_user_id=user_id,business_id=business_id,
                               reason=reason.strip(),details={'authority':'controlled_operator'})
        for store_id,(business_id,enabled) in stores.items():
            connection.execute('UPDATE stores SET business_id=%s,accounts_enabled=%s WHERE id=%s',(business_id,enabled,store_id))
            connection.execute('UPDATE account_store_memberships SET business_id=%s WHERE store_id=%s',(business_id,store_id))
            connection.execute('UPDATE account_invitations SET business_id=%s WHERE store_id=%s',(business_id,store_id))
            service._audit(connection,None,'bootstrap.store_mapped',store_id=store_id,business_id=business_id,
                           reason=reason.strip(),details={'accountsEnabled':enabled,'authority':'controlled_operator'})
        # Explicit external IDs must not leave future generated IDs behind them.
        connection.execute("SELECT setval(pg_get_serial_sequence('businesses','id'), GREATEST((SELECT COALESCE(MAX(id),1) FROM businesses),(SELECT last_value FROM businesses_id_seq),1), TRUE)")
        connection.commit()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Controlled account mapping and recovery; no .env is loaded.')
    sub=parser.add_subparsers(dest='operation',required=True)
    mapping=sub.add_parser('bootstrap',help='Validate an explicit JSON mapping; default is dry-run.')
    mapping.add_argument('--manifest',required=True,type=Path)
    mapping.add_argument('--apply',action='store_true')
    recovery=sub.add_parser('recovery',help='Issue a single-use reset after independent operator identity verification.')
    recovery.add_argument('--user-id',required=True,type=int)
    recovery.add_argument('--reason',required=True)
    recovery.add_argument('--apply',action='store_true')
    recovery.add_argument('--reveal-token',action='store_true',help='Intentionally print the one-time secret for supervised delivery.')
    args=parser.parse_args(argv)
    from config import load_settings
    from .database import connect_dedicated
    from .settings import validate_runtime_settings
    from .migrate import require_schema
    try:
        settings=load_settings(load_env=False)
        validate_runtime_settings(settings)
        connect=lambda:connect_dedicated(settings)
        require_schema(connect)
        if args.operation=='bootstrap':
            result=bootstrap_mapping(connect,json.loads(args.manifest.read_text(encoding='utf-8')),apply=args.apply)
        elif not args.apply:
            _positive_id(args.user_id,'User ID')
            if not args.reason.strip():
                raise IdentityError('invalid','An audit reason is required.')
            with connect() as connection:
                if not connection.execute("SELECT 1 FROM account_users u LEFT JOIN manager_users m ON m.id=u.legacy_manager_id WHERE u.id=%s AND u.state='active' AND (u.legacy_manager_id IS NULL OR m.active)",(args.user_id,)).fetchone():
                    raise IdentityError('not_found','Active account not found.')
            result={'mode':'dry-run','userId':args.user_id,'action':'operator_password_recovery'}
        else:
            if not args.reveal_token:
                raise IdentityError('invalid','Applying recovery requires --reveal-token for intentional supervised secret delivery.')
            from backend.shiftly.identity.accounts import AccountsService
            result=AccountsService(connect).issue_password_reset(user_id=args.user_id,reason=args.reason)
        print(json.dumps(result,sort_keys=True))
    except (OSError,ValueError,RuntimeError,IdentityError,psycopg.Error):
        # Never emit database details, connection credentials or supplied secret data.
        raise SystemExit('Account administration failed. Check the explicit mapping, authority, configuration and database readiness.') from None


if __name__=='__main__':
    main()
