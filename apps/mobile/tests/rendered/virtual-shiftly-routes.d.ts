declare module 'virtual:shiftly-routes' {
  export const modules: Record<string, { default: import('react').ComponentType }>;
  export const routeKeys: string[];
}
