#!/usr/bin/python
from six import *
import optparse
import re
from pynuoadmin import nuodb_mgmt
import subprocess
import socket
import sys, time
import traceback
from datetime import datetime
import importlib
import os
import fileinput

def get_admin_conn(pid):
    """ searches for NUOCMD_ variables in nuoadmin or nuodocker then overrides whatever is set from
        command line or environment.  If unable to read environment from nuoadmin or nuodocker then
        defaults to settings passed in or environment variables."""
    admin_conn = None
    try:
        env = {}
        ROOT = ""
        try:
            # starting with 4.1 you can no longer getenv from nuodb process.  So look at parent
            # process. docker.py
            ppid = None
            with open('/proc/%s/status' % (pid,) , 'r') as e:
                for l in e:
                    k,v = l[:-1].split(":\t")
                    if k == "PPid":
                        ppid = v
                        break
            if ppid is None:
                raise "Unable to determine ppid for %s" % (pid)
            with open('/proc/%s/environ' % (ppid,) ,'r') as e:
                x = e.read()
                env = dict([ tuple(y.split('=',1)) for y in x.split('\0') if '=' in y and y.startswith('NUOCMD_')])
            ROOT = '/proc/%s/root' % (pid,)
        except IOError:
            pass
        
        api_server = env.get('NUOCMD_API_SERVER' , os.environ.get('NUOCMD_API_SERVER'))
        if api_server is None:
            # look in /etc/nuodb/nuoadmin.conf to see if ssl is enabled.
            pass

        match = re.match('(https?://|)([^:]+)(:[0-9]+|)', api_server)
        if match:
            protocol = match.group(1)
            if len(protocol) == 0:
                protocol = 'https://'
            adminhost = match.group(2)
            port = match.group(3)
            if len(port) == 0:
                port = ':8888'
            api_server = protocol + adminhost + port

        if protocol == 'https://':
            client_key = env.get('NUOCMD_CLIENT_KEY', os.environ.get('NUOCMD_CLIENT_KEY'))
            if client_key:
                client_key = ROOT + client_key

            # this assumes set to a path. It could be set to True in which case we need
            # to return the default path

            server_cert = env.get('NUOCMD_VERIFY_SERVER',os.environ.get('NUOCMD_VERIFY_SERVER',False))
            if server_cert and server_cert != True:
                server_cert = ROOT + server_cert
        else:
            client_key = None
            server_cert = None

        nuodb_mgmt.disable_ssl_warnings()
        admin_conn = nuodb_mgmt.AdminConnection(api_server, client_key=client_key,verify=server_cert)
    except Exception as x:
        print_("Exception: %s" % x,file=sys.stderr)
    finally:
        return admin_conn
    

parser = optparse.OptionParser(usage="%prog [options] module [-- <module args>]")
parser.add_option('-k',
                  '--client-key',
                  dest='client_key',
                  default=os.getenv('NUOCMD_CLIENT_KEY','/etc/nuodb/keys/nuocmd.pem'),
                  help='PEM file containing client key to verify with admin')
parser.add_option('-a',
                  '--api-server',
                  dest='api_server',
                  default=os.getenv('NUOCMD_API_SERVER','https://localhost:8888'),
                  help='ADMIN url defaults to $NUOCMD_API_SERVER if set')
parser.add_option('-v',
                  '--verify-server',
                  dest='verify_server',
                  default=os.getenv('NUOCMD_VERIFY_SERVER','/etc/nuodb/keys/ca.cert'),
                  help='trusted certificate used to verify the server when using HTTPS.')
parser.add_option('-n',
                  '--hostname',
                  dest='hostname',
                  default=socket.gethostname(),
                  help='name of this host, as known by admin layer.')
parser.add_option('-i',
                  '--interval',
                  dest='interval',
                  default=10,
                  type=int,
                  help='interval in seconds between measurements.')
(options, module_args) = parser.parse_args()

os.environ['NUOCMD_CLIENT_KEY'] = options.client_key
os.environ['NUOCMD_API_SERVER'] = options.api_server
os.environ['NUOCMD_VERIFY_SERVER'] = options.verify_server

if len(module_args) == 0:
    parser.print_help(sys.stderr)
    sys.exit(1)

module = module_args.pop(0)
m = importlib.import_module(module)
Monitor = m.Monitor

nuodb_mgmt.disable_ssl_warnings()

running_local_processes = {}
while True:
    pids = None
    latency=datetime.now()
    try:
        # only interested in nuodb process on localhost, and don't
        # want to make nuoadmin rest call unless a new process is discovered.
        _processes = subprocess.check_output(["pidof", "nuodb" ])
        pids = _processes[:-1].split()

        # check if found processes are already known or new
        for pid in pids:
            if pid not in running_local_processes:
                filter_by = dict(hostname=options.hostname,pid=str(pid))
                conn = get_admin_conn(pid)
                ps = conn.get_processes(**filter_by)
                if ps:
                    local_process = ps[0]
                    running_local_processes[pid] = Monitor(local_process,conn, True, module_args)


        # check if any known processes are no longer available
        for key in list(running_local_processes):
            if key not in pids:
                del running_local_processes[key]

        # for each nuodb process, execute query
        for key,monitor in list(running_local_processes.items()):
            try:
                sys.stdout.flush()
                monitor.execute_query()
            except KeyboardInterrupt:
                raise
            except:
                del running_local_processes[key]
    except subprocess.CalledProcessError:
        print_('nuodb not running',file=sys.stderr)
        pass
    except KeyboardInterrupt:
        for key in list(running_local_processes):
            del running_local_processes[key]
        raise
    except:
        print_('unknown exception',file=sys.stderr)
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        _sleep = options.interval-(datetime.now()-latency).total_seconds()
        try:
            # this might not work in Python3 but, does then most of this
            # code does not work in Python3
            if sys.exc_info()[0] == KeyboardInterrupt:
                raise KeyboardInterrupt

            if _sleep > 0:
                time.sleep(_sleep)
            else:
                if len(running_local_processes) == 0:
                    time.sleep(10.0)
        except KeyboardInterrupt:
            for key in list(running_local_processes):
                del running_local_processes[key]
            sys.exit(1)
