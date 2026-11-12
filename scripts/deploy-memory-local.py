"""Reversibly replace only the local chat container, preserving its env/network/data.

The previous container is kept stopped for rollback. No Compose volumes are removed.
Use --apply only after tests and builds. Never prints environment values.
"""
import argparse
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--watch', action='store_true', help='Keep the preview process attached after deployment')
args = parser.parse_args()
name = 'lifecompanion-librechat'
backup_name = 'lifecompanion-librechat-before-memory'

def docker(*args, capture=False):
    return subprocess.run(['docker', *args], check=True, text=True,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE)

old = json.loads(docker('inspect', name, capture=True).stdout)[0]
replacements = {
    '/app/packages/api/dist': root / 'products/librechat-custom/packages/api/dist',
    '/app/packages/data-provider/dist': root / 'products/librechat-custom/packages/data-provider/dist',
    '/app/client/dist': root / 'products/librechat-custom/client/dist',
}
for path in replacements.values():
    if not path.is_dir() or not any(path.iterdir()):
        raise SystemExit('BUILD_OUTPUT_MISSING')
if any(mount['Type'] != 'bind' for mount in old['Mounts']):
    raise SystemExit('UNSUPPORTED_MOUNT_TYPE')
if any('\n' in value or '\r' in value for value in old['Config']['Env']):
    raise SystemExit('MULTILINE_ENV_REQUIRES_REVIEW')
networks = list(old['NetworkSettings']['Networks'])
if len(networks) != 1:
    raise SystemExit('EXPECTED_SINGLE_EXISTING_NETWORK')
ports = old['HostConfig']['PortBindings']
if ports.get('3080/tcp') != [{'HostIp': '127.0.0.1', 'HostPort': '3080'}]:
    raise SystemExit('UNEXPECTED_CHAT_PORT_BINDING')
print(json.dumps({'container': name, 'rollback_container': backup_name,
                  'updated_mounts': list(replacements), 'database_volumes': 'preserved',
                  'apply': args.apply}, indent=2))
if not args.apply:
    raise SystemExit(0)
if subprocess.run(['docker', 'inspect', backup_name], stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL).returncode == 0:
    raise SystemExit('ROLLBACK_CONTAINER_ALREADY_EXISTS')
runtime = root / 'infra/runtime'
runtime.mkdir(parents=True, exist_ok=True)
created = False
renamed = False
with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=runtime,
                                 suffix='.env', delete=False) as env_file:
    env_path = Path(env_file.name)
    for value in old['Config']['Env']:
        if '\n' in value or '\r' in value:
            raise SystemExit('MULTILINE_ENV_REQUIRES_REVIEW')
        env_file.write(value+'\n')
try:
    command = ['create', '--name', name, '--network', networks[0],
               '--restart', 'unless-stopped', '--publish', '127.0.0.1:3080:3080',
               '--env-file', str(env_path)]
    destinations = set()
    for mount in old['Mounts']:
        destination = mount['Destination']
        source = str(replacements.get(destination, mount['Source']))
        destinations.add(destination)
        readonly = destination in replacements or not mount['RW']
        command += ['--mount', f'type=bind,src={source},dst={destination}'+(',readonly' if readonly else '')]
    for destination, source in replacements.items():
        if destination not in destinations:
            command += ['--mount', f'type=bind,src={source},dst={destination},readonly']
    command += [old['Config']['Image']]
    if old['Config'].get('Cmd'):
        command += old['Config']['Cmd']
    docker('stop', '--time', '20', name)
    docker('rename', name, backup_name)
    renamed = True
    docker(*command)
    created = True
    docker('start', name)
    for attempt in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:3080/health', timeout=2) as health:
                if health.status == 200:
                    break
        except (OSError, TimeoutError):
            pass
        if attempt == 59:
            raise RuntimeError('CHAT_HEALTH_TIMEOUT')
        time.sleep(1)
    print('LOCAL_CHAT_HEALTHY; previous container retained for rollback', flush=True)
except Exception:
    if created:
        docker('rm', '--force', name)
    if renamed:
        docker('rename', backup_name, name)
    docker('start', name)
    raise SystemExit('DEPLOYMENT_FAILED_ROLLED_BACK')
finally:
    env_path.unlink(missing_ok=True)

if args.watch:
    while True:
        time.sleep(30)
        state = json.loads(docker('inspect', name, capture=True).stdout)[0]['State']
        if not state['Running']:
            raise SystemExit('LOCAL_CHAT_STOPPED')
