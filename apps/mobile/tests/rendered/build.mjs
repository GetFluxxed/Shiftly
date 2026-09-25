import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const require=createRequire(import.meta.url);
const { build }=createRequire(require.resolve('tsx'))('esbuild');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
await build({entryPoints:[path.join(root,process.argv[3]||'tests/rendered/entry.tsx')],bundle:true,outfile:process.argv[2],
  platform:'browser',resolveExtensions:['.web.tsx','.web.ts','.web.js','.tsx','.ts','.jsx','.js','.json'],format:'iife',jsx:'automatic',define:{'process.env.NODE_ENV':'"test"',__DEV__:'true'},
  alias:{'react-native':'react-native-web'},loader:{'.ttf':'dataurl'},
  plugins:[{name:'native-test-boundaries',setup(b){
    b.onResolve({filter:/SessionProvider$/},()=>({path:path.join(root,'tests/rendered/session.tsx')}));
    b.onResolve({filter:/^expo-router$/},()=>({path:path.join(root,'tests/rendered/router.tsx')}));
    b.onResolve({filter:/^@expo\/vector-icons\/Ionicons$/},()=>({path:path.join(root,'tests/rendered/icons.tsx')}));
  }}]});
