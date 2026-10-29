import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { build } = createRequire(require.resolve('tsx'))('esbuild');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const expoModulesSource = path.join(path.dirname(require.resolve('expo/package.json')), '..', 'expo-modules-core', 'src', 'index.ts');
const output = process.argv[2] ?? '/tmp/shiftly-rendered-router.js';

const fixtureModules = {
  offline: `
    export function OfflineInventoryWorkspace() { return null; }
    export function useOfflineInventory() { return { status: 'ready' }; }
  `,
  headsUp: `export function HeadsUpCard() { return null; }`,
};

await build({
  entryPoints: [path.join(root, 'tests/rendered/navigation-entry.tsx')],
  bundle: true,
  outfile: output,
  platform: 'browser',
  format: 'iife',
  resolveExtensions: ['.web.tsx', '.web.ts', '.tsx', '.ts', '.web.jsx', '.web.js', '.jsx', '.js', '.json'],
  alias: { 'react-native': 'react-native-web' },
  loader: { '.ttf': 'dataurl', '.png': 'dataurl' },
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"test"', 'process.env.EXPO_OS': '"web"', __DEV__: 'true' },
  banner: { js: 'var global = globalThis; var process = { env: { NODE_ENV: "test", EXPO_OS: "web" } };' },
  plugins: [{
    name: 'router-regression-fixtures',
    setup(buildApi) {
      buildApi.onResolve({ filter: /^expo-router$/ }, () => ({ path: require.resolve('expo-router') }));
      buildApi.onResolve({ filter: /^expo-router\/build\/ExpoRoot$/ }, () => ({ path: require.resolve('expo-router/build/ExpoRoot') }));
      buildApi.onResolve({ filter: /^expo-modules-core$/ }, () => ({ path: expoModulesSource }));
      buildApi.onResolve({ filter: /SessionProvider$/ }, () => ({ path: path.join(root, 'tests/rendered/session.tsx') }));
      buildApi.onResolve({ filter: /src\/inventory\/OfflineInventoryWorkspace$/ }, () => ({ path: 'offline', namespace: 'fixture' }));
      buildApi.onResolve({ filter: /src\/headsUp\/HeadsUpCard$/ }, () => ({ path: 'headsUp', namespace: 'fixture' }));
      buildApi.onResolve({ filter: /^@expo\/vector-icons\/Ionicons$/ }, () => ({ path: path.join(root, 'tests/rendered/icons.tsx') }));
      buildApi.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path: fixture }) => ({
        contents: fixtureModules[fixture], loader: 'tsx', resolveDir: root,
      }));
    },
  }],
});
