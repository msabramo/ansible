#!/usr/bin/env python

# (c) 2012, Marco Vito Moscaritolo <marco@agavee.com>
#
# This file is part of Ansible,
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
inventory: nova
short_description: OpenStack external inventory script
description:
  - Generates inventory that Ansible can understand by making API request to OpenStack endpoint using the novaclient library.
  - |
    When run against a specific host, this script returns the following variables:
        os_os-ext-sts_task_state
        os_addresses
        os_links
        os_image
        os_os-ext-sts_vm_state
        os_flavor
        os_id
        os_rax-bandwidth_bandwidth
        os_user_id
        os_os-dcf_diskconfig
        os_accessipv4
        os_accessipv6
        os_progress
        os_os-ext-sts_power_state
        os_metadata
        os_status
        os_updated
        os_hostid
        os_name
        os_created
        os_tenant_id
        os__info
        os__loaded

    where some item can have nested structure.
  - All information are set on B(nova.ini) file
version_added: None
options:
  version:
    description:
      - OpenStack version to use.
    required: true
    default: null
    choices: [ "1.1", "2" ]
  username:
    description:
      - Username used to authenticate in OpenStack. Can use environment varaible.
    required: true
    default: null
  api_key:
    description:
      - Password used to authenticate in OpenStack, can be the ApiKey on some authentication system. Can use environment variable.
    required: true
    default: null
  auth_url:
    description:
      - Authentication URL required to generate token. Can use environment variable.
      - To manage RackSpace use I(https://identity.api.rackspacecloud.com/v2.0/)
    required: true
    default: null
  auth_system:
    description:
      - Authentication system used to login
      - To manage RackSpace install B(rackspace-novaclient) and insert I(rackspace)
    required: true
    default: null
  region_name:
    description:
      - Region name to use in request
      - In RackSpace some value can be I(ORD) or I(DWF).
    required: true
    default: null
  project_id:
    description:
      - Project ID to use in connection. Can use environment variable.
      - In RackSpace use OS_TENANT_NAME
    required: false
    default: null
  endpoint_type:
    description:
      - The endpoint type for novaclient
      - In RackSpace use 'publicUrl'
    required: false
    default: null
  service_type:
    description:
      - The service type you are managing.
      - In RackSpace use 'compute'
    required: false
    default: null
  service_name:
    description:
      - The service name you are managing.
      - In RackSpace use 'cloudServersOpenStack'
    required: false
    default: null
  insicure:
    description:
      - To no check security
    required: false
    default: false
    choices: [ "true", "false" ]
  prefer_private:
    description:
      - Flag to determine if the script should prefer to return private IPs or public IPs as the addressable hostname.
    default: false
    choices: [ "true", "false" ]
author: Marco Vito Moscaritolo
notes:
  - This script assumes Ansible is being executed where the environment variables needed for novaclient have already been set on nova.ini file
  - For more details, see U(https://github.com/openstack/python-novaclient)
examples:
    - description: List instances
      code: nova.py --list
    - description: Instance property
      code: nova.py --instance INSTANCE_IP
'''


import sys
import re
import os
import ConfigParser
from novaclient import client as nova_client

try:
    import json
except ImportError:
    import simplejson as json

###################################################
# executed with no parameters, return the list of
# all groups and hosts

NOVA_CONFIG_FILES = [os.getcwd() + "/nova.ini",
                     os.path.expanduser(os.environ.get('ANSIBLE_CONFIG', "~/nova.ini")),
                     "/etc/ansible/nova.ini"]

NOVA_DEFAULTS = {
    'auth_system': None,
    'region_name': None,
    'service_type': 'compute',
}


def nova_load_config_file():
    p = ConfigParser.SafeConfigParser(NOVA_DEFAULTS)

    for path in NOVA_CONFIG_FILES:
        if os.path.exists(path):
            p.read(path)
            return p

    return None


def get_fallback(config, value, section="openstack"):
    """
    Get value from config object and return the value
    or false
    """
    try:
        return config.get(section, value)
    except ConfigParser.NoOptionError:
        return False


def push(data, key, element):
    """
    Assist in items to a dictionary of lists
    """
    if (not element) or (not key):
        return

    if key in data:
        data[key].append(element)
    else:
        data[key] = [element]


def to_safe(word):
    '''
    Converts 'bad' characters in a string to underscores so they can
    be used as Ansible groups
    '''
    return re.sub(r"[^A-Za-z0-9\-]", "_", word)


def get_ips(server, access_ip=True):
    """
    Returns a list of the server's IPs, or the preferred
    access IP
    """
    private = []
    public = []
    address_list = []
    # Iterate through each servers network(s), get addresses and get type
    addresses = getattr(server, 'addresses', {})
    if len(addresses) > 0:
        for network in addresses.itervalues():
            for address in network:
                if address.get('OS-EXT-IPS:type', False) == 'fixed':
                    private.append(address['addr'])
                elif address.get('OS-EXT-IPS:type', False) == 'floating':
                    public.append(address['addr'])

    if not access_ip:
        address_list.append(server.accessIPv4)
        address_list.append(''.join(private))
        address_list.append(''.join(public))
        return address_list

    access_ip = None
    # Append group to list
    if server.accessIPv4:
        access_ip = server.accessIPv4
    if (not access_ip) and public and not (private and prefer_private):
        access_ip = ''.join(public)
    if private and not access_ip:
        access_ip = ''.join(private)

    return access_ip


def get_metadata(server):
    """Returns dictionary of all host metadata"""
    get_ips(server, False)
    results = {}
    for key in vars(server):
        # Extract value
        value = getattr(server, key)

        # Generate sanitized key
        key = 'os_' + re.sub(r"[^A-Za-z0-9\-]", "_", key).lower()

        # Att value to instance result (exclude manager class)
        #TODO: maybe use value.__class__ or similar inside of key_name
        if key != 'os_manager':
            results[key] = value
    return results

config = nova_load_config_file()
if not config:
    sys.exit('Unable to find configfile in %s' % ', '.join(NOVA_CONFIG_FILES))

# Load up connections info based on config and then environment
# variables
username = (get_fallback(config, 'username') or
            os.environ.get('OS_USERNAME', None))
api_key = (get_fallback(config, 'api_key') or
           os.environ.get('OS_PASSWORD', None))
auth_url = (get_fallback(config, 'auth_url') or
            os.environ.get('OS_AUTH_URL', None))
project_id = (get_fallback(config, 'project_id') or
              os.environ.get('OS_TENANT_NAME', None))

# Determine what type of IP is preferred to return
prefer_private = False
try:
    prefer_private = config.getboolean('openstack', 'prefer_private')
except ConfigParser.NoOptionError:
    pass

client = nova_client.Client(
    version=config.get('openstack', 'version'),
    username=username,
    api_key=api_key,
    auth_url=auth_url,
    region_name=config.get('openstack', 'region_name'),
    project_id=project_id,
    auth_system=config.get('openstack', 'auth_system'),
    service_type=config.get('openstack', 'service_type'),
)

# Default or added list option
if (len(sys.argv) == 2 and sys.argv[1] == '--list') or len(sys.argv) == 1:
    groups = {'_meta': {'hostvars': {}}}
    # Cycle on servers
    for server in client.servers.list():
        access_ip = get_ips(server)

        # Push to name group of 1
        push(groups, server.name, access_ip)

        # Run through each metadata item and add instance to it
        for key, value in server.metadata.iteritems():
            composed_key = to_safe('tag_{0}_{1}'.format(key, value))
            push(groups, composed_key, access_ip)

        # Do special handling of group for backwards compat
        # inventory groups
        group = server.metadata['group'] if 'group' in server.metadata else 'undefined'
        push(groups, group, access_ip)

        # Add vars to _meta key for performance optimization in
        # Ansible 1.3+
        groups['_meta']['hostvars'][access_ip] = get_metadata(server)

    # Return server list
    print(json.dumps(groups, sort_keys=True, indent=2))
    sys.exit(0)

#####################################################
# executed with a hostname as a parameter, return the
# variables for that host

elif len(sys.argv) == 3 and (sys.argv[1] == '--host'):
    results = {}
    ips = []
    for server in client.servers.list():
        if sys.argv[2] in (get_ips(server) or []):
            results = get_metadata(server)
    print(json.dumps(results, sort_keys=True, indent=2))
    sys.exit(0)

else:
    print "usage: --list  ..OR.. --host <hostname>"
    sys.exit(1)
