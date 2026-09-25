"""Behavioral account lifecycle tests against isolated PostgreSQL schemas."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import psycopg
import pytest

from backend.shiftly.identity.accounts_core import AccountCore
from backend.shiftly.identity.accounts_lifecycle import AccountLifecycle
from backend.shiftly.identity.accounts_policy import ALL_CAPABILITIES, CREW_CAPABILITIES
from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from backend.shiftly.identity.service import IdentityError
from backend.shiftly.runtime.accounts_admin import bootstrap_mapping
from backend.shiftly.runtime.migrate import migrate


class Service(AccountLifecycle, AccountCore):
    pass


@pytest.fixture
def life(empty_database):
    connect=lambda:psycopg.connect(empty_database)
    migrate(connect)
    service=Service(connect)
    def user(name,*,legacy=False):
        salt='test-salt'
        digest=password_hash('original-password',salt)
        with connect() as connection:
            legacy_id=None
            if legacy:
                legacy_id=connection.execute(
                    'INSERT INTO manager_users(username,password_salt,password_hash) VALUES(%s,%s,%s) RETURNING id',
                    (name,salt,digest),
                ).fetchone()[0]
            return connection.execute(
                'INSERT INTO account_users(username,display_name,password_salt,password_hash,legacy_manager_id) VALUES(%s,%s,%s,%s,%s) RETURNING id',
                (name,name,salt,digest,legacy_id),
            ).fetchone()[0]
    def membership(uid,sid,role,grants=()):
        with connect() as connection:
            business_id=connection.execute('SELECT business_id FROM stores WHERE id=%s',(sid,)).fetchone()[0]
            connection.execute(
                'INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s,%s)',
                (uid,sid,business_id,role,list(grants)),
            )
    def token(uid,sid):
        with connect() as connection:
            return service._issue_session(connection,uid,sid).token
    with connect() as connection:
        biz=connection.execute("INSERT INTO businesses(name) VALUES('First Business') RETURNING id").fetchone()[0]
        otherbiz=connection.execute("INSERT INTO businesses(name) VALUES('Other Business') RETURNING id").fetchone()[0]
        stores=[]
        for index,business in enumerate([biz,biz,otherbiz,None],1):
            stores.append(connection.execute(
                'INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES(%s,%s,%s,%s) RETURNING id',
                (f'Store {index}',hash_store_code(f'store{index}'),business,business is not None),
            ).fetchone()[0])
    owner=user('Owner One')
    manager=user('Manager One',legacy=True)
    crew=user('Crew One')
    with connect() as connection:
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner')",(owner,biz))
    membership(manager,stores[0],'manager',['memberships.manage'])
    membership(crew,stores[0],'crew')
    with connect() as connection:
        legacy_id=connection.execute('SELECT legacy_manager_id FROM account_users WHERE id=%s',(manager,)).fetchone()[0]
        connection.execute('INSERT INTO store_memberships(manager_user_id,store_id) VALUES(%s,%s)',(legacy_id,stores[0]))
    return SimpleNamespace(connect=connect,service=service,user=user,membership=membership,token=token,biz=biz,
                           otherbiz=otherbiz,stores=stores,owner=owner,manager=manager,crew=crew,
                           owner_token=token(owner,stores[0]),manager_token=token(manager,stores[0]))


def denied(code,call):
    with pytest.raises(IdentityError) as caught:
        call()
    assert caught.value.code==code


def test_invitation_activation_token_hash_and_single_use(life):
    result=life.service.invite(life.manager_token,username='New Crew')
    assert result['token'] not in repr(result)
    with life.connect() as connection:
        row=connection.execute('SELECT token_hash FROM account_invitations WHERE user_id=%s',(result['userId'],)).fetchone()
        assert row==(hash_token(result['token']),)
    session=life.service.activate_invitation(result['token'],'new-password',client_key='activation')
    actor=life.service.resolve_actor(session.token)
    assert actor.user_id==result['userId'] and actor.role=='crew'
    assert 'counts.approve' not in actor.capabilities
    assert session.token not in repr(session)
    denied('invalid',lambda:life.service.activate_invitation(result['token'],'other-password',client_key='activation'))
    denied('conflict',lambda:life.service.invite(life.owner_token,username='  new CREW '))


def test_invitation_expiry_reissue_and_pending_only(life):
    invitation=life.service.invite(life.owner_token,username='Pending Crew')
    with life.connect() as connection:
        connection.execute('UPDATE account_invitations SET expires_at=NOW()-INTERVAL \'1 minute\' WHERE user_id=%s',(invitation['userId'],))
    denied('invalid',lambda:life.service.activate_invitation(invitation['token'],'new-password',client_key='expiry'))
    replacement=life.service.reissue_invitation(life.manager_token,user_id=invitation['userId'])
    denied('invalid',lambda:life.service.activate_invitation(invitation['token'],'new-password',client_key='expiry'))
    life.service.activate_invitation(replacement['token'],'new-password',client_key='expiry')
    denied('conflict',lambda:life.service.reissue_invitation(life.manager_token,user_id=invitation['userId']))


def test_invitation_activation_race_has_one_winner(life):
    invitation=life.service.invite(life.owner_token,username='Racing Crew')
    def activate(index):
        try:
            return life.service.activate_invitation(invitation['token'],'new-password',client_key=f'parallel-{index}').role
        except IdentityError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(activate,range(2)))==['account','invalid']


def test_revoking_inviter_authority_blocks_pending_activation(life):
    invitation=life.service.invite(life.manager_token,username='Withdrawn Crew')
    life.service.set_membership(life.owner_token,user_id=life.manager,role='manager',active=False)
    denied('forbidden',lambda:life.service.activate_invitation(invitation['token'],'new-password',client_key='withdrawn'))


def test_manager_allowed_crew_grants_cannot_promote_or_modify_manager(life):
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.crew,role='crew',capabilities=['counts.submit','inventory.view']))
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.crew,role='crew',capabilities=['counts.approve']))
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.crew,role='manager'))
    other=life.user('Second Manager')
    life.membership(other,life.stores[0],'manager')
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=other,role='crew'))
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.manager,role='crew'))


def test_admin_delegation_is_store_scoped_and_cannot_overgrant(life):
    admin=life.user('Delegated Admin')
    grants=CREW_CAPABILITIES|{'memberships.manage'}
    life.service.set_business_membership(life.owner_token,user_id=admin,role='admin',capabilities=grants)
    life.service.set_membership(life.owner_token,user_id=admin,role='admin',capabilities=grants)
    token=life.token(admin,life.stores[0])
    life.service.invite(token,username='Admin Created Crew')
    denied('forbidden',lambda:life.service.invite(token,username='Forbidden Manager',role='manager'))
    denied('forbidden',lambda:life.service.set_membership(token,user_id=life.crew,role='crew',store_id=life.stores[1]))
    denied('forbidden',lambda:life.service.set_business_membership(token,user_id=life.crew,role='owner'))


def test_staff_transfer_requires_removal_then_preserves_individual_credentials(life):
    local_token=life.token(life.crew,life.stores[0])
    denied('conflict',lambda:life.service.set_membership(life.owner_token,user_id=life.crew,role='manager',store_id=life.stores[1]))
    life.service.set_membership(life.owner_token,user_id=life.crew,role='crew',active=False)
    denied('unauthenticated',lambda:life.service.resolve_actor(local_token))
    life.service.set_membership(life.owner_token,user_id=life.crew,role='manager',store_id=life.stores[1])
    session=life.service.login(None,'Crew One','original-password',client_key='transferred')
    assert life.service.resolve_actor(session.token).store_id==life.stores[1]
    denied('forbidden',lambda:life.service.switch_store(session.token,life.stores[0]))


def test_owner_global_suspension_requires_all_scopes_and_revokes_sessions(life):
    crew_token=life.token(life.crew,life.stores[0])
    result=life.service.suspend_user(life.owner_token,user_id=life.crew,reason='Account access ended')
    assert result['state']=='suspended'
    denied('unauthenticated',lambda:life.service.resolve_actor(crew_token))
    life.service.suspend_user(life.owner_token,user_id=life.crew,suspended=False)
    assert life.service.login('store1','Crew One','original-password',client_key='reactivated').response['authenticated']
    life.membership(life.crew,life.stores[3],'crew')
    denied('forbidden',lambda:life.service.suspend_user(life.owner_token,user_id=life.crew))


def test_last_owner_guard_and_concurrent_removal(life):
    denied('conflict',lambda:life.service.set_business_membership(life.owner_token,user_id=life.owner,role='owner',active=False))
    denied('conflict',lambda:life.service.suspend_user(life.owner_token,user_id=life.owner))
    second=life.user('Owner Two')
    life.service.set_business_membership(life.owner_token,user_id=second,role='owner')
    second_token=life.token(second,life.stores[0])
    def remove(pair):
        actor,target=pair
        try:
            life.service.set_business_membership(actor,user_id=target,role='owner',active=False)
            return 'removed'
        except IdentityError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(remove,[(life.owner_token,second),(second_token,life.owner)]))
    assert results.count('removed')==1
    with life.connect() as connection:
        assert connection.execute("SELECT count(*) FROM business_memberships WHERE business_id=%s AND role='owner' AND state='active'",(life.biz,)).fetchone()[0]==1


def test_ownership_transfer_revokes_old_owner_tokens(life):
    result=life.service.transfer_ownership(life.owner_token,user_id=life.crew,reason='Approved owner succession')
    assert result['ownerUserId']==life.crew
    denied('unauthenticated',lambda:life.service.resolve_actor(life.owner_token))
    assert life.service.resolve_actor(life.token(life.crew,life.stores[1])).role=='owner'


def test_operator_reset_replay_race_and_legacy_credentials(life):
    with life.connect() as connection:
        legacy_id=connection.execute('SELECT legacy_manager_id FROM account_users WHERE id=%s',(life.manager,)).fetchone()[0]
        connection.execute("INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at) VALUES(%s,%s,%s,NOW()+INTERVAL '1 hour')",(hash_token('legacy-token'),legacy_id,life.stores[0]))
    reset=life.service.issue_password_reset(user_id=life.manager,reason='Independent operator identity verification')
    assert reset['token'] not in repr(reset)
    def apply(index):
        try:
            life.service.reset_password(reset['token'],'replacement-password',client_key=f'reset-{index}')
            return 'reset'
        except IdentityError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(apply,range(2)))==['invalid','reset']
    denied('unauthenticated',lambda:life.service.resolve_actor(life.manager_token))
    denied('unauthenticated',lambda:life.service.login('store1','Manager One','original-password',client_key='old-password'))
    assert life.service.login('store1','Manager One','replacement-password',client_key='new-password').response['authenticated']
    with life.connect() as connection:
        row=connection.execute('SELECT u.password_salt,u.password_hash,m.password_salt,m.password_hash FROM account_users u JOIN manager_users m ON m.id=u.legacy_manager_id WHERE u.id=%s',(life.manager,)).fetchone()
        assert row[:2]==row[2:]
        assert connection.execute('SELECT count(*) FROM manager_sessions WHERE manager_user_id=%s',(legacy_id,)).fetchone()==(0,)
        assert 'replacement-password' not in str(connection.execute('SELECT details FROM account_audit').fetchall())


def test_password_change_revokes_all_tokens_and_prior_recovery(life):
    reset=life.service.issue_password_reset(user_id=life.manager,reason='Operator verified')
    denied('unauthenticated',lambda:life.service.change_password(life.manager_token,current_password='wrong',new_password='new-password'))
    life.service.change_password(life.manager_token,current_password='original-password',new_password='new-password')
    denied('unauthenticated',lambda:life.service.resolve_actor(life.manager_token))
    denied('invalid',lambda:life.service.reset_password(reset['token'],'replacement-password',client_key='old-reset'))


def test_recovery_expiry_and_attempt_budget(life):
    reset=life.service.issue_password_reset(user_id=life.crew,reason='Operator verified')
    with life.connect() as connection:
        connection.execute('UPDATE account_password_resets SET expires_at=NOW()-INTERVAL \'1 second\'')
    denied('invalid',lambda:life.service.reset_password(reset['token'],'new-password',client_key='brute-force'))
    for index in range(9):
        denied('invalid',lambda:life.service.reset_password(f'unknown-{index}','new-password',client_key='brute-force'))
    denied('limited',lambda:life.service.reset_password('unknown-last','new-password',client_key='brute-force'))


def test_audit_failure_rolls_back_membership_and_session_revocation(life,monkeypatch):
    crew_token=life.token(life.crew,life.stores[0])
    def fail(*args,**kwargs):
        raise RuntimeError('injected audit failure')
    monkeypatch.setattr(life.service,'_audit',fail)
    with pytest.raises(RuntimeError):
        life.service.set_membership(life.owner_token,user_id=life.crew,role='crew',active=False)
    assert life.service.resolve_actor(crew_token).user_id==life.crew


def test_cutover_revokes_shared_crew_sessions(life):
    with life.connect() as connection:
        connection.execute("INSERT INTO crew_sessions(token_hash,store_id,expires_at) VALUES(%s,%s,NOW()+INTERVAL '1 hour')",(hash_token('shared'),life.stores[0]))
    denied('forbidden',lambda:life.service.cutover_store(life.manager_token))
    assert not life.service.cutover_store(life.owner_token)['sharedCrewEnabled']
    with life.connect() as connection:
        assert connection.execute('SELECT shared_crew_enabled FROM stores WHERE id=%s',(life.stores[0],)).fetchone()==(False,)
        assert connection.execute('SELECT count(*) FROM crew_sessions WHERE store_id=%s',(life.stores[0],)).fetchone()==(0,)


def test_bootstrap_requires_explicit_ids_dry_run_then_atomic_apply(life):
    manifest={'reason':'Verified synthetic owner mapping','businesses':[{'id':700,'name':'Mapped Business','owner_user_ids':[life.crew]}],
              'stores':[{'store_id':life.stores[3],'business_id':700,'accounts_enabled':True}]}
    preview=bootstrap_mapping(life.connect,manifest)
    assert preview['mode']=='dry-run'
    with life.connect() as connection:
        assert not connection.execute('SELECT 1 FROM businesses WHERE id=700').fetchone()
        assert connection.execute('SELECT business_id FROM stores WHERE id=%s',(life.stores[3],)).fetchone()==(None,)
    bootstrap_mapping(life.connect,manifest,apply=True)
    assert life.service.resolve_actor(life.token(life.crew,life.stores[3])).role=='owner'
    bootstrap_mapping(life.connect,manifest,apply=True)
    manifest['businesses'][0]['owner_user_ids']=[life.owner]
    denied('conflict',lambda:bootstrap_mapping(life.connect,manifest,apply=True))


def test_bootstrap_validation_failure_does_not_apply_partial_mapping(life):
    manifest={'reason':'Synthetic invalid mapping','businesses':[{'id':701,'name':'Invalid Business','owner_user_ids':[999999]}],
              'stores':[{'store_id':life.stores[3],'business_id':701,'accounts_enabled':True}]}
    denied('invalid',lambda:bootstrap_mapping(life.connect,manifest,apply=True))
    with life.connect() as connection:
        assert not connection.execute('SELECT 1 FROM businesses WHERE id=701').fetchone()


def test_pending_invitation_cannot_be_claimed_through_another_store(life):
    invitation=life.service.invite(life.owner_token,username='Protected Pending')
    denied('forbidden',lambda:life.service.set_membership(life.owner_token,user_id=invitation['userId'],role='crew',store_id=life.stores[1]))
    # Even anomalous/operator-created multiple scopes fail closed on activation.
    life.membership(invitation['userId'],life.stores[2],'crew')
    denied('forbidden',lambda:life.service.reissue_invitation(life.manager_token,user_id=invitation['userId']))
    denied('forbidden',lambda:life.service.activate_invitation(invitation['token'],'new-password',client_key='cross-pending'))


def test_local_manager_cannot_revoke_business_owner_or_admin_sessions(life):
    life.membership(life.owner,life.stores[0],'crew')
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.owner,role='crew',active=False))
    assert life.service.resolve_actor(life.owner_token).role=='owner'
    life.service.set_business_membership(life.owner_token,user_id=life.crew,role='admin',capabilities=['catalog.manage'])
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=life.crew,role='crew',active=False))


def test_disabled_legacy_identity_cannot_replace_last_owner(life):
    with life.connect() as connection:
        connection.execute('UPDATE manager_users SET active=FALSE WHERE id=(SELECT legacy_manager_id FROM account_users WHERE id=%s)',(life.manager,))
    denied('conflict',lambda:life.service.transfer_ownership(life.owner_token,user_id=life.manager))
    assert life.service.resolve_actor(life.owner_token).role=='owner'
    with life.connect() as connection:
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner')",(life.manager,life.biz))
    denied('conflict',lambda:life.service.set_business_membership(life.owner_token,user_id=life.owner,role='owner',active=False))


def test_operator_cli_defaults_to_dry_run_and_requires_explicit_secret_delivery(life,tmp_path,monkeypatch,capsys):
    import json
    import config
    from backend.shiftly.runtime.accounts_admin import main
    monkeypatch.setattr(config,'load_env_file',lambda *args: (_ for _ in ()).throw(AssertionError('Must not load .env')))
    manifest={'reason':'Synthetic CLI verification','businesses':[{'id':702,'name':'CLI Business','owner_user_ids':[life.crew]}],
              'stores':[{'store_id':life.stores[3],'business_id':702,'accounts_enabled':False}]}
    path=tmp_path/'mapping.json'
    path.write_text(json.dumps(manifest))
    main(['bootstrap','--manifest',str(path)])
    assert json.loads(capsys.readouterr().out)['mode']=='dry-run'
    with life.connect() as connection:
        assert not connection.execute('SELECT 1 FROM businesses WHERE id=702').fetchone()
    main(['recovery','--user-id',str(life.crew),'--reason','Verified test account'])
    assert json.loads(capsys.readouterr().out)['mode']=='dry-run'
    with pytest.raises(SystemExit):
        main(['recovery','--user-id',str(life.crew),'--reason','Verified test account','--apply'])
    with life.connect() as connection:
        assert connection.execute('SELECT count(*) FROM account_password_resets').fetchone()==(0,)
    main(['recovery','--user-id',str(life.crew),'--reason','Verified test account','--apply','--reveal-token'])
    issued=json.loads(capsys.readouterr().out)
    with life.connect() as connection:
        assert connection.execute('SELECT token_hash FROM account_password_resets WHERE user_id=%s',(life.crew,)).fetchone()==(hash_token(issued['token']),)


def test_limited_admin_cannot_demote_manager_outside_delegation(life):
    admin=life.user('Limited Admin')
    grants=CREW_CAPABILITIES|{'memberships.manage'}
    life.service.set_business_membership(life.owner_token,user_id=admin,role='admin',capabilities=grants)
    life.service.set_membership(life.owner_token,user_id=admin,role='admin',capabilities=grants)
    token=life.token(admin,life.stores[0])
    denied('forbidden',lambda:life.service.set_membership(token,user_id=life.manager,role='crew',active=False))
    assert life.service.resolve_actor(life.manager_token).role=='manager'

@pytest.mark.parametrize('role,grants', [('manager',[]),('admin',[]),('owner',[]),('crew',['inventory.view']),('crew',['memberships.manage'])])
def test_invitation_never_assigns_privileges(life,role,grants):
    denied('forbidden',lambda:life.service.invite(life.owner_token,username='Tampered',role=role,capabilities=grants))
    with life.connect() as c:
        assert not c.execute("SELECT 1 FROM account_users WHERE username='Tampered'").fetchone()


def test_preview_does_not_consume_and_promotion_requires_activation(life):
    invite=life.service.invite(life.owner_token,username='Individual Account')
    assert life.service.invitation_details(invite['token'],client_key='preview')['username']=='Individual Account'
    denied('conflict',lambda:life.service.set_membership(life.owner_token,user_id=invite['userId'],role='manager'))
    session=life.service.activate_invitation(invite['token'],'personal-password',client_key='accept')
    assert life.service.resolve_actor(session.token).role=='crew'
    denied('invalid',lambda:life.service.invitation_details(invite['token'],client_key='used'))
    denied('forbidden',lambda:life.service.set_membership(life.manager_token,user_id=invite['userId'],role='crew'))
    life.service.set_membership(life.owner_token,user_id=invite['userId'],role='manager')
    denied('unauthenticated',lambda:life.service.resolve_actor(session.token))
    promoted=life.service.login_payload({'username':'Individual Account','password':'personal-password','role':'owner','storeId':life.stores[1]},client_key='personal-login')
    actor=life.service.resolve_actor(promoted.token)
    assert actor.role=='manager' and actor.store_id==life.stores[0]
    denied('forbidden',lambda:life.service.switch_store(promoted.token,life.stores[1]))
    denied('forbidden',lambda:life.service.resolve_actor(promoted.token,store_id=life.stores[1]))


def test_ambiguous_staff_assignments_fail_closed_even_with_old_sessions(life):
    before=life.token(life.manager,life.stores[0])
    life.membership(life.manager,life.stores[1],'manager')
    denied('forbidden',lambda:life.service.resolve_actor(before))
    denied('forbidden',lambda:life.service.login(None,'Manager One','original-password',client_key='ambiguous'))
    life.service.set_membership(life.owner_token,user_id=life.manager,role='manager',active=False,store_id=life.stores[1])
    assert life.service.resolve_actor(before).store_id==life.stores[0]


def test_concurrent_second_store_assignments_cannot_give_staff_two_stores(life):
    unassigned=life.user('One Store Only')
    def assign(sid):
        try:
            life.service.set_membership(life.owner_token,user_id=unassigned,role='manager',store_id=sid)
            return 'assigned'
        except IdentityError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(assign,life.stores[:2]))==['assigned','conflict']
    with life.connect() as c:
        assert c.execute("SELECT count(*) FROM account_store_memberships WHERE user_id=%s AND state='active'",(unassigned,)).fetchone()[0]==1
