#!/usr/bin/env python3
"""
Keepalived Monitor - ICMP + DNS port + Real DNS lookup (asynkron).

Usage:
  status_vrrp.py [--host=HOST ...] [--lookup=DOMAIN ...] [--interval=SEK] [--file=FILE]
  status_vrrp.py (-h | --help)

Options:
  --host=HOST     Hosts/DNS servers (repeatable)
  --lookup=DOMAIN Domains to lookup (repeatable)
  --interval=SEK  Interval in seconds [default: 3]
  --file=FILE     File with hosts (one per line)
  -h --help       Show this help
"""

import asyncio
import signal
import sys
from dns import message, rdatatype
from dns import asyncquery as aquery
from icmplib import async_ping
import docopt
from colorama import init, Fore, Style

init(autoreset=True)

stop_monitoring = False

def signal_handler(sig, frame):
    global stop_monitoring
    stop_monitoring = True
    print(f"\n{Style.RESET_ALL}Stopping...", flush=True)

signal.signal(signal.SIGINT, signal_handler)

# Begrens samtidige DNS-forespørsler (UDP og TCP) for å holde event-loopen responsiv
DNS_SEM = asyncio.Semaphore(32)

class HostStatus:
    def __init__(self, host, domains):
        self.host = host
        self.domains = domains
        self.icmp_ok = False
        self.tcp22_ok = False
        self.udp53_ok = False
        self.tcp53_ok = False
        self.rtt = 0
        self.lookup_results = {d: None for d in domains}

async def check_tcp_port(host, port, timeout=1.0):
    tcp22_ok = False
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        tcp22_ok = True
    except Exception:
        tcp22_ok = False

    return tcp22_ok
    
async def check_ports(host, timeout=1.0):
    """Asynkron sjekk av UDP/TCP port 53."""
    udp_ok = False
    tcp_ok = False

    # UDP 53: send en enkel asynkron DNS-forespørsel (bedre enn rå UDP I/O)
    try:
        q = message.make_query('www.example.com', rdatatype.A)
        async with DNS_SEM:
            # Liten ekstra margin på total timeout
            resp = await asyncio.wait_for(aquery.udp(q, host, timeout=timeout), timeout=timeout + 0.2)
        # Dersom vi fikk en respons (selv NXDOMAIN/NOERROR uten svarsektion), er UDP-stakken ok
        udp_ok = resp is not None
    except Exception:
        udp_ok = False

    # TCP 53: enkel TCP connect som er asynkron
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 53),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        tcp_ok = True
    except Exception:
        tcp_ok = False

    return udp_ok, tcp_ok

async def dns_lookup(host, domain, timeout=1.0):
    """Reell DNS-oppslag (asynkron). Prøver UDP først, faller tilbake til TCP."""
    q = message.make_query(domain, rdatatype.A)

    # Prøv UDP først
    try:
        async with DNS_SEM:
            resp = await asyncio.wait_for(aquery.udp(q, host, timeout=timeout), timeout=timeout + 0.2)
        ips = [str(rd) for rrset in resp.answer for rd in rrset]
        if ips:
            return ips
    except Exception:
        pass

    # Fallback til TCP
    try:
        async with DNS_SEM:
            resp = await asyncio.wait_for(aquery.tcp(q, host, timeout=timeout), timeout=timeout + 0.2)
        ips = [str(rd) for rrset in resp.answer for rd in rrset]
        return ips if ips else None
    except Exception:
        return None

def print_table(statuses):
    print("\033[2J\033[H", end='', flush=True)
    print("="*80)
    print(f"{'Host':<20} {'ICMP':<4} {'ssh':<3} {'53U':<3} {'53T':<3} {'RTT':<6}", end="")
    for domain in statuses[0].domains:
        print(f" | {domain:<20}", end="")
    print(" | Status")
    print("="*80)

    for status in statuses:
        line = f"{status.host:<20} | "
        line += f"{Fore.GREEN}✓{Style.RESET_ALL}   " if status.icmp_ok else f"{Fore.RED}✗{Style.RESET_ALL}   "
        line += f"{Fore.GREEN}✓{Style.RESET_ALL}   " if status.tcp22_ok else f"{Fore.RED}✗{Style.RESET_ALL}   "
        line += f"{Fore.GREEN}✓{Style.RESET_ALL}   " if status.udp53_ok else f"{Fore.RED}✗{Style.RESET_ALL}   "
        line += f"{Fore.GREEN}✓{Style.RESET_ALL}   " if status.tcp53_ok else f"{Fore.RED}✗{Style.RESET_ALL}   "
        b = f"{status.rtt:.0f}ms" if status.rtt > 0 else "-----"
        line += f"{b:<6}"

        dns_count = sum(1 for ips in status.lookup_results.values() if ips)
        for domain in status.domains:
            ips = status.lookup_results[domain]
            if ips:
                color = Fore.GREEN
                ip_str = ips[0][:17]
            else:
                color = Fore.RED
                ip_str = "----------------"
            line += f" | {color}{ip_str:<20}{Style.RESET_ALL}"

        overall = f"{Fore.GREEN}FULL OK{Style.RESET_ALL}" if status.icmp_ok and dns_count > 0 else f"{Fore.RED}DOWN{Style.RESET_ALL}"
        print(f"{line} | {overall}")
    print("="*80)

async def monitor(hosts, domains, interval):
    if not domains:
        domains = ['google.com']

    statuses = [HostStatus(h, domains) for h in hosts]

    print(f"🟢 {len(hosts)} hosts, {len(domains)} domains, {interval}s interval")

    while not stop_monitoring:
        tasks = []

        for status in statuses:
            # Litt mer robust ICMP (2 pakker og litt høyere timeout)
            icmp_task = async_ping(status.host, count=2, timeout=1.2, privileged=False)
            port_task = check_ports(status.host, timeout=1.0)
            port22_task = check_tcp_port(status.host, 22, timeout=1.0)
            tasks.extend([icmp_task, port_task, port22_task])

            for domain in status.domains:
                tasks.append(dns_lookup(status.host, domain, timeout=1.0))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_idx = 0
        for status in statuses:
            # ICMP
            icmp_result = results[result_idx]
            try:
                status.icmp_ok = getattr(icmp_result, "is_alive", False)
                status.rtt = getattr(icmp_result, "avg_rtt", 0) if status.icmp_ok else 0
            except Exception:
                status.icmp_ok = False
                status.rtt = 0
            result_idx += 1

            # Ports
            port_result = results[result_idx]
            # print(port_result)
            try:
                status.udp53_ok, status.tcp53_ok = port_result
            except Exception:
                status.udp53_ok = False
                status.tcp53_ok = False
            result_idx += 1

            # port22
            port_result = results[result_idx]
            try:
                status.tcp22_ok = port_result
            except Exception:
                status.tcp22_ok = False
            result_idx += 1


            # DNS
            for domain in status.domains:
                dns_result = results[result_idx]
                status.lookup_results[domain] = dns_result if dns_result else None
                result_idx += 1

        print_table(statuses)
        if not stop_monitoring:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

async def main(args):
    hosts = args['--host'] or []
    if args['--file']:
        try:
            with open(args['--file']) as f:
                hosts.extend(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            print(f"{Fore.RED}File not found: {args['--file']}")
            sys.exit(1)

    domains = args['--lookup'] or None

    if not hosts:
        print("No hosts!")
        sys.exit(1)

    interval = float(args['--interval'])
    await monitor(hosts, domains, interval)

if __name__ == "__main__":
    try:
        args = docopt.docopt(__doc__)
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print(f"\n{Style.RESET_ALL}Stopped.")
