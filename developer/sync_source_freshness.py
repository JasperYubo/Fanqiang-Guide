"""Synchronize only the published, allowlisted metadata snapshot; never fetch tools.

The HTTPS source is fixed. No credentials, URL arguments, redirects, code execution,
release changes, or authored knowledge rewrites are supported. Validation precedes
atomic replacement; errors leave the previous successful file untouched.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = "https://raw.githubusercontent.com/JasperYubo/Fanqiang-Guide/main/data/source-freshness.json"
MAX_BYTES = 4 * 1024 * 1024
MAX_LIBRARY_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT = 10
TOTAL_TIMEOUT = 30
TTL_HOURS = 48
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
ERROR = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
TOP_KEYS = {"schema_version", "generated_at", "source_run_at", "freshness_ttl_hours", "scope",
            "input_sha256", "record_count", "repository_count", "counts", "records"}
ROW_KEYS = {"scope", "status", "knowledge_checked_at", "source_checked_at", "last_attempt_at", "expires_at",
            "repository_status", "release_status", "error_code", "requested_repository", "repository",
            "latest_release", "repository_resolution", "release_resolution"}
AVAILABILITY_KEYS = {"repository_availability", "installation_source_status", "availability_checked_at", "availability_notice"}
AVAILABILITIES = {"available", "unavailable", "unknown", "not_monitored"}
STATUSES = {"current", "stale", "unknown", "unmonitored"}


class SyncError(RuntimeError):
    pass


def require(condition, code="invalid_snapshot"):
    if not condition:
        raise SyncError(code)


def timestamp(value, nullable=False):
    if value is None and nullable:
        return None
    require(isinstance(value, str) and len(value) <= 40, "invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None, "invalid_timestamp")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise SyncError("invalid_timestamp") from None


def text(value, maximum=1024):
    require(isinstance(value, str) and 0 < len(value) <= maximum and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), "invalid_text")
    return value


def slug(value):
    require(isinstance(value, str) and SLUG.fullmatch(value) and value.split('/')[1] not in {'.', '..'}, "invalid_repository")
    return value


def github_url(value, repository, release=False):
    text(value, 4096)
    try:
        parts = urllib.parse.urlsplit(value)
        decoded = urllib.parse.unquote(parts.path)
        require(parts.scheme == "https" and parts.netloc == "github.com" and not parts.query and not parts.fragment
                and '\\' not in decoded and not any(p in {'.', '..'} for p in decoded.split('/')), "invalid_github_url")
        prefix = '/' + slug(repository)
        require(decoded.lower().startswith((prefix + '/releases/tag/').lower()) if release else decoded.lower() == prefix.lower(), "invalid_github_url")
        return decoded
    except ValueError:
        raise SyncError("invalid_github_url") from None


def library_records(value):
    require(isinstance(value, list) and 0 < len(value) <= 2000, "invalid_library")
    records = {}
    for row in value:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and row['id'] not in records
                and isinstance(row.get('verification'), dict) and isinstance(row['verification'].get('checked_at'), str), "invalid_library")
        require(re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}',row['id']), 'invalid_library')
        try:require(date.fromisoformat(row['verification']['checked_at']).isoformat()==row['verification']['checked_at'], 'invalid_knowledge_date')
        except ValueError:raise SyncError('invalid_knowledge_date') from None
        records[row['id']] = row
    return records


def configured_slug(row):
    value = row.get('repository')
    require(isinstance(value, str), "repository_not_in_local_library")
    parts = urllib.parse.urlsplit(value)
    require(parts.scheme == 'https' and parts.netloc == 'github.com' and not parts.query and not parts.fragment, "repository_not_in_local_library")
    name = parts.path.strip('/')
    if name.endswith('.git'):
        name = name[:-4]
    return slug(name)


def resolution(value, requested, repository, checked):
    if value is None:
        require(repository.lower() == requested.lower(), "missing_migration_provenance")
        return
    require(isinstance(value, dict) and set(value) == {'full_name', 'checked_at', 'api_redirect_chain'}, "invalid_migration")
    require(value['full_name'] == repository and value['checked_at'] == checked, "invalid_migration")
    chain = value['api_redirect_chain']
    require(isinstance(chain, list) and 2 <= len(chain) <= 4 and len(set(chain)) == len(chain)
            and chain[0] == 'https://api.github.com/repos/' + requested, "invalid_migration")
    for url in chain:
        text(url, 4096);parts = urllib.parse.urlsplit(url)
        require(parts.scheme == 'https' and parts.netloc == 'api.github.com' and not parts.query and not parts.fragment
                and '%' not in parts.path and '\\' not in parts.path, "invalid_migration")
        if parts.path.startswith('/repos/'):
            slug(parts.path[len('/repos/'):])
        else:
            require(re.fullmatch(r'/repositories/[1-9][0-9]{0,19}', parts.path), "invalid_migration")
    if urllib.parse.urlsplit(chain[-1]).path.startswith('/repos/'):
        require(urllib.parse.urlsplit(chain[-1]).path[len('/repos/'):].lower() == repository.lower(), "invalid_migration")


def validate_snapshot(data, library, *, now, previous=None, library_sha256=None):
    records = library_records(library)
    require(isinstance(data, dict) and set(data) in (TOP_KEYS, TOP_KEYS | {'availability_counts'}) and type(data['schema_version']) is int and data['schema_version'] == 1)
    require(data['scope'] == 'repository_metadata_only' and type(data['freshness_ttl_hours']) is int and data['freshness_ttl_hours'] == TTL_HOURS)
    generated, source_run = timestamp(data['generated_at']), timestamp(data['source_run_at'])
    require(source_run <= generated <= now + timedelta(minutes=5), "future_snapshot")
    require(isinstance(data['records'], dict) and set(data['records']) == set(records), "record_ids_mismatch")
    require(type(data['record_count']) is int and data['record_count'] == len(records))
    hashes = data['input_sha256']
    require(isinstance(hashes, dict) and set(hashes) == {'library', 'manifest', 'upstream'}
            and all(isinstance(v, str) and HEX.fullmatch(v) for v in hashes.values()))
    if library_sha256 is not None:require(hashes["library"] == library_sha256, "library_hash_mismatch")
    counts = {status: 0 for status in STATUSES};repositories = set()
    with_availability = 'availability_counts' in data
    availability_counts = {status: 0 for status in AVAILABILITIES}
    expected_row_keys = ROW_KEYS | AVAILABILITY_KEYS if with_availability else ROW_KEYS
    for ident, row in data['records'].items():
        require(isinstance(row, dict) and set(row) == expected_row_keys and row['scope'] == 'repository_metadata_only')
        require(row['status'] in STATUSES and row['knowledge_checked_at'] == records[ident]['verification']['checked_at'], "knowledge_date_changed")
        counts[row['status']] += 1
        source_at, attempt, expiry = [timestamp(row[k], True) for k in ['source_checked_at','last_attempt_at','expires_at']]
        require(all(v is None or v <= source_run for v in [source_at, attempt]), "future_observation")
        require((source_at is None and expiry is None) or (source_at is not None and expiry == source_at + timedelta(hours=TTL_HOURS)), "invalid_expiry")
        require(row['error_code'] is None or isinstance(row['error_code'], str) and ERROR.fullmatch(row['error_code']), "invalid_error_code")
        if with_availability:
            expected = ('not_monitored' if row['status'] == 'unmonitored' else
                        'available' if row['repository_status'] == 'ok' else
                        'unavailable' if row['repository_status'] == 'unavailable' and row['error_code'] == 'repository_not_found' else 'unknown')
            installation = {'not_monitored':'not_verified', 'available':'requires_release_verification',
                            'unavailable':'withheld', 'unknown':'not_verified'}[expected]
            require(row['repository_availability'] == expected and row['installation_source_status'] == installation,
                    'availability_evidence_mismatch')
            require(row['availability_checked_at'] == row['last_attempt_at'], 'availability_time_mismatch')
            if expected == 'unavailable':text(row['availability_notice'])
            else:require(row['availability_notice'] is None, 'availability_evidence_mismatch')
            availability_counts[expected] += 1
        if row['status'] == 'unmonitored':
            if previous is not None and ident in previous['records']:require(previous['records'][ident]['last_attempt_at'] is None, 'successful_evidence_lost')
            require(row['repository_status'] == 'not_monitored' and row['release_status'] == 'not_checked'
                    and all(row[k] is None for k in ROW_KEYS - {'scope','status','knowledge_checked_at','repository_status','release_status'}))
            continue
        requested = slug(row['requested_repository']);repositories.add(requested.lower())
        require(requested.lower() == configured_slug(records[ident]).lower(), "repository_not_in_local_library")
        require(attempt is not None and row['repository_status'] in {'ok','unavailable','error'}
                and row['release_status'] in {'ok','none','error','not_checked'})
        require(source_at is None or source_at <= attempt, 'future_observation')
        repo, release = row['repository'], row['latest_release']
        if repo is not None:
            require(isinstance(repo, dict) and set(repo) == {'full_name','url','archived','disabled','pushed_at','checked_at'})
            slug(repo['full_name']);github_url(repo['url'], repo['full_name'])
            require(type(repo['archived']) is bool and type(repo['disabled']) is bool)
            timestamp(repo['pushed_at'], True);require(timestamp(repo['checked_at']) <= attempt, "future_observation")
            require(source_at is None or source_at <= timestamp(repo['checked_at']), 'source_check_newer_than_evidence')
            resolution(row['repository_resolution'], requested, repo['full_name'], repo['checked_at'])
        else:
            require(row['repository_status'] != 'ok' and row['repository_resolution'] is None)
        if release is not None:
            require(row['release_status'] != 'none')
            require(isinstance(release, dict) and set(release) == {'tag_name','url','published_at','checked_at','repository_full_name'})
            name = slug(release['repository_full_name']);tag = text(release['tag_name'])
            if row['release_status']=='ok':require(repo is not None and name.lower()==repo['full_name'].lower(), 'release_repository_identity_mismatch')
            decoded = github_url(release['url'], name, True)
            require(decoded[len('/'+name+'/releases/tag/'):] == tag, "release_tag_mismatch")
            timestamp(release['published_at']);require(timestamp(release['checked_at']) <= attempt, "future_observation")
            require(source_at is None or source_at <= timestamp(release['checked_at']), 'source_check_newer_than_evidence')
            resolution(row['release_resolution'], requested, name, release['checked_at'])
        else:
            require(row['release_status'] != 'ok' and row['release_resolution'] is None)
        if row['status'] == 'current':
            require(repo is not None and row['repository_status'] == 'ok' and row['release_status'] in {'ok','none'}
                    and row['error_code'] is None and source_at is not None and generated < expiry)
        if row['status'] == 'unknown':
            require(repo is None and release is None and source_at is None)
        if previous is not None and ident in previous['records']:
            old = previous['records'][ident]
            for key in ['last_attempt_at','source_checked_at']:
                if old[key] is not None and row[key] is not None:
                    require(timestamp(row[key]) >= timestamp(old[key]), "observation_time_regressed")
            for key in ['repository','latest_release']:
                if old[key] is not None:
                    if row[key] is None:
                        require(key == 'latest_release' and row['release_status'] == 'none'
                                and source_at is not None and source_at >= timestamp(old[key]['checked_at']), "successful_evidence_lost")
                    else:
                        require(timestamp(row[key]['checked_at']) >= timestamp(old[key]['checked_at']), "observation_time_regressed")
    require(data['counts'] == counts and type(data['repository_count']) is int and data['repository_count'] == len(repositories), "snapshot_counts_mismatch")
    if with_availability:require(data['availability_counts'] == availability_counts, 'availability_counts_mismatch')
    if previous is not None:
        require(generated >= timestamp(previous['generated_at']) and source_run >= timestamp(previous['source_run_at']), "snapshot_time_regressed")
    return data


def previous_library(data):
    """Validate retained snapshot against its own historical identity evidence.

    The former library bytes may no longer exist after an authorized deployment.
    Old evidence is retained as a monotonic time floor, never treated as proof of
    the new library hash. The incoming snapshot must still bind the current bytes.
    """
    require(isinstance(data,dict) and isinstance(data.get('records'),dict) and 0<len(data['records'])<=2000)
    result=[]
    for ident,row in data['records'].items():
        require(isinstance(row,dict))
        requested=row.get('requested_repository')
        item={'id':ident,'verification':{'checked_at':row.get('knowledge_checked_at')}}
        if requested is not None:item['repository']='https://github.com/'+slug(requested)
        result.append(item)
    return result


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_snapshot(*, opener=None, monotonic=time.monotonic):
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    request = urllib.request.Request(SOURCE_URL, headers={'Accept':'application/json','Accept-Encoding':'identity','User-Agent':'Fanqiang-Freshness-Sync/1'})
    deadline = monotonic() + REQUEST_TIMEOUT
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            require(response.status == 200 and response.geturl() == SOURCE_URL, 'unexpected_source_response')
            require(response.headers.get('Content-Encoding', 'identity') in ('identity',''), 'compressed_response_blocked')
            length = response.headers.get('Content-Length')
            if length is not None:
                require(length.isdigit() and int(length) <= MAX_BYTES, 'response_too_large')
            reader = getattr(response, 'read1', response.read);chunks=[];total=0
            while True:
                require(monotonic() < deadline, 'request_timeout')
                chunk=reader(min(65536,MAX_BYTES+1-total))
                if not chunk:break
                chunks.append(chunk);total+=len(chunk)
                require(total<=MAX_BYTES,'response_too_large')
            return b''.join(chunks)
    except urllib.error.HTTPError as error:
        raise SyncError('source_http_'+str(error.code)) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise SyncError('source_unavailable') from None


def read_bounded(path, limit):
    require(not path.is_symlink(), 'input_symlink_blocked')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'input_too_large')
    return raw


def read_json(path,limit):
    return json.loads(read_bounded(path,limit).decode('utf-8-sig'))


def atomic_write(path, raw):
    require(not path.is_symlink(), 'output_symlink_blocked')
    descriptor,temporary=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o644);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def sync(library_path, output_path, *, opener=None, now=None, monotonic=time.monotonic):
    library_path,output_path=Path(library_path),Path(output_path)
    require(library_path.resolve()!=output_path.resolve(),'output_overlaps_library')
    now=now or datetime.now(timezone.utc)
    library_raw=read_bounded(library_path,MAX_LIBRARY_BYTES);library=json.loads(library_raw.decode('utf-8-sig'))
    library_hash=hashlib.sha256(library_raw).hexdigest()
    previous=read_json(output_path,MAX_BYTES) if output_path.exists() else None
    if previous is not None:validate_snapshot(previous,previous_library(previous),now=now)
    raw=fetch_snapshot(opener=opener,monotonic=monotonic)
    data=json.loads(raw.decode('utf-8'))
    validate_snapshot(data,library,now=now,previous=previous,library_sha256=library_hash)
    if output_path.exists() and output_path.read_bytes()==raw:
        return {'ok':True,'status':'unchanged','generated_at':data['generated_at'],'record_count':data['record_count']}
    atomic_write(output_path,raw)
    return {'ok':True,'status':'updated','generated_at':data['generated_at'],'record_count':data['record_count'],'sha256':hashlib.sha256(raw).hexdigest()}


def main(argv=None):
    fallback=Path(__file__).with_name('library.json')
    if not fallback.exists():fallback=Path(__file__).resolve().parents[1]/'apps/lookup/runtime/library.json'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=fallback)
    parser.add_argument('--output',type=Path,default=Path('/srv/fanqiang/state/source-freshness.json'))
    args=parser.parse_args(argv)
    def timeout_handler(*args):raise SyncError('total_timeout')
    old_handler=signal.signal(signal.SIGALRM,timeout_handler);signal.setitimer(signal.ITIMER_REAL,TOTAL_TIMEOUT)
    try:
        require(args.output.parent.is_dir(),'state_directory_missing')
        with args.output.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=sync(args.library,args.output)
        print(json.dumps(result));return 0
    except (SyncError,OSError,ValueError,TypeError,KeyError,RecursionError):
        print(json.dumps({'ok':False,'error_code':'freshness_sync_failed','previous_snapshot_preserved':True}),file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)


if __name__=='__main__':raise SystemExit(main())
