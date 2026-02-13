#!/usr/bin/env python3
import socket
import threading
import csv
import os
import sys
import ipaddress
from datetime import datetime

# Konfigurasjon
PORT = 9000  # Endre til ønsket port
CSV_FILE = 'server_status.csv'

def init_csv():
    """Opprett CSV-fil med header hvis den ikke finnes"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['servernavn', 'default', 'ipv4', 'ipv6', 
                           'default-ip', 'ipv4-ip', 'ipv6-ip', 'sist_oppdater'])

def clean_client_ip(client_ip):
    """Fjern ::ffff: prefix fra IPv4-mapped addresses og returner ren IP"""
    try:
        # Parse IP-adressen med ipaddress modulen
        ip = ipaddress.ip_address(client_ip)
        return str(ip)  # Returnerer ren IPv4 eller IPv6
    except:
        # Fallback til original IP hvis parsing feiler
        return client_ip

def get_ip_version(client_ip):
    """Bestem om IP er IPv4 eller IPv6 (håndterer ::ffff: prefix)"""
    clean_ip = clean_client_ip(client_ip)
    try:
        ipaddress.ip_address(clean_ip)
        # Sjekk om det er IPv6 (ikke-mapped)
        return ':' in clean_ip and not clean_ip.startswith('::ffff:')
    except:
        return False  # IPv4 eller ugyldig

def update_status(server, test_type, client_ip, is_ipv6):
    """Oppdater status i CSV-fil"""
    clean_ip = clean_client_ip(client_ip)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)
    
    # Finn eller legg til server
    found = False
    for row in rows:
        if row['servernavn'] == server:
            # Oppdater status
            row[test_type] = 'YES'
            row[f'{test_type}-ip'] = clean_ip
            row['sist_oppdater'] = now
            
            # Hvis default, sett default-ip også
            if test_type == 'default':
                row['default-ip'] = clean_ip
                
            found = True
            break
    
    if not found:
        new_row = {
            'servernavn': server,
            'default': 'NO',
            'ipv4': 'NO', 
            'ipv6': 'NO',
            'default-ip': '',
            'ipv4-ip': '',
            'ipv6-ip': '',
            'sist_oppdater': now
        }
        # Sett status og IP for riktig type
        new_row[test_type] = 'YES'
        new_row[f'{test_type}-ip'] = clean_ip
        
        if test_type == 'default':
            new_row['default-ip'] = clean_ip
            
        rows.append(new_row)
    
    # Skriv tilbake til fil
    with open(CSV_FILE, 'w', newline='') as f:
        fieldnames = ['servernavn', 'default', 'ipv4', 'ipv6', 
                     'default-ip', 'ipv4-ip', 'ipv6-ip', 'sist_oppdater']
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

def handle_client(client_socket, address):
    """Håndter en enkelt klientkobling"""
    client_ip = address[0]
    clean_ip = clean_client_ip(client_ip)
    is_ipv6_client = get_ip_version(client_ip)
    
    try:
        # Motta data (kun servernavn, eller med flagg)
        data = client_socket.recv(1024).decode('utf-8').strip()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Mottok fra {address} (ren IP: {clean_ip}): '{data}'")
        
        if not data:
            return
        
        parts = data.split()
        if len(parts) < 1:
            print("Ugyldig dataformat - tom melding")
            return
        
        server = parts[0]
        flags = parts[1:] if len(parts) > 1 else []
        
        # Bestem test_type basert på flagg
        if '-4' in flags:
            test_type = 'ipv4'
        elif '-6' in flags:
            test_type = 'ipv6'
        else:
            test_type = 'default'
        
        # Oppdater status med IP-info
        update_status(server, test_type, client_ip, is_ipv6_client)
        ip_type = "IPv6" if is_ipv6_client else "IPv4"
        print(f"Oppdatert {server} - {test_type}: YES fra {clean_ip} ({ip_type})")
        
    except Exception as e:
        print(f"Feil ved håndtering av klient {address}: {e}")
    finally:
        client_socket.close()

def main():
    init_csv()
    print(f"Starter server på port {PORT}...")
    print(f"Status lagres i {CSV_FILE}")
    print("Trykk Ctrl+C for å stoppe\n")
    
    # Lag socket som støtter både IPv4 og IPv6
    server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)  # Dual stack
    
    try:
        server_socket.bind(('::', PORT))
        server_socket.listen(10)
        print(f"[+] Lytter på [::]:{PORT} (IPv4/IPv6 dual stack)")
        print("[+] Håndterer ::ffff:IPv4 mapped addresses automatisk\n")
        
        while True:
            client_socket, address = server_socket.accept()
            print(f"[+] Ny kobling fra {address}")
            
            # Start tråd for klient
            client_thread = threading.Thread(
                target=handle_client, 
                args=(client_socket, address)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except KeyboardInterrupt:
        print("\n[-] Avslutter...")
    except Exception as e:
        print(f"Feil: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()
