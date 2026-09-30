-- Add the dedicated production role and production-planning permissions.
-- Existing memberships and invitations are preserved; invitations remain crew-only
-- at the service boundary and production accounts are assigned after activation.

ALTER TABLE business_memberships
    DROP CONSTRAINT business_memberships_capabilities_check;
ALTER TABLE business_memberships
    ADD CONSTRAINT business_memberships_capabilities_check CHECK (
        capabilities <@ ARRAY[
            'reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve',
            'receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','catalog.manage',
            'memberships.manage','production.view','production.submit','production.manage','recipes.manage','forecasts.view'
        ]::TEXT[]
    );

ALTER TABLE account_store_memberships
    DROP CONSTRAINT account_store_memberships_role_check,
    DROP CONSTRAINT account_store_memberships_check,
    DROP CONSTRAINT account_store_memberships_capabilities_check,
    DROP CONSTRAINT account_store_memberships_check1,
    DROP CONSTRAINT account_store_memberships_check2;

ALTER TABLE account_store_memberships
    ADD CONSTRAINT account_store_memberships_role_check
        CHECK (role IN ('manager', 'production', 'crew', 'admin')),
    ADD CONSTRAINT account_store_memberships_capabilities_check CHECK (
        capabilities <@ ARRAY[
            'reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve',
            'receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','catalog.manage',
            'memberships.manage','production.view','production.submit','production.manage','recipes.manage','forecasts.view'
        ]::TEXT[]
    ),
    ADD CONSTRAINT account_store_memberships_admin_scope_check
        CHECK (role <> 'admin' OR business_id IS NOT NULL),
    ADD CONSTRAINT account_store_memberships_crew_capabilities_check CHECK (
        role <> 'crew' OR capabilities <@ ARRAY[
            'reports.submit','inventory.view','counts.submit','receipts.draft','catalog.propose'
        ]::TEXT[]
    ),
    ADD CONSTRAINT account_store_memberships_production_capabilities_check CHECK (
        role <> 'production' OR capabilities <@ ARRAY[
            'inventory.view','counts.submit','receipts.draft','catalog.propose','production.view','production.submit'
        ]::TEXT[]
    ),
    ADD CONSTRAINT account_store_memberships_manager_capabilities_check
        CHECK (role <> 'manager' OR NOT ('catalog.manage' = ANY(capabilities)));

ALTER TABLE account_invitations
    DROP CONSTRAINT account_invitations_capabilities_check;
ALTER TABLE account_invitations
    ADD CONSTRAINT account_invitations_capabilities_check CHECK (
        capabilities <@ ARRAY[
            'reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve',
            'receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','memberships.manage',
            'production.view','production.submit','production.manage','recipes.manage','forecasts.view'
        ]::TEXT[]
    );
