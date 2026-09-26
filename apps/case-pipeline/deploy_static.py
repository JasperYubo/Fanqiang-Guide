"""Origin-side atomic static release deployment, preserving the application service."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tarfile

ROOT=Path('/srv/fanqiang/releases')
LINK=Path('/srv/fanqiang/current')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True);parser.add_argument('--name',required=True);args=parser.parse_args()
    if not args.name.startswith('cases-v1.0-') or '/' in args.name or '..' in args.name:raise ValueError('invalid_release_name')
    dest=ROOT/args.name
    before=str(LINK.resolve())
    if not dest.exists():
        dest.mkdir(mode=0o755)
        with tarfile.open(args.archive) as archive:
            for m in archive.getmembers():
                p=Path(m.name)
                if not m.isfile() or p.is_absolute() or '..' in p.parts or not m.name.startswith('public/'):
                    raise ValueError('invalid_archive')
            archive.extractall(dest,filter='data')
    public=dest/'public'
    home=(public/'index.html').read_text()
    for marker in ('id="chat-panel"','/assets/chat-v1.2.js','/assets/external-browser-v1.0.js','G-V0RLGGS7FB'):
        if marker not in home:raise ValueError('missing_static_contract')
    for p in dest.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
    next_link=LINK.with_name('current.cases-next')
    if next_link.is_symlink():next_link.unlink()
    if next_link.exists():raise RuntimeError('release_pointer_busy')
    next_link.symlink_to(public,target_is_directory=True)
    os.replace(next_link,LINK)
    try:
        for rel in ('','assets/chat-v1.2.js','cases/','data/cases.json','sitemap.xml'):
            url='https://fanqiang.guide/'+rel
            got=subprocess.run(['curl','--silent','--show-error','--fail','--max-time','15','--resolve','fanqiang.guide:443:127.0.0.1',url],check=True,capture_output=True).stdout
            path=public/(rel+'index.html' if not rel or rel.endswith('/') else rel)
            if got!=path.read_bytes():raise RuntimeError('origin_response_mismatch')
        subprocess.run(['systemctl','is-active','nginx','fanqiang-lookup'],check=True,capture_output=True)
    except Exception:
        next_link.symlink_to(before,target_is_directory=True);os.replace(next_link,LINK);raise
    (dest/'deployment-state.json').write_text(json.dumps({'before':before,'after':str(public),'rollback':'ln -sfn '+before+' /srv/fanqiang/current','static_files':sum(p.is_file() for p in public.rglob('*'))},indent=2))
    print(json.dumps({'ok':True,'before':before,'after':str(public)}))
if __name__=='__main__':main()
