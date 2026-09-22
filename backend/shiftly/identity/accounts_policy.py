"""Named-account permissions. Roles are scoped facts, never client input authority."""
from dataclasses import dataclass

from .service import IdentityError

CREW_CAPABILITIES = frozenset({
    "reports.submit", "inventory.view", "counts.submit", "receipts.draft", "catalog.propose",
})
MANAGER_CAPABILITIES = CREW_CAPABILITIES | frozenset({
    "reports.view", "reports.manage", "counts.approve", "receipts.post", "stock.adjust", "configuration.manage",
})
MANAGER_GRANTABLE = MANAGER_CAPABILITIES | {"memberships.manage"}
ALL_CAPABILITIES = MANAGER_GRANTABLE | {"catalog.manage"}
REPORT_CAPABILITIES = frozenset({"reports.submit", "reports.view", "reports.manage"})


@dataclass(frozen=True)
class AccountActor:
    user_id: int
    username: str
    display_name: str
    store_id: int
    business_id: int | None
    role: str
    capabilities: frozenset[str]
    legacy_manager_id: int | None
    credential_version: int
    provenance: str = "named"

    def as_dict(self):
        return {
            "userId": self.user_id, "username": self.username, "displayName": self.display_name,
            "storeId": self.store_id, "businessId": self.business_id, "role": self.role,
            "capabilities": sorted(self.capabilities), "provenance": self.provenance,
        }


def capabilities_for(role, grants=(), *, mapped=True):
    """Admins receive explicit intersected delegation; managers cannot manage catalog."""
    grants = frozenset(grants)
    if not grants <= ALL_CAPABILITIES:
        raise IdentityError("invalid", "Unknown permission.")
    if role == "owner":
        capabilities = ALL_CAPABILITIES
    elif role == "admin":
        capabilities = grants
    elif role == "manager":
        if not grants <= MANAGER_GRANTABLE:
            raise IdentityError("forbidden", "Managers cannot manage the shared catalog.")
        capabilities = MANAGER_CAPABILITIES | grants
    elif role == "crew":
        if not grants <= CREW_CAPABILITIES:
            raise IdentityError("forbidden", "Crew cannot receive approval or posting permissions.")
        capabilities = frozenset({"reports.submit"}) | grants
    else:
        raise IdentityError("forbidden", "No active account role.")
    return frozenset(capabilities if mapped else capabilities & REPORT_CAPABILITIES)


def assert_grant(actor, role, grants=(), *, business_id=None):
    """Validate a requested local membership; ownership remains a separate operation."""
    if "memberships.manage" not in actor.capabilities:
        raise IdentityError("forbidden", "Team management permission is required.")
    if business_id is not None and actor.business_id != business_id:
        raise IdentityError("forbidden", "Business scope does not match.")
    if role not in {"manager", "crew", "admin"}:
        raise IdentityError("invalid", "Invalid store role.")
    if actor.role == "manager" and role != "crew":
        raise IdentityError("forbidden", "Managers can manage crew only.")
    if actor.role == "admin" and role == "admin":
        raise IdentityError("forbidden", "Only an owner appoints administrators.")
    if actor.role not in {"owner", "admin", "manager"}:
        raise IdentityError("forbidden", "This account cannot manage memberships.")
    effective = capabilities_for(role, grants)
    if actor.role != "owner" and not effective <= actor.capabilities:
        raise IdentityError("forbidden", "Cannot grant permissions beyond your own authority.")
    return frozenset(grants)
