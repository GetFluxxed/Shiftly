export interface Actor {
  userId: number;
  username: string;
  displayName: string;
  storeId: number;
  businessId: number | null;
  role: string;
  capabilities: string[];
  provenance: 'named';
}
export interface Store extends Actor { storeName: string }
export interface AccountStatus { authenticated: boolean; actor?: Actor; stores?: Store[] }
export interface IssuedSession extends AccountStatus {
  sessionToken: string; expiresIn: number; storeName: string;
}
export interface SignInFields { storeCode: string; username: string; password: string }
export interface RedemptionFields { token: string; password: string }
export interface RequestOptions { method?: 'GET' | 'POST'; body?: Record<string, unknown> }
