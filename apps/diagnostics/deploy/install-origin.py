#!/usr/bin/env python3
"""Run as root on the existing fanqiang Linux origin, after copying release archive."""
import hashlib, json, os, pathlib, subprocess, tarfile, time, urllib.request
ROOT = pathlib.Path('/opt/fanqiang-diagnostics')
CONF = pathlib.Path('/etc/nginx/conf.d/fanqiang.conf')
ARCHIVE = ROOT / 'incoming-v0.1.0.tar.gz'
stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
release = ROOT / 'releases' / ('v0.1.0-' + stamp)
backup = ROOT / 'backups' / stamp
if os.geteuid() != 0: raise SystemExit('origin_root_required')
if not ARCHIVE.is_file(): raise SystemExit('release_archive_missing')
release.mkdir(parents=True)
backup.mkdir(parents=True)
with tarfile.open(ARCHIVE, 'r:gz') as archive:
    for item in archive.getmembers():
        p = pathlib.PurePosixPath(item.name)
        if p.is_absolute() or '..' in p.parts or item.issym() or item.islnk() or not (item.isfile() or item.isdir()):
            raise SystemExit('invalid_archive_member')
    archive.extractall(release, filter='data')
for name in ['collector.mjs', 'collector.service', 'nginx-locations.conf', 'site/index.html']:
    if not (release/name).is_file(): raise SystemExit('incomplete_release')
oldconf = CONF.read_bytes()
if oldconf.count(b'root /srv/fanqiang/current;') != 1: raise SystemExit('nginx_structure_changed')
if b'# BEGIN FANQIANG DIAGNOSTICS' in oldconf: raise SystemExit('diagnostics_already_deployed')
(backup/'fanqiang.conf').write_bytes(oldconf)
unit = pathlib.Path('/etc/systemd/system/fanqiang-diagnostics.service')
previous_unit = unit.read_bytes() if unit.exists() else None
if previous_unit: (backup/'collector.service').write_bytes(previous_unit)
current = ROOT/'current'
previous_link = os.readlink(current) if current.is_symlink() else None
if current.exists() and not current.is_symlink(): raise SystemExit('current_is_not_symlink')
downloads = pathlib.Path('/srv/fanqiang-diagnostics/downloads')
download_sources = release/'downloads'
if not download_sources.is_dir(): raise SystemExit('release_downloads_missing')
# Validate the entire immutable set before changing the active release or service.
for path in download_sources.iterdir():
    if not path.is_file() or path.is_symlink(): raise SystemExit('download_not_file')
    target = downloads/path.name
    if target.is_symlink() or (target.exists() and not target.is_file()): raise SystemExit('unsafe_download_target')
    if target.exists() and hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
        raise SystemExit('immutable_download_collision')
was_enabled = subprocess.run(['systemctl','is-enabled','--quiet','fanqiang-diagnostics.service'],check=False).returncode == 0
was_active = subprocess.run(['systemctl','is-active','--quiet','fanqiang-diagnostics.service'],check=False).returncode == 0
newconf=oldconf.replace(b'root /srv/fanqiang/current;',(release/'nginx-locations.conf').read_bytes()+b'\n    root /srv/fanqiang/current;',1)
new_link = ROOT/('current.new-' + stamp)
added_downloads = []
conf_changed = False
service_changed = False

def atomic_write(path, content):
    staged = path.with_name('.' + path.name + '.diagnostics-' + stamp)
    try:
        with staged.open('xb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        staged.chmod(0o644)
        os.replace(staged, path)
    finally:
        if staged.exists(): staged.unlink()

try:
    new_link.symlink_to(release)
    os.replace(new_link, current)
    downloads.mkdir(parents=True, exist_ok=True)
    for path in download_sources.iterdir():
        target = downloads/path.name
        if not target.exists():
            atomic_write(target,path.read_bytes())
            added_downloads.append(target)
    atomic_write(unit,(release/'collector.service').read_bytes())
    service_changed = True
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','fanqiang-diagnostics.service'],check=True)
    subprocess.run(['systemctl','restart','fanqiang-diagnostics.service'],check=True)
    for attempt in range(25):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8792/health',timeout=2) as response:
                health=json.load(response)
            if health.get('ok') and health.get('service') == 'fanqiang-diagnostics' and health.get('version') == '0.1.0': break
        except Exception:
            pass
        time.sleep(0.2)
    else: raise RuntimeError('collector_health_failed')
    atomic_write(CONF,newconf)
    conf_changed = True
    subprocess.run(['nginx','-t'],check=True)
    subprocess.run(['systemctl','reload','nginx'],check=True)
except Exception:
    if conf_changed:
        atomic_write(CONF,oldconf)
        subprocess.run(['nginx','-t'],check=False)
        subprocess.run(['systemctl','reload','nginx'],check=False)
    if service_changed:
        subprocess.run(['systemctl','stop','fanqiang-diagnostics.service'],check=False)
    if previous_link:
        restore_link = ROOT/('current.restore-' + stamp)
        restore_link.symlink_to(previous_link)
        os.replace(restore_link,current)
    elif current.is_symlink(): current.unlink()
    if new_link.is_symlink(): new_link.unlink()
    if service_changed:
        if previous_unit is not None: atomic_write(unit,previous_unit)
        elif unit.exists(): unit.unlink()
        subprocess.run(['systemctl','daemon-reload'],check=False)
        subprocess.run(['systemctl','enable' if was_enabled else 'disable','fanqiang-diagnostics.service'],check=False)
        if was_active: subprocess.run(['systemctl','start','fanqiang-diagnostics.service'],check=False)
    for target in added_downloads: target.unlink(missing_ok=True)
    raise
evidence={'version':'0.1.0','deployed_at':stamp,'release':str(release),'backup':str(backup),'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),'nginx_before_sha256':hashlib.sha256(oldconf).hexdigest(),'nginx_after_sha256':hashlib.sha256(newconf).hexdigest(),'service':'fanqiang-diagnostics.service','health':health}
(ROOT/'deployment.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence))
