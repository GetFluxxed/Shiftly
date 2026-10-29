// Only the browser test renderer consumes ReactDOM; native application code does not.
declare module 'react-dom/client' {
  export function createRoot(container: Element): { render(children: import('react').ReactNode): void };
}
