#!/usr/bin/env python3
"""Linux-only portable release packager. No installation, publishing or global configuration."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, shutil, stat, sys, tarfile, tempfile, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
REPO=APP.parents[1]
VERSION="0.1.0"
NODE_VERSION="24.18.1"
EPOCH=int(datetime(2026,11,2,tzinfo=timezone.utc).timestamp())
NAMES={"windows-x64":"fanqiang-diagnostics-0.1.0-windows-x64.zip","linux-x64":"fanqiang-diagnostics-0.1.0-linux-x64.tar.gz"}
NPM_NAME="fanqiang-diagnostics-0.1.0-npm.tgz"

INSTALLER=r"""
import {promises as fs} from 'node:fs';
import {createHash} from 'node:crypto';
import {homedir} from 'node:os';
import {dirname,join,resolve,sep,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
if(process.platform!=='linux'||process.arch!=='x64')throw new Error('This installer supports Linux x64 only.');
const source=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const manifest=JSON.parse(await fs.readFile(join(source,'PACKAGING.json'),'utf8'));
if(manifest.version!=='0.1.0'||manifest.platform!=='linux-x64'||!manifest.files||!/^[a-f0-9]{64}$/.test(manifest.client_sha256))throw new Error('Invalid package manifest.');
const args=process.argv.slice(2);
if(args.length&&!(args.length===2&&args[0]==='--prefix'&&isAbsolute(args[1])&&resolve(args[1])!==sep))throw new Error('Usage: installer [--prefix /absolute/program/path]');
const base=args.length?resolve(args[1]):join(homedir(),'.local','share','fanqiang-diagnostics'),releases=join(base,'releases');
const destination=join(releases,manifest.version+'-'+manifest.client_sha256.slice(0,12));
async function safeDirectory(path){
 let current=sep;
 for(const part of resolve(path).split(sep).filter(Boolean)){
  current=join(current,part);
  try{const st=await fs.lstat(current);if(!st.isDirectory()||st.isSymbolicLink())throw new Error('Unsafe directory: '+current);}
  catch(error){if(error.code==='ENOENT')await fs.mkdir(current,{mode:0o700});else throw error;}
 }
}
const validRelative=p=>typeof p==='string'&&p.length<240&&!p.startsWith('/')&&!p.includes('\\')&&!p.split('/').some(x=>!x||x==='.'||x==='..');
const entries=Object.entries(manifest.files).sort(([a],[b])=>a.localeCompare(b));
for(const [relative,info] of entries){
 if(!validRelative(relative)||!info||!/^[a-f0-9]{64}$/.test(info.sha256)||![0o644,0o755].includes(info.mode))throw new Error('Invalid package entry.');
 const input=join(source,relative),st=await fs.lstat(input);
 if(!st.isFile()||st.isSymbolicLink()||createHash('sha256').update(await fs.readFile(input)).digest('hex')!==info.sha256)throw new Error('Package checksum mismatch: '+relative);
}
await safeDirectory(releases);await fs.chmod(base,0o700);
let exists=false;
try{const st=await fs.lstat(destination);if(!st.isDirectory()||st.isSymbolicLink())throw new Error('Unsafe installation.');exists=true;}
catch(error){if(error.code!=='ENOENT')throw error;}
if(exists){
 for(const [relative,info] of entries){
  const p=join(destination,relative),st=await fs.lstat(p);
  if(!st.isFile()||st.isSymbolicLink()||createHash('sha256').update(await fs.readFile(p)).digest('hex')!==info.sha256)throw new Error('Existing version differs; no files were overwritten.');
 }
}else{
 const staging=await fs.mkdtemp(join(releases,'.install-'));
 try{
  for(const [relative,info] of entries){
   const output=join(staging,relative);await fs.mkdir(dirname(output),{recursive:true,mode:0o700});
   await fs.copyFile(join(source,relative),output);await fs.chmod(output,info.mode);
  }
  await fs.copyFile(join(source,'PACKAGING.json'),join(staging,'PACKAGING.json'));
  await fs.rename(staging,destination);
 }catch(error){
  if(dirname(staging)===releases&&staging.startsWith(join(releases,'.install-')))await fs.rm(staging,{recursive:true,force:true});
  throw error;
 }
}
const marker='# fanqiang-diagnostics-managed-launcher';
const quote=s=>"'"+s.replace(/'/g,"'\"'\"'")+"'";
async function launcher(name,target){
 const p=join(base,name),body='#!/bin/sh\n'+marker+'\nexec '+quote(join(destination,target))+' "$@"\n';
 try{const st=await fs.lstat(p);if(!st.isFile()||st.isSymbolicLink()||!(await fs.readFile(p,'utf8')).includes(marker))throw new Error('Refusing to overwrite a user launcher: '+p);}
 catch(error){if(error.code!=='ENOENT')throw error;}
 const temp=p+'.new-'+process.pid;await fs.writeFile(temp,body,{mode:0o700,flag:'wx'});await fs.rename(temp,p);
}
await launcher('start.sh','开始诊断.sh');await launcher('generate-mcp-config.sh','生成MCP配置.sh');
console.log('安装完成：'+destination+'\n启动：'+join(base,'start.sh')+'\n生成MCP配置：'+join(base,'generate-mcp-config.sh')+'\n已有session-*报告与回执保留；未创建后台服务。');
"""
START_SH="""#!/bin/sh
set -eu
fq_diag_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$fq_diag_dir/runtime/bin/node" "$fq_diag_dir/dist/client.mjs" --web --open "$@"
"""
CONFIG_SH="""#!/bin/sh
set -eu
fq_diag_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
"$fq_diag_dir/runtime/bin/node" "$fq_diag_dir/dist/client.mjs" --print-config > "$fq_diag_dir/mcp-config.json"
printf '%s\\n' "MCP 配置已写入：$fq_diag_dir/mcp-config.json"
cat "$fq_diag_dir/mcp-config.json"
"""
INSTALL_SH="""#!/bin/sh
set -eu
fq_diag_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$fq_diag_dir/runtime/bin/node" "$fq_diag_dir/scripts/install-linux.mjs" "$@"
"""
START_CMD="""@echo off
chcp 65001 >nul
setlocal
"%~dp0runtime\\node.exe" "%~dp0dist\\client.mjs" --web --open
set "FQ_DIAG_EXIT=%ERRORLEVEL%"
if not "%FQ_DIAG_EXIT%"=="0" (
  echo 启动未完成，请保留窗口中的错误信息。
  pause
)
exit /b %FQ_DIAG_EXIT%
"""
CONFIG_CMD="""@echo off
chcp 65001 >nul
setlocal
"%~dp0runtime\\node.exe" "%~dp0dist\\client.mjs" --print-config > "%~dp0mcp-config.json"
if errorlevel 1 (
  echo 配置生成失败，请确认已完整解压目录。
  pause
  exit /b 1
)
echo MCP 配置已写入本目录的 mcp-config.json。请手动合并到AI客户端设置。
type "%~dp0mcp-config.json"
pause
"""
LEGAL="""打包法律声明

本包为Fanqiang Diagnostics 0.1.0便携分发，不代表Node.js或其他依赖项目为本工具背书。
应用源码采用LICENSE.txt中的MIT许可证；随包Node.js原始许可证和第三方声明见licenses/Node-LICENSE.txt。
licenses/THIRD_PARTY_NOTICES.txt收集构建时SDK依赖的许可证参考资料；代码裁剪可能使部分依赖未进入最终程序。dist/client.mjs保留的上游法律注释仍有效。
Node.js可执行文件没有修改。运行时版本24.18.1，原始归档及经校验的SHA256记录在PACKAGING.json。
重新分发时请保留对应版权、许可证与声明；各组成部分以其原始许可证为准。
工具按许可证约定提供，不保证测量结果或网络服务可用性；接收回执不构成设备认证或真实性背书。
Windows包在Linux上打包及静态核验，尚未完成Windows原生运行测试。
"""

def sha(path):
 d=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""):d.update(b)
 return d.hexdigest()

def write(path,content,mode=0o644,crlf=False):
 path.parent.mkdir(parents=True,exist_ok=True)
 content=content.replace("\r\n","\n")
 payload=(content.replace("\n","\r\n") if crlf else content).encode("utf-8")
 if not path.is_file() or path.read_bytes()!=payload:path.write_bytes(payload)
 path.chmod(mode)

def dependency_notices():
 todo=[APP/"node_modules/@modelcontextprotocol/sdk"];seen=set();blocks=[]
 if not (todo[0]/"package.json").is_file():raise RuntimeError("Install locked build dependencies first.")
 while todo:
  directory=todo.pop().resolve()
  if directory in seen:continue
  seen.add(directory);pkg=json.loads((directory/"package.json").read_text())
  heading=pkg.get("name",directory.name)+" "+pkg.get("version","")
  content=[heading,"Declared license: "+str(pkg.get("license","See upstream notices"))]
  notices=[p for p in directory.iterdir() if p.is_file() and p.name.lower().startswith(("license","licence","copying","notice")) and p.stat().st_size<=1048576]
  for p in sorted(notices):content.extend(["\n--- "+p.name+" ---",p.read_text(errors="replace")])
  if not notices:content.append("No root license text file found; consult package metadata and bundled source notices.")
  blocks.append((heading,"\n".join(content)))
  for name in sorted(set(pkg.get("dependencies",{}))|set(pkg.get("optionalDependencies",{}))|set(pkg.get("peerDependencies",{}))):
   cursor=directory
   while cursor!=cursor.parent:
    candidate=cursor/"node_modules"/name
    if (candidate/"package.json").is_file():todo.append(candidate);break
    if cursor==APP.parent:break
    cursor=cursor.parent
 header=("Third-party license reference for the self-contained client bundle.\n"
         "This follows installed SDK dependency metadata. Tree-shaking may omit some listed packages from executable code.\n"
         "Original source notices in dist/client.mjs remain intact. Node.js notices are separate in Node-LICENSE.txt.\n\n")
 return header+"\n\n==============================\n\n".join(b for _,b in sorted(blocks))+"\n"

def extract_runtime(stage,vendor,platform,checks):
 suffix="win-x64.zip" if platform=="windows-x64" else "linux-x64.tar.xz"
 name="node-v"+NODE_VERSION+"-"+suffix;archive=vendor/name;record=checks.get(name)
 if not record or archive.stat().st_size!=record["bytes"] or sha(archive)!=record["sha256"]:raise RuntimeError("Runtime checksum mismatch: "+name)
 prefix="node-v"+NODE_VERSION+("-win-x64/" if platform=="windows-x64" else "-linux-x64/")
 node=stage/("runtime/node.exe" if platform=="windows-x64" else "runtime/bin/node")
 license_path=stage/"licenses/Node-LICENSE.txt"
 node.parent.mkdir(parents=True,exist_ok=True);license_path.parent.mkdir(parents=True,exist_ok=True)
 if platform=="windows-x64":
  with zipfile.ZipFile(archive) as z:
   for source,target in [(prefix+"node.exe",node),(prefix+"LICENSE",license_path)]:
    with z.open(source) as incoming,target.open("wb") as outgoing:shutil.copyfileobj(incoming,outgoing,1048576)
 else:
  wanted={prefix+"bin/node":node,prefix+"LICENSE":license_path}
  with tarfile.open(archive,"r:xz") as t:
   for member in t:
    if member.name not in wanted:continue
    if not member.isfile():raise RuntimeError("Non-regular runtime archive entry.")
    target=wanted.pop(member.name)
    with t.extractfile(member) as incoming,target.open("wb") as outgoing:shutil.copyfileobj(incoming,outgoing,1048576)
    if not wanted:break
   if wanted:raise RuntimeError("Missing runtime archive members.")
 node.chmod(0o755 if platform=="linux-x64" else 0o644);license_path.chmod(0o644)
 return {"version":NODE_VERSION,"source_archive":name,"source_archive_sha256":record["sha256"],"node_sha256":sha(node)}

def build_stage(stage,platform,vendor,checks,notices):
 stage.mkdir();(stage/"dist").mkdir()
 for source,target in [(APP/"dist/client.mjs","dist/client.mjs"),(APP/"LICENSE.txt","LICENSE.txt"),(APP/"README.md","README.md"),(APP/"README.md","使用说明.txt")]:
  shutil.copyfile(source,stage/target);(stage/target).chmod(0o644)
 runtime=extract_runtime(stage,vendor,platform,checks)
 write(stage/"licenses/THIRD_PARTY_NOTICES.txt",notices);write(stage/"打包法律声明.txt",LEGAL)
 if platform=="windows-x64":
  write(stage/"开始诊断.cmd",START_CMD,crlf=True);write(stage/"生成MCP配置.cmd",CONFIG_CMD,crlf=True)
 else:
  write(stage/"开始诊断.sh",START_SH,0o755);write(stage/"生成MCP配置.sh",CONFIG_SH,0o755)
  write(stage/"安装到当前用户.sh",INSTALL_SH,0o755);write(stage/"scripts/install-linux.mjs",INSTALLER)
 files={p.relative_to(stage).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size,"mode":stat.S_IMODE(p.stat().st_mode)} for p in sorted(stage.rglob("*")) if p.is_file()}
 manifest={"schema_version":"1","version":VERSION,"platform":platform,"archive_epoch":EPOCH,"runtime":runtime,"client_sha256":sha(stage/"dist/client.mjs"),"files":files}
 write(stage/"PACKAGING.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
 return manifest

def make_archive(stage,output,platform):
 if platform=="windows-x64":
  with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
   for p in sorted(stage.rglob("*")):
    if not p.is_file():continue
    info=zipfile.ZipInfo(stage.name+"/"+p.relative_to(stage).as_posix(),datetime.fromtimestamp(EPOCH,timezone.utc).timetuple()[:6])
    info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|stat.S_IMODE(p.stat().st_mode))<<16
    with p.open("rb") as incoming,z.open(info,"w") as outgoing:shutil.copyfileobj(incoming,outgoing,1048576)
 else:
  with output.open("wb") as raw,gzip.GzipFile(filename="",mode="wb",fileobj=raw,mtime=EPOCH,compresslevel=9) as gz,tarfile.open(fileobj=gz,mode="w",format=tarfile.GNU_FORMAT) as t:
   for p in sorted(stage.rglob("*")):
    if not p.is_file():continue
    info=t.gettarinfo(str(p),stage.name+"/"+p.relative_to(stage).as_posix())
    info.uid=info.gid=0;info.uname=info.gname="";info.mtime=EPOCH
    with p.open("rb") as incoming:t.addfile(info,incoming)

def verify_archive(path,root,manifest,platform):
 expected={root+"/"+k:v["sha256"] for k,v in manifest["files"].items()};seen=set()
 def check(name,incoming):
  if name in seen:raise RuntimeError("Duplicate archive member.")
  seen.add(name)
  if name==root+"/PACKAGING.json":
   if json.load(incoming)!=manifest:raise RuntimeError("Manifest mismatch.")
  elif expected.get(name)!=hashlib.file_digest(incoming,"sha256").hexdigest():raise RuntimeError("Archive hash mismatch: "+name)
 if platform=="windows-x64":
  with zipfile.ZipFile(path) as z:
   for m in z.infolist():
    if m.is_dir():raise RuntimeError("Unexpected directory member.")
    with z.open(m) as incoming:check(m.filename,incoming)
 else:
  with tarfile.open(path,"r:gz") as t:
   for m in t:
    if not m.isfile():raise RuntimeError("Unexpected non-file member.")
    with t.extractfile(m) as incoming:check(m.name,incoming)
 if seen!=set(expected)|{root+"/PACKAGING.json"}:raise RuntimeError("Archive file set mismatch.")

def main():
 if sys.platform!="linux":raise SystemExit("Run this packager on Linux only.")
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--vendor",type=Path,default=Path("/opt/fanqiang-diagnostics-v0.1/vendor"))
 parser.add_argument("--output",type=Path,default=Path("/opt/fanqiang-diagnostics-v0.1/artifacts"))
 parser.add_argument("--wait-seconds",type=int,default=120);args=parser.parse_args()
 if not 0<=args.wait_seconds<=600:raise SystemExit("Invalid wait.")
 end=time.monotonic()+args.wait_seconds
 while not (APP/"dist/client.mjs").is_file():
  if time.monotonic()>=end:raise SystemExit("Finish npm run build before packaging.")
  time.sleep(1)
 build=json.loads((APP/"dist/build-manifest.json").read_text())
 if build.get("files",{}).get("client.mjs")!=sha(APP/"dist/client.mjs"):raise RuntimeError("Bundle/build manifest mismatch.")
 if json.loads((APP/"package.json").read_text())["version"]!=VERSION:raise RuntimeError("Package version mismatch.")
 checks={r["file"]:r for r in json.loads((args.vendor/"runtime-checksums.json").read_text())}
 args.output.mkdir(parents=True,exist_ok=True)
 notices=dependency_notices()
 if not (APP/"LICENSE.txt").is_file() or (APP/"LICENSE.txt").read_bytes()!=(REPO/"LICENSE").read_bytes():shutil.copyfile(REPO/"LICENSE",APP/"LICENSE.txt")
 write(APP/"licenses/THIRD_PARTY_NOTICES.txt",notices)
 records=[]
 for platform,filename in NAMES.items():
  with tempfile.TemporaryDirectory(prefix=".portable-",dir=args.output) as scratch:
   scratch=Path(scratch);stage=scratch/("fanqiang-diagnostics-"+VERSION+"-"+platform)
   manifest=build_stage(stage,platform,args.vendor,checks,notices);archive=scratch/filename
   if manifest["client_sha256"]!=build["files"]["client.mjs"]:raise RuntimeError("Client changed during packaging; rebuild the release.")
   make_archive(stage,archive,platform);verify_archive(archive,stage.name,manifest,platform)
   destination=args.output/filename;os.replace(archive,destination)
   records.append({"file":filename,"sha256":sha(destination),"bytes":destination.stat().st_size,"client_sha256":manifest["client_sha256"],"platform":platform,"files":len(manifest["files"])+1})
 sums=[sha(args.output/n)+"  "+n for n in sorted([*NAMES.values(),NPM_NAME]) if (args.output/n).is_file()]
 write(args.output/"SHA256SUMS.txt","\n".join(sums)+"\n")
 summary={"version":VERSION,"node_version":NODE_VERSION,"archives_verified":True,"artifacts":records}
 write(args.output/"portable-release-manifest.json",json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
