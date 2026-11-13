// Build into the requested directory, then bind the output to its source bytes.
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync,lstatSync} from 'node:fs';
import {resolve,relative,join} from 'node:path';
import {spawnSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..'),args=process.argv.slice(2);
const manager=JSON.parse(readFileSync(join(root,'package.json'),'utf8')).packageManager.split('@')[1];
if(!process.versions.node.startsWith('24.')||!process.env.npm_config_user_agent?.startsWith('pnpm/'+manager+' '))throw new Error('Use the pinned pnpm release with Node 24 to build Keystone');
let output=join(root,'dist');
for(let i=0;i<args.length;i++){
 if(args[i]==='--outDir'&&args[i+1])output=resolve(root,args[++i]);
 else if(args[i]!=='--emptyOutDir')throw new Error('Unsupported build option');
}
const hash=data=>createHash('sha256').update(data).digest('hex');
function files(folder){return readdirSync(folder).flatMap(name=>{const path=join(folder,name),info=lstatSync(path);if(info.isSymbolicLink())throw new Error('Linked build input');return info.isDirectory()?files(path):[path];});}
function fingerprint(){
 const paths=['package.json','pnpm-lock.yaml','tsconfig.json','vite.config.ts','index.html','scripts/build.mjs'].map(p=>join(root,p)).concat(files(join(root,'src')));
 return hash(JSON.stringify(paths.map(p=>['web/'+relative(root,p).split('\\').join('/'),hash(readFileSync(p))]).sort(([a],[b])=>a<b?-1:a>b?1:0)));
}
const before=fingerprint();
for(const command of [['node_modules/typescript/bin/tsc','--noEmit'],['node_modules/vite/bin/vite.js','build',...args]]){
 const result=spawnSync(process.execPath,command,{cwd:root,stdio:'inherit'});if(result.status!==0)process.exit(result.status??2);
}
if(fingerprint()!==before)throw new Error('Source changed during build');
const assets=files(output).filter(p=>relative(output,p)==='index.html'||relative(output,p).startsWith('assets/'));
const proof=Object.fromEntries(assets.map(p=>[relative(output,p).split('\\').join('/'),hash(readFileSync(p))]).sort(([a],[b])=>a<b?-1:a>b?1:0));
writeFileSync(join(output,'build.json'),JSON.stringify({schema_version:1,kind:'keystone.frontend-build',source_sha256:before,built_at:new Date().toISOString(),files:proof},null,2)+'\n');
