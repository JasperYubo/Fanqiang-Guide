import { build } from 'esbuild';
import { mkdir, chmod, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createHash } from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
await mkdir(resolve(root,'dist'),{recursive:true});
const common={bundle:true,platform:'node',format:'esm',target:'node20',legalComments:'eof',banner:{js:"import { createRequire as __createRequire } from 'node:module'; const require = __createRequire(import.meta.url);"}};
for(const name of ['client','collector']){
 await build({...common,entryPoints:[resolve(root,'src',name+'.mjs')],outfile:resolve(root,'dist',name+'.mjs')});
 await chmod(resolve(root,'dist',name+'.mjs'),0o755);
}
const hash={};
for(const name of ['client.mjs','collector.mjs'])hash[name]=createHash('sha256').update(await readFile(resolve(root,'dist',name))).digest('hex');
await writeFile(resolve(root,'dist','build-manifest.json'),JSON.stringify({version:'0.1.0',node:process.version,files:hash},null,2)+'\n');
console.log(JSON.stringify({built:hash}));
