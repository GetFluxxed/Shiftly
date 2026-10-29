import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

type RemoveEvent = { data: { action: { type: string } }; repeat: () => void };

function nativeHook(platform: 'android' | 'ios') {
  const source = readFileSync(new URL('../src/navigation/usePageBack.native.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { esModuleInterop: true, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const stateChanges: boolean[] = [];
  let hardwareBack: (() => boolean) | undefined;
  let preventRemove: ((event: RemoveEvent) => void) | undefined;
  let preventRemoveEnabled = false;
  const react = {
    useRef: <T>(current: T) => ({ current }),
    useState: <T>(initial: T) => [initial, (next: T) => stateChanges.push(Boolean(next))] as const,
    useCallback: <T>(callback: T) => callback,
    useEffect: (effect: () => void) => effect(),
  };
  const modules: Record<string, unknown> = {
    react: { __esModule: true, default: react },
    'react-native': {
      Platform: { OS: platform },
      BackHandler: { addEventListener: (_name: string, listener: () => boolean) => {
        hardwareBack = listener;
        return { remove() {} };
      } },
    },
    'expo-router': {
      useFocusEffect: (effect: () => void) => effect(),
      useIsFocused: () => true,
      usePathname: () => '/test',
      usePreventRemove: (enabled: boolean, handler: (event: RemoveEvent) => void) => {
        preventRemoveEnabled = enabled;
        preventRemove = handler;
      },
    },
    './pageBack': { isPageBackAction: (type: string) => ['GO_BACK', 'POP', 'POP_TO_TOP'].includes(type) },
  };
  const exports = {} as { usePageBack: (onBack: () => void, enabled?: boolean) => void };
  vm.runInNewContext(compiled, {
    exports,
    module: { exports },
    require: (name: string) => modules[name],
  });
  return {
    usePageBack: exports.usePageBack,
    stateChanges,
    get hardwareBack() { return hardwareBack; },
    get preventRemove() { return preventRemove; },
    get preventRemoveEnabled() { return preventRemoveEnabled; },
  };
}

test('native page Back disables interception and invokes the current Android callback when enabled', () => {
  const disabled = nativeHook('android');
  disabled.usePageBack(() => assert.fail('disabled Back must not run'), false);
  assert.equal(disabled.hardwareBack, undefined);

  const enabled = nativeHook('android');
  let calls = 0;
  enabled.usePageBack(() => { calls += 1; });
  assert.equal(enabled.hardwareBack?.(), true);
  assert.equal(calls, 1);
});

test('native page Back handles semantic iOS removal and lets forward removal continue', () => {
  const back = nativeHook('ios');
  let calls = 0;
  let repeats = 0;
  back.usePageBack(() => { calls += 1; });
  assert.equal(back.preventRemoveEnabled, true);
  back.preventRemove?.({ data: { action: { type: 'POP' } }, repeat: () => { repeats += 1; } });
  assert.equal(calls, 1);
  assert.equal(repeats, 0);

  back.preventRemove?.({ data: { action: { type: 'NAVIGATE' } }, repeat: () => { repeats += 1; } });
  assert.equal(calls, 1);
  assert.equal(repeats, 1);
  assert.equal(back.stateChanges.at(-1), true);
});
