"""Named-account lifecycle. Every privileged mutation rechecks policy under one lock.

The operator-only reset/bootstrap interfaces are deliberately absent from HTTP
adapters. Local team authority never implies control over a person's password.
"""

import hmac
import uuid

import psycopg

from .accounts_policy import ALL_CAPABILITIES, assert_grant
from .primitives import hash_token
from .service import IdentityError


class SecretResult(dict):
    """JSON-compatible intentional secret delivery without incidental repr leaks."""

    def __repr__(self):
        return repr({key: '[redacted]' if key in {'token', 'invitationToken', 'resetToken'} else value
                     for key, value in self.items()})

    __str__ = __repr__


class AccountLifecycle:
    @staticmethod
    def _id(value, label='User'):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise IdentityError('invalid', f'{label} ID must be a positive integer.')
        return value

    @staticmethod
    def _reason(value):
        if not isinstance(value, str) or len(value) > 500:
            raise IdentityError('invalid', 'Reason must be text of at most 500 characters.')
        return value.strip()

    @staticmethod
    def _grants(values):
        if not isinstance(values, (list, tuple, set, frozenset)) or any(not isinstance(v, str) for v in values):
            raise IdentityError('invalid', 'Capabilities must be a list of known permission names.')
        grants = frozenset(values)
        if not grants <= ALL_CAPABILITIES:
            raise IdentityError('invalid', 'Unknown account capability.')
        return grants

    def _lifecycle_actor(self, connection, token, *, store_id=None):
        self._lock(connection)
        return self.require(token, 'memberships.manage', connection=connection, store_id=store_id)

    @staticmethod
    def _require_owner(actor):
        if actor.role != 'owner' or actor.business_id is None:
            raise IdentityError('forbidden', 'Business ownership is required.')

    def _check_store_grant(self, actor, role, capabilities):
        if not isinstance(role, str):
            raise IdentityError('invalid', 'Role must be text.')
        grants = self._grants(capabilities)
        return assert_grant(actor, role, grants, business_id=actor.business_id)

    @staticmethod
    def _assert_target(connection, user_id, *, active=False):
        row = connection.execute(
            'SELECT u.state,u.legacy_manager_id,m.active FROM account_users u LEFT JOIN manager_users m ON m.id=u.legacy_manager_id WHERE u.id=%s FOR UPDATE OF u',
            (user_id,),
        ).fetchone()
        if not row:
            raise IdentityError('not_found', 'Account not found.')
        if active and (row[0] != 'active' or (row[1] is not None and not row[2])):
            raise IdentityError('conflict', 'An active account is required.')
        return row[:2]

    @staticmethod
    def _owner_survives(connection, business_id, excluded_user_id):
        if not connection.execute(
            """SELECT 1 FROM business_memberships m JOIN account_users u ON u.id=m.user_id
               LEFT JOIN manager_users legacy ON legacy.id=u.legacy_manager_id
               WHERE m.business_id=%s AND m.role='owner' AND m.state='active'
                 AND u.state='active' AND (u.legacy_manager_id IS NULL OR legacy.active) AND m.user_id<>%s LIMIT 1""", (business_id, excluded_user_id),
        ).fetchone():
            raise IdentityError('conflict', 'The last active business owner cannot be removed or suspended.')

    def invite(self, token, *, username, display_name='', role='crew', capabilities=(), store_id=None,
               expires_in=86400, reason=''):
        username = self._validate_username(username)
        if not isinstance(display_name, str) or len(display_name) > 120:
            raise IdentityError('invalid', 'Display name must be text of at most 120 characters.')
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or not 60 <= expires_in <= 604800:
            raise IdentityError('invalid', 'Invitation lifetime must be between 60 seconds and 7 days.')
        reason = self._reason(reason)
        try:
            with self.connect() as connection:
                actor = self._lifecycle_actor(connection, token, store_id=store_id)
                if role == 'admin':
                    raise IdentityError('forbidden', 'Activate an individual account before delegating business administration.')
                grants = self._check_store_grant(actor, role, capabilities)
                if connection.execute('SELECT 1 FROM account_users WHERE username_key=account_username_key(%s)', (username,)).fetchone():
                    raise IdentityError('conflict', 'This username already exists; assign membership without changing its password.')
                salt = self.token_factory(24)
                user_id = connection.execute(
                    """INSERT INTO account_users (username,display_name,password_salt,password_hash,state)
                       VALUES (%s,%s,%s,%s,'pending') RETURNING id""",
                    (username, display_name.strip() or username, salt, self.password_hasher(self.token_factory(32), salt)),
                ).fetchone()[0]
                connection.execute(
                    """INSERT INTO account_store_memberships(user_id,store_id,business_id,role,state,capabilities)
                       VALUES (%s,%s,%s,%s,'active',%s)""",
                    (user_id, actor.store_id, actor.business_id, role, sorted(grants)),
                )
                invitation_id, raw_token = uuid.uuid4(), self.token_factory(32)
                connection.execute(
                    """INSERT INTO account_invitations(id,token_hash,user_id,store_id,business_id,role,capabilities,created_by,expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 second'))""",
                    (invitation_id, hash_token(raw_token), user_id, actor.store_id, actor.business_id, role,
                     sorted(grants), actor.user_id, expires_in),
                )
                self._audit(connection, actor, 'account.invited', subject_user_id=user_id, reason=reason,
                            details={'role': role, 'capabilities': sorted(grants)})
                connection.commit()
            return SecretResult(userId=user_id, invitationId=str(invitation_id), token=raw_token, expiresIn=expires_in)
        except psycopg.errors.UniqueViolation as error:
            raise IdentityError('conflict', 'This username already exists.') from error

    def reissue_invitation(self, token, *, user_id, expires_in=86400, store_id=None, reason=''):
        user_id, reason = self._id(user_id), self._reason(reason)
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or not 60 <= expires_in <= 604800:
            raise IdentityError('invalid', 'Invitation lifetime must be between 60 seconds and 7 days.')
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token, store_id=store_id)
            state, _ = self._assert_target(connection, user_id)
            if state != 'pending':
                raise IdentityError('conflict', 'Only pending accounts can receive a replacement activation invitation.')
            membership = connection.execute(
                "SELECT role,capabilities FROM account_store_memberships WHERE user_id=%s AND store_id=%s AND state='active'",
                (user_id, actor.store_id),
            ).fetchone()
            if not membership or membership[0] not in {'crew', 'manager'}:
                raise IdentityError('forbidden', 'An active permitted store membership is required.')
            if connection.execute('SELECT 1 FROM account_store_memberships WHERE user_id=%s AND store_id<>%s', (user_id, actor.store_id)).fetchone():
                raise IdentityError('forbidden', 'Activation of a pending account with multiple scopes requires operator reconciliation.')
            role, grants = membership
            self._check_store_grant(actor, role, grants)
            connection.execute('UPDATE account_invitations SET revoked_at=NOW() WHERE user_id=%s AND used_at IS NULL', (user_id,))
            invitation_id, raw_token = uuid.uuid4(), self.token_factory(32)
            connection.execute(
                """INSERT INTO account_invitations(id,token_hash,user_id,store_id,business_id,role,capabilities,created_by,expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 second'))""",
                (invitation_id, hash_token(raw_token), user_id, actor.store_id, actor.business_id, role,
                 sorted(grants), actor.user_id, expires_in),
            )
            self._audit(connection, actor, 'invitation.reissued', subject_user_id=user_id, reason=reason)
            connection.commit()
        return SecretResult(userId=user_id, invitationId=str(invitation_id), token=raw_token, expiresIn=expires_in)

    def _admit_secret(self, client_key, purpose):
        # One budget per client/purpose, rather than attacker-selected token values.
        if not self.admission.reserve_login(client_key, purpose):
            raise IdentityError('limited', 'Too many failed account attempts. Try again later.')

    def activate_invitation(self, invitation_token, password, *, client_key):
        self._admit_secret(client_key, 'account-activation')
        succeeded = False
        try:
            self._validate_password(password)
            if not isinstance(invitation_token, str) or not invitation_token or len(invitation_token) > 512:
                raise IdentityError('invalid', 'Invalid or expired activation token.')
            with self.connect() as connection:
                self._lock(connection)
                row = connection.execute(
                    """SELECT i.id,i.user_id,i.store_id,i.role,i.capabilities,i.created_by
                       FROM account_invitations i JOIN account_users u ON u.id=i.user_id
                       JOIN account_store_memberships m ON m.user_id=i.user_id AND m.store_id=i.store_id
                       JOIN stores s ON s.id=i.store_id
                       WHERE i.token_hash=%s AND i.expires_at>NOW() AND i.used_at IS NULL AND i.revoked_at IS NULL
                         AND u.state='pending' AND m.state='active' AND s.active AND s.accounts_enabled
                         AND m.role=i.role AND m.capabilities=i.capabilities
                       FOR UPDATE OF i,u,m""", (hash_token(invitation_token),),
                ).fetchone()
                if not row:
                    raise IdentityError('invalid', 'Invalid or expired activation token.')
                invitation_id, user_id, store_id, role, grants, inviter_id = row
                if connection.execute('SELECT 1 FROM account_store_memberships WHERE user_id=%s AND store_id<>%s', (user_id, store_id)).fetchone():
                    raise IdentityError('forbidden', 'Activation of a pending account with multiple scopes requires operator reconciliation.')
                # Withdrawal of inviter authority also withdraws unaccepted grants.
                inviter = self._actor_for_user(connection, inviter_id, store_id)
                if 'memberships.manage' not in inviter.capabilities:
                    raise IdentityError('forbidden', 'Invitation authority was withdrawn.')
                self._check_store_grant(inviter, role, grants)
                salt = self.token_factory(24)
                connection.execute(
                    """UPDATE account_users SET password_salt=%s,password_hash=%s,state='active',
                       credential_version=credential_version+1,updated_at=NOW() WHERE id=%s""",
                    (salt, self.password_hasher(password, salt), user_id),
                )
                connection.execute('UPDATE account_invitations SET used_at=NOW() WHERE id=%s', (invitation_id,))
                self._audit(connection, None, 'account.activated', subject_user_id=user_id, store_id=store_id,
                            business_id=inviter.business_id, details={'inviterUserId': inviter_id})
                result = self._issue_session(connection, user_id, store_id)
                connection.commit()
            succeeded = True
            return result
        finally:
            self.admission.finish_login(client_key, 'account-activation', failed=not succeeded)

    def roster(self, token, *, store_id=None):
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token, store_id=store_id)
            rows = connection.execute(
                """SELECT u.id,u.username,u.display_name,u.state,m.role,m.state,m.capabilities,
                          b.role,b.state,COALESCE(b.capabilities,ARRAY[]::TEXT[])
                   FROM account_store_memberships m JOIN account_users u ON u.id=m.user_id
                   LEFT JOIN business_memberships b ON b.user_id=u.id AND b.business_id=%s
                   WHERE m.store_id=%s ORDER BY u.username_key,u.id""", (actor.business_id,actor.store_id),
            ).fetchall()
            return {'storeId': actor.store_id, 'members': [dict(zip(
                ('userId','username','displayName','accountState','role','membershipState','capabilities',
                 'businessRole','businessState','businessCapabilities'), row)) for row in rows]}

    def set_membership(self, token, *, user_id, role, capabilities=(), active=True, store_id=None, reason=''):
        user_id, reason = self._id(user_id), self._reason(reason)
        if not isinstance(active, bool):
            raise IdentityError('invalid', 'Active must be a boolean.')
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token, store_id=store_id)
            target = self._assert_target(connection, user_id)
            if actor.user_id == user_id:
                raise IdentityError('forbidden', 'Self-modification of membership is not permitted.')
            grants = self._check_store_grant(actor, role, capabilities)
            old = connection.execute('SELECT role,capabilities FROM account_store_memberships WHERE user_id=%s AND store_id=%s', (user_id, actor.store_id)).fetchone()
            if actor.role != 'owner' and connection.execute(
                "SELECT 1 FROM business_memberships WHERE user_id=%s AND business_id=%s AND state='active'",
                (user_id, actor.business_id),
            ).fetchone():
                raise IdentityError('forbidden', 'Only owners can modify memberships of business owners or delegated administrators.')
            if target[0] == 'pending' and not old:
                raise IdentityError('forbidden', 'Activate the existing invitation before assigning another store membership.')
            # Do not turn an existing manager/admin into crew to bypass management limits.
            if actor.role == 'manager' and old and old[0] != 'crew':
                raise IdentityError('forbidden', 'Managers can manage crew memberships only.')
            if actor.role != 'owner' and old:
                self._check_store_grant(actor, old[0], old[1])
            if role == 'admin' and not connection.execute(
                "SELECT 1 FROM business_memberships WHERE user_id=%s AND business_id=%s AND role='admin' AND state='active'",
                (user_id, actor.business_id),
            ).fetchone():
                raise IdentityError('conflict', 'An active business administrator delegation is required first.')
            connection.execute(
                """INSERT INTO account_store_memberships(user_id,store_id,business_id,role,state,capabilities)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,store_id) DO UPDATE SET
                   business_id=EXCLUDED.business_id,role=EXCLUDED.role,state=EXCLUDED.state,capabilities=EXCLUDED.capabilities,updated_at=NOW()""",
                (user_id, actor.store_id, actor.business_id, role, 'active' if active else 'revoked', sorted(grants)),
            )
            connection.execute('UPDATE account_invitations SET revoked_at=NOW() WHERE user_id=%s AND store_id=%s AND used_at IS NULL', (user_id, actor.store_id))
            self._revoke_user_sessions(connection, user_id, store_id=actor.store_id)
            if target[1] is not None and (not active or role != 'manager'):
                connection.execute('DELETE FROM store_memberships WHERE manager_user_id=%s AND store_id=%s', (target[1], actor.store_id))
            self._audit(connection, actor, 'membership.changed', subject_user_id=user_id, reason=reason,
                        details={'role': role, 'active': active, 'capabilities': sorted(grants)})
            connection.commit()
        return {'userId': user_id, 'storeId': actor.store_id, 'role': role, 'active': active, 'capabilities': sorted(grants)}

    def set_business_membership(self, token, *, user_id, role, capabilities=(), active=True, reason=''):
        user_id, reason = self._id(user_id), self._reason(reason)
        grants = self._grants(capabilities)
        if not isinstance(role, str) or role not in {'owner', 'admin'} or not isinstance(active, bool):
            raise IdentityError('invalid', 'Business role must be owner or admin and active must be a boolean.')
        if role == 'owner' and grants:
            raise IdentityError('invalid', 'Owners have the full owner policy; explicit grants are not accepted.')
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token)
            self._require_owner(actor)
            self._assert_target(connection, user_id, active=active)
            if actor.user_id == user_id and active:
                raise IdentityError('forbidden', 'Use ownership transfer to change your own role.')
            old = connection.execute('SELECT role,state FROM business_memberships WHERE user_id=%s AND business_id=%s', (user_id, actor.business_id)).fetchone()
            if old == ('owner', 'active') and (role != 'owner' or not active):
                self._owner_survives(connection, actor.business_id, user_id)
            connection.execute(
                """INSERT INTO business_memberships(user_id,business_id,role,state,capabilities) VALUES(%s,%s,%s,%s,%s)
                   ON CONFLICT(user_id,business_id) DO UPDATE SET role=EXCLUDED.role,state=EXCLUDED.state,capabilities=EXCLUDED.capabilities,updated_at=NOW()""",
                (user_id, actor.business_id, role, 'active' if active else 'revoked', sorted(grants)),
            )
            self._revoke_business_sessions(connection, user_id, actor.business_id)
            self._audit(connection, actor, 'business_membership.changed', subject_user_id=user_id, reason=reason,
                        details={'role': role, 'active': active, 'capabilities': sorted(grants)})
            connection.commit()
        return {'userId': user_id, 'businessId': actor.business_id, 'role': role, 'active': active}

    def _revoke_business_sessions(self, connection, user_id, business_id):
        for (store_id,) in connection.execute('SELECT id FROM stores WHERE business_id=%s', (business_id,)).fetchall():
            self._revoke_user_sessions(connection, user_id, store_id=store_id)

    def transfer_ownership(self, token, *, user_id, reason=''):
        user_id, reason = self._id(user_id), self._reason(reason)
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token)
            self._require_owner(actor)
            if user_id == actor.user_id:
                raise IdentityError('invalid', 'Choose another active account for ownership transfer.')
            self._assert_target(connection, user_id, active=True)
            connection.execute(
                """INSERT INTO business_memberships(user_id,business_id,role,state,capabilities) VALUES(%s,%s,'owner','active','{}')
                   ON CONFLICT(user_id,business_id) DO UPDATE SET role='owner',state='active',capabilities='{}',updated_at=NOW()""", (user_id, actor.business_id),
            )
            connection.execute("UPDATE business_memberships SET state='revoked',updated_at=NOW() WHERE user_id=%s AND business_id=%s", (actor.user_id, actor.business_id))
            self._revoke_business_sessions(connection, actor.user_id, actor.business_id)
            self._revoke_business_sessions(connection, user_id, actor.business_id)
            self._audit(connection, actor, 'ownership.transferred', subject_user_id=user_id, reason=reason)
            connection.commit()
        return {'businessId': actor.business_id, 'ownerUserId': user_id}

    def _global_authority(self, connection, actor, user_id):
        self._require_owner(actor)
        owned = {r[0] for r in connection.execute(
            "SELECT business_id FROM business_memberships WHERE user_id=%s AND role='owner' AND state='active'", (actor.user_id,),
        ).fetchall()}
        # Include revoked membership history too: local removal cannot create global control.
        scopes = {r[0] for r in connection.execute(
            """SELECT business_id FROM business_memberships WHERE user_id=%s UNION
               SELECT s.business_id FROM account_store_memberships m JOIN stores s ON s.id=m.store_id WHERE m.user_id=%s""", (user_id,user_id),
        ).fetchall()}
        if not scopes or None in scopes or not scopes <= owned:
            raise IdentityError('forbidden', 'Global account authority is not established; use controlled operator recovery.')

    def suspend_user(self, token, *, user_id, suspended=True, reason=''):
        user_id, reason = self._id(user_id), self._reason(reason)
        if not isinstance(suspended, bool):
            raise IdentityError('invalid', 'Suspended must be a boolean.')
        with self.connect() as connection:
            actor = self._lifecycle_actor(connection, token)
            state, legacy_id = self._assert_target(connection, user_id)
            self._global_authority(connection, actor, user_id)
            if state == 'pending':
                raise IdentityError('conflict', 'Revoke pending invitations through their store membership.')
            if suspended:
                for (business_id,) in connection.execute(
                    "SELECT business_id FROM business_memberships WHERE user_id=%s AND role='owner' AND state='active'", (user_id,),
                ).fetchall():
                    self._owner_survives(connection, business_id, user_id)
            connection.execute("UPDATE account_users SET state=%s,credential_version=credential_version+1,updated_at=NOW() WHERE id=%s", ('suspended' if suspended else 'active', user_id))
            if legacy_id is not None:
                connection.execute('UPDATE manager_users SET active=%s WHERE id=%s', (not suspended, legacy_id))
            self._revoke_user_sessions(connection, user_id)
            connection.execute('UPDATE account_password_resets SET revoked_at=NOW() WHERE user_id=%s AND used_at IS NULL', (user_id,))
            self._audit(connection, actor, 'account.suspended' if suspended else 'account.reactivated', subject_user_id=user_id, reason=reason)
            connection.commit()
        return {'userId': user_id, 'state': 'suspended' if suspended else 'active'}

    def _replace_password(self, connection, user_id, password):
        salt = self.token_factory(24)
        digest = self.password_hasher(password, salt)
        legacy_id = connection.execute(
            """UPDATE account_users SET password_salt=%s,password_hash=%s,credential_version=credential_version+1,
               updated_at=NOW() WHERE id=%s RETURNING legacy_manager_id""", (salt,digest,user_id),
        ).fetchone()[0]
        if legacy_id is not None:
            connection.execute('UPDATE manager_users SET password_salt=%s,password_hash=%s WHERE id=%s', (salt,digest,legacy_id))
        self._revoke_user_sessions(connection, user_id)
        connection.execute('UPDATE account_password_resets SET revoked_at=NOW() WHERE user_id=%s AND used_at IS NULL', (user_id,))

    def change_password(self, token, *, current_password, new_password):
        self._validate_password(new_password)
        if not isinstance(current_password, str) or len(current_password)>1024:
            raise IdentityError('invalid', 'Invalid current password.')
        with self.connect() as connection:
            self._lock(connection)
            actor = self.resolve_actor(token, connection=connection)
            salt,digest = connection.execute('SELECT password_salt,password_hash FROM account_users WHERE id=%s FOR UPDATE', (actor.user_id,)).fetchone()
            if not hmac.compare_digest(digest, self.password_hasher(current_password,salt)):
                raise IdentityError('unauthenticated', 'Current password is incorrect.')
            self._replace_password(connection, actor.user_id, new_password)
            self._audit(connection, actor, 'password.changed', subject_user_id=actor.user_id)
            connection.commit()
        return {'changed': True, 'reauthenticationRequired': True}

    def issue_password_reset(self, *, user_id, reason, expires_in=3600):
        """CONTROLLED OPERATOR ONLY. Never expose as a normal authenticated HTTP action."""
        user_id, reason = self._id(user_id), self._reason(reason)
        if not reason:
            raise IdentityError('invalid', 'Operator recovery requires an audit reason.')
        if isinstance(expires_in,bool) or not isinstance(expires_in,int) or not 60<=expires_in<=86400:
            raise IdentityError('invalid', 'Reset lifetime must be between 60 seconds and one day.')
        with self.connect() as connection:
            self._lock(connection)
            self._assert_target(connection,user_id,active=True)
            generation = connection.execute('SELECT credential_version FROM account_users WHERE id=%s', (user_id,)).fetchone()[0]
            connection.execute('UPDATE account_password_resets SET revoked_at=NOW() WHERE user_id=%s AND used_at IS NULL', (user_id,))
            reset_id,raw_token=uuid.uuid4(),self.token_factory(32)
            connection.execute(
                """INSERT INTO account_password_resets(id,token_hash,user_id,credential_version,expires_at)
                   VALUES(%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 second'))""", (reset_id,hash_token(raw_token),user_id,generation,expires_in),
            )
            self._audit(connection,None,'password_reset.issued',subject_user_id=user_id,reason=reason,details={'authority':'controlled_operator'})
            connection.commit()
        return SecretResult(userId=user_id,resetId=str(reset_id),token=raw_token,expiresIn=expires_in)

    def reset_password(self, reset_token, password, *, client_key):
        self._admit_secret(client_key,'account-recovery')
        succeeded=False
        try:
            self._validate_password(password)
            if not isinstance(reset_token,str) or not reset_token or len(reset_token)>512:
                raise IdentityError('invalid','Invalid or expired recovery token.')
            with self.connect() as connection:
                self._lock(connection)
                row=connection.execute(
                    """SELECT r.id,r.user_id FROM account_password_resets r JOIN account_users u ON u.id=r.user_id
                       WHERE r.token_hash=%s AND r.used_at IS NULL AND r.revoked_at IS NULL AND r.expires_at>NOW()
                         AND u.state='active' AND u.credential_version=r.credential_version FOR UPDATE OF r,u""",(hash_token(reset_token),),
                ).fetchone()
                if not row:
                    raise IdentityError('invalid','Invalid or expired recovery token.')
                reset_id,user_id=row
                connection.execute('UPDATE account_password_resets SET used_at=NOW() WHERE id=%s',(reset_id,))
                self._replace_password(connection,user_id,password)
                self._audit(connection,None,'password.reset',subject_user_id=user_id,details={'authority':'controlled_operator_token'})
                connection.commit()
            succeeded=True
            return {'changed':True,'reauthenticationRequired':True}
        finally:
            self.admission.finish_login(client_key,'account-recovery',failed=not succeeded)

    def cutover_store(self, token, *, store_id=None, reason=''):
        reason=self._reason(reason)
        with self.connect() as connection:
            actor=self._lifecycle_actor(connection,token,store_id=store_id)
            self._require_owner(actor)
            connection.execute('UPDATE stores SET shared_crew_enabled=FALSE WHERE id=%s',(actor.store_id,))
            connection.execute('DELETE FROM crew_sessions WHERE store_id=%s',(actor.store_id,))
            self._audit(connection,actor,'store.shared_crew_disabled',reason=reason)
            connection.commit()
        return {'storeId':actor.store_id,'sharedCrewEnabled':False}
