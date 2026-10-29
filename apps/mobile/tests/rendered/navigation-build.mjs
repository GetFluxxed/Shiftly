import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { build } = createRequire(require.resolve('tsx'))('esbuild');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const expoModulesSource = path.join(path.dirname(require.resolve('expo/package.json')), '..', 'expo-modules-core', 'src', 'index.ts');
const output = process.argv[2] ?? '/tmp/shiftly-rendered-router.js';
const full = process.argv.includes('--full');

const fixtureModules = {
  offline: `
    export function OfflineInventoryWorkspace() { return null; }
    export function useOfflineInventory() { return { status: 'ready' }; }
  `,
  headsUp: `export function HeadsUpCard() { return null; }`,
};

await build({
  entryPoints: [path.join(root, `tests/rendered/${full ? 'navigation-full-entry' : 'navigation-entry'}.tsx`)],
  bundle: true,
  outfile: output,
  platform: 'browser',
  format: 'iife',
  resolveExtensions: ['.web.tsx', '.web.ts', '.tsx', '.ts', '.web.jsx', '.web.js', '.jsx', '.js', '.json'],
  alias: { 'react-native': 'react-native-web' },
  loader: { '.ttf': 'dataurl', '.png': 'dataurl', '.js': 'jsx' },
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"test"', 'process.env.EXPO_OS': '"web"', __DEV__: 'true' },
  banner: { js: 'var global = globalThis; var process = { env: { NODE_ENV: "test", EXPO_OS: "web" } };' },
  plugins: [{
    name: 'router-regression-fixtures',
    setup(buildApi) {
      if (full) {
        buildApi.onResolve({ filter: /^virtual:shiftly-routes$/ }, () => ({ path: 'shiftly-routes', namespace: 'fixture' }));
      }
      buildApi.onResolve({ filter: /^expo-router$/ }, () => ({ path: require.resolve('expo-router') }));
      buildApi.onResolve({ filter: /^expo-router\/build\/ExpoRoot$/ }, () => ({ path: require.resolve('expo-router/build/ExpoRoot') }));
      buildApi.onResolve({ filter: /^expo-modules-core$/ }, () => ({ path: expoModulesSource }));
      // This renderer runs only in the browser; Expo's server font collector
      // imports Node async_hooks, which is not part of a browser font load.
      buildApi.onResolve({ filter: /^\.\/serverContext$/ }, args => args.importer.includes('expo-font')
        ? { path: path.join(path.dirname(require.resolve('expo-font/package.json')), 'build/serverContext.js') }
        : undefined);
      buildApi.onResolve({ filter: /SessionProvider$/ }, () => ({ path: path.join(root, 'tests/rendered/session.tsx') }));
      buildApi.onResolve({ filter: /src\/inventory\/OfflineInventoryWorkspace$/ }, () => ({ path: 'offline', namespace: 'fixture' }));
      buildApi.onResolve({ filter: /src\/headsUp\/HeadsUpCard$/ }, () => ({ path: 'headsUp', namespace: 'fixture' }));
      if (!process.argv.includes('--visual')) {
        buildApi.onResolve({ filter: /^@expo\/vector-icons\/Ionicons$/ }, () => ({ path: path.join(root, 'tests/rendered/icons.tsx') }));
      }
      buildApi.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path: fixture }) => ({
        contents: fixture === 'shiftly-routes' ? (() => {
          const app = path.join(root, 'app');
          const files = [];
          const walk = directory => {
            for (const entry of require('node:fs').readdirSync(directory, { withFileTypes: true })) {
              const absolute = path.join(directory, entry.name);
              if (entry.isDirectory()) walk(absolute);
              else if (entry.name.endsWith('.tsx') && absolute !== path.join(app, '_layout.tsx')) files.push(absolute);
            }
          };
          walk(app); files.sort();
          const imports = files.map((file, index) => `import * as route${index} from ${JSON.stringify(file)};`).join('\n');
          const rows = files.map((file, index) => `${JSON.stringify('./' + path.relative(app, file).replaceAll(path.sep, '/'))}: route${index}`).join(',\n');
          const keys = ['./_layout.tsx', ...files.map(file => './' + path.relative(app, file).replaceAll(path.sep, '/'))];
          return `${imports}\nexport const modules = {${rows}};\nexport const routeKeys = ${JSON.stringify(keys)};`;
        })() : fixtureModules[fixture], loader: 'tsx', resolveDir: root,
      }));
    },
  }],
});
