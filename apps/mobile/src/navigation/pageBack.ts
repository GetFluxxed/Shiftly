/** Stack removal actions that represent the user's native Back gesture. */
export function isPageBackAction(type: string): boolean {
  return type === 'GO_BACK' || type === 'POP' || type === 'POP_TO_TOP';
}
