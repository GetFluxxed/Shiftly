"""Native form choices derived from shared policy; mutations still recheck authority."""
from .accounts_policy import ALL_CAPABILITIES, capabilities_for
from .contracts import IdentityError


class AccountAdministration:
    def report_managers(self, token):
        """The report directory uses individual identities and current store policy."""
        with self.connect() as connection:
            actor = self.require(token, 'reports.view', connection=connection)
            rows = connection.execute(
                """SELECT DISTINCT u.id,
                          (SELECT MAX(created_at) FROM account_sessions a WHERE a.user_id=u.id AND a.store_id=%s)
                   FROM account_users u
                   LEFT JOIN account_store_memberships m ON m.user_id=u.id AND m.store_id=%s AND m.state='active'
                   LEFT JOIN business_memberships b ON b.user_id=u.id AND b.business_id=%s AND b.state='active'
                   WHERE u.state='active' AND (m.role IN ('manager','admin') OR b.role='owner') ORDER BY u.id""",
                (actor.store_id, actor.store_id, actor.business_id),
            ).fetchall()
            result = []
            for user_id, last_sign_in in rows:
                try:
                    person = self._actor_for_user(connection, user_id, actor.store_id)
                except IdentityError:
                    continue
                if 'reports.view' in person.capabilities:
                    result.append({'name': person.display_name, 'lastSignIn': last_sign_in.isoformat() if last_sign_in else None})
            return result

    def management(self, token):
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token)
            roster = self._roster(connection, actor)
            roles = []
            for role in ('crew', 'manager', 'admin'):
                try:
                    self._check_store_grant(actor, role, ())
                except IdentityError:
                    continue
                included = capabilities_for(role)
                optional = []
                for capability in sorted(ALL_CAPABILITIES - included):
                    try:
                        self._check_store_grant(actor, role, [capability])
                        optional.append(capability)
                    except IdentityError:
                        pass
                roles.append({'role': role, 'included': sorted(included), 'optional': optional})
            for member in roster['members']:
                editable = actor.role in {'owner', 'admin'} and member['userId'] != actor.user_id
                if actor.role != 'owner':
                    editable = editable and member['businessState'] != 'active'
                    try:
                        self._check_store_grant(actor, member['role'], member['capabilities'])
                    except IdentityError:
                        editable = False
                multiple_scopes = connection.execute(
                    'SELECT 1 FROM account_store_memberships WHERE user_id=%s AND store_id<>%s',
                    (member['userId'], actor.store_id),
                ).fetchone()
                member['canEdit'] = editable
                member['canReissue'] = bool(editable and member['accountState'] == 'pending'
                    and member['membershipState'] == 'active' and member['role'] == 'crew' and not member['capabilities']
                    and not multiple_scopes)
            directory = []
            owner = actor.role == 'owner' and actor.business_id is not None
            if owner:
                rows = connection.execute(
                    """SELECT u.id,u.username,u.display_name,u.state,b.role,b.state,
                              COALESCE(b.capabilities,ARRAY[]::TEXT[]),
                              (u.legacy_manager_id IS NULL OR legacy.active)
                       FROM account_users u
                       LEFT JOIN business_memberships b ON b.user_id=u.id AND b.business_id=%s
                       LEFT JOIN manager_users legacy ON legacy.id=u.legacy_manager_id
                       WHERE b.user_id IS NOT NULL OR EXISTS (
                           SELECT 1 FROM account_store_memberships m JOIN stores s ON s.id=m.store_id
                           WHERE m.user_id=u.id AND s.business_id=%s)
                       ORDER BY u.username_key,u.id""", (actor.business_id, actor.business_id),
                ).fetchall()
                for row in rows:
                    member = dict(zip(('userId', 'username', 'displayName', 'accountState',
                                       'businessRole', 'businessState', 'businessCapabilities', 'legacyActive'), row))
                    other = member['userId'] != actor.user_id
                    member['canDelegate'] = bool(other and member['accountState'] == 'active' and member['legacyActive'])
                    member['canRevokeBusiness'] = bool(other and member['businessState'] == 'active')
                    member['canTransfer'] = member['canDelegate']
                    member['canSuspend'] = False
                    if other and member['accountState'] != 'pending':
                        try:
                            self._global_authority(connection, actor, member['userId'])
                            if member['accountState'] != 'suspended':
                                for (business_id,) in connection.execute(
                                    "SELECT business_id FROM business_memberships WHERE user_id=%s AND role='owner' AND state='active'",
                                    (member['userId'],),
                                ).fetchall():
                                    self._owner_survives(connection, business_id, member['userId'])
                            member['canSuspend'] = True
                        except IdentityError:
                            pass
                    if member['businessRole'] == 'owner' and member['businessState'] == 'active':
                        try:
                            self._owner_survives(connection, actor.business_id, member['userId'])
                        except IdentityError:
                            member['canRevokeBusiness'] = False
                    del member['legacyActive']
                    directory.append(member)
            shared = False  # Shared credentials are never accepted by release request authentication.
            return {**roster, 'roles': roles, 'directory': directory, 'isOwner': owner,
                    'businessCapabilities': sorted(ALL_CAPABILITIES) if owner else [],
                    'sharedCrewEnabled': shared if owner else None}
