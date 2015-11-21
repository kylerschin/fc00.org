#!/usr/bin/env python3
# Based on Kyrias' sendGraph script. Requires Python 3, requests and cjdns.
# You can install them using pip: pip3 install cjdns requests
###############################################################################
# CONFIG

# URL where data is sent
#    www.fc00.org              for clearnet access
#    h.fc00.org                for hyperboria
#    [fc53:dcc5:e89d:9082:4097:6622:5e82:c654] for DNS-less access
url = 'http://www.fc00.org/sendGraph'

# update your email address, so I can contact you in case something goes wrong
your_mail = 'your@email.here'


# ----------------------
# RPC connection details
# ----------------------

# If this is set to True connection details will be loaded from ~/.cjdnsadmin
cjdns_use_default = True

# otherwise these are used.
cjdns_ip     = '127.0.0.1'
cjdns_port       = 11234
cjdns_password   = 'NONE'

###############################################################################

import sys
import traceback
import json

import requests

import cjdns
from cjdns import key_utils
from cjdns import admin_tools

import queue
import threading

def main():
    con = connect()

    nodes = dump_node_store(con)
    edges = {}

    get_peer_queue = queue.Queue(0)
    result_queue = queue.Queue(0)

    for k in nodes:
        get_peer_queue.put(k)

    for i in range(8):
        t = threading.Thread(target=worker, args=[nodes, get_peer_queue, result_queue])
        t.daemon = True
        t.start()

    for i in range(len(nodes)):
        peers, node_ip = result_queue.get()
        get_edges_for_peers(edges, peers, node_ip)

    send_graph(nodes, edges)
    sys.exit(0)

def worker(nodes, get_peer_queue, result):
    con = connect()

    while True:
        try:
            k = get_peer_queue.get_nowait()
        except queue.Empty:
            return

        node = nodes[k]
        print('fetch', node)
        node_ip = node['ip']

        peers = get_peers(con, node['path'])

        result.put((peers, node_ip))

def connect():
    try:
        if cjdns_use_default:
            print('Connecting using default or ~/.cjdnsadmin credentials...')
            con = cjdns.connectWithAdminInfo()
        else:
            print('Connecting to port {:d}...'.format(cjdns_port))
            con = cjdns.connect(cjdns_ip, cjdns_port, cjdns_password)

        return con

    except:
        print('Connection failed!')
        print(traceback.format_exc())
        sys.exit(1)


def dump_node_store(con):
    nodes = dict()

    i = 0
    while True:
        res = con.NodeStore_dumpTable(i)

        if not 'routingTable' in res:
            break

        for n in res['routingTable']:
            if not all(key in n for key in ('addr', 'path', 'ip')):
                continue

            ip = n['ip']
            path = n['path']
            addr = n['addr']
            version = None
            if 'version' in n:
                version = n['version']

            nodes[ip] = {'ip': ip, 'path': path, 'addr': addr, 'version': version}

        if not 'more' in res or res['more'] != 1:
            break

        i += 1

    return nodes


def get_peers(con, path):
    peers = set()

    i = 1
    while i < 3:
        res = con.RouterModule_getPeers(path)

        if ('result' in res and res['result'] == 'timeout') or \
           ('error'  in res and res['error']  != 'none'):
            failure = ''
            if 'error' in res:
                failure = res['error']
            if 'result' in res:
                if len(failure) != 0:
                    failure += '/'
                failure += res['result']

            print('get_peers: getPeers failed with {:s} on {:s}, trying again. {:d} tries remaining.'
                  .format(failure, path, 2 - i))
            i += 1
            continue
        else:
            break

    if 'result' not in res or res['result'] != 'peers':
        print('get_peers: failed too many times, skipping.')
        print(res)
        return peers

    for peer in res['peers']:
        key = peer.split('.', 5)[-1]
        peers |= {key}

    return peers


def get_edges_for_peers(edges, peers, node_ip):
    for peer_key in peers:
        peer_ip = key_utils.to_ipv6(peer_key)

        if node_ip > peer_ip:
            A = node_ip
            B = peer_ip
        else:
            A = peer_ip
            B = node_ip

        edge = { 'a': A,
                 'b': B }

        if A not in edges:
            edges[A] = []

        if not([True for edge in edges[A] if edge['b'] == B]):
            edges[A] += [edge]


def send_graph(nodes, edges):
    graph = {
        'nodes': [],
        'edges': [edge for sublist in edges.values()
                   for edge    in sublist],
    }

    for node in nodes.values():
        graph['nodes'].append({
            'ip':      node['ip'],
            'version': node['version'],
        })

    print('Nodes: {:d}\nEdges: {:d}\n'.format(len(nodes), len(edges)))

    json_graph = json.dumps(graph)
    print('Sending data to {:s}...'.format(url))

    payload = {'data': json_graph, 'mail': your_mail, 'version': 2}
    r = requests.post(url, data=payload)

    if r.text == 'OK':
        print('Done!')
    else:
        print('Error: {:s}'.format(r.text))

if __name__ == '__main__':
    main()
