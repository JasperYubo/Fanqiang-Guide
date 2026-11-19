"""Embed reviewed assistant source into the single-file public installer."""
from pathlib import Path
import argparse
import re
ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = {'AGENTEOF':'apps/server/assistant/AGENT.md',
            'SOULEOF':'apps/server/assistant/SOUL.md',
            'SKILLEOF':'apps/server/assistant/skills/huarun/SKILL.md',
            'GATEEOF':'apps/server/assistant/hook.py',
            'RESEARCHEOF':'apps/server/research.py',
            'AUTOUPDATEEOF':'apps/server/auto_update.py',
            'AWSPROVIDEREOF':'apps/server/aws_provider.py',
            'NETWORKEOF':'apps/server/network.py',
            'PROVIDEREOF':'apps/server/ip_provider.py',
            'EGRESSEOF':'apps/server/egress.py',
            'NETWORKSETUPEOF':'apps/server/network_setup.py',
            'DISCOVERYEOF':'apps/server/provider_discovery.py',
            'GENERICEOF':'apps/server/generic_provider.py'}

def render(source):
    for delimiter, relative in PAYLOADS.items():
        payload = (ROOT / relative).read_text().rstrip('\n') + '\n'
        pattern = r"(<<\s*'" + delimiter + r"'[ \t]*(?:\|\|[ \t]*return[ \t]+1)?[ \t]*\n).*?^" + delimiter + r"\s*$"
        source, count = re.subn(pattern, lambda m: m.group(1) + payload + delimiter, source, flags=re.M | re.S)
        if count != 1:
            raise ValueError('Expected exactly one payload for ' + delimiter)
    return source

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args()
    installer=ROOT/'apps/server/install.sh';old=installer.read_text();new=render(old)
    if args.write:installer.write_text(new)
    elif old!=new:raise SystemExit('Assistant installer payload drift; run sync_server_assistant.py --write')
    print('Assistant source and installer payloads match.')
if __name__=='__main__':main()
