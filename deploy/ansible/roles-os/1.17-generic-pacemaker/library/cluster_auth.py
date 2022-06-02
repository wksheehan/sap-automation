#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_auth

short_description: authenticates nodes that will constitute a cluster

version_added: "1.0"

description: authenticates the user on one or more nodes to be used in a cluster on RHEL operating system 

options:
    state:
        description:
            - "present" ensures the nodes are authenticated
            - "absent" ensures the nodes are deauthenticated
        required: false
        choices: ["present", "absent"]
        default: "present"
        type: str
    nodes:
        description:
            - the nodes to authenticate or deauthenticate
            - a string of one or more nodes separated by spaces
        required: true
        type: str
    username:
        description:
            - the username of the cluster administrator
        required: false
        default: "hacluster"
        type: str
    password:
        description:
            - the password of the cluster administrator
            - required when state is present
        required: false
        type: str

author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Authenticate user hacluster on node1 for both the nodes in a two-node cluster (node1 and node2)
  cluster_auth:
    nodes: node1 node2
    username: hacluster
    password: testpass
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, get_os_version, execute_command
from distutils.spawn import find_executable

def run_module():

    # ==== SETUP ====

    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        nodes=dict(required=True),
        username=dict(required=False, default="hacluster"),
        password=dict(required=False, no_log=True)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
        message=""
    )

    os          = get_os_name(module, result)
    version     = get_os_version(module, result)
    state       = module.params["state"]
    nodes       = module.params["nodes"]
    username    = module.params["username"]
    password    = module.params["password"]


    # ==== INITIAL CHECKS ====
    
    if find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    if state == "present" and password is None:
        module.fail_json(msg="Must specify password when state is present", **result)
    

    # ==== COMMAND DICTIONARY ==== 

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["RedHat"]["status"]                    = "pcs cluster pcsd-status %s" % nodes
    commands["RedHat"]["7"]                         = {}
    commands["RedHat"]["8"]                         = {}
    commands["RedHat"]["7"]["authenticate"]         = "pcs cluster auth %s -u %s -p %s" % (nodes, username, password)
    commands["RedHat"]["8"]["authenticate"]         = "pcs host auth %s -u %s -p %s" % (nodes, username, password)
    commands["RedHat"]["7"]["deauthenticate"]       = "pcs cluster deauth %s" % nodes
    commands["RedHat"]["8"]["deauthenticate"]       = "pcs host deauth %s" % nodes
    

    # ==== MAIN CODE ====

    rc, out, err = module.run_command(commands[os]["status"])
    nodes_online = rc == 0

    if state == "present":
        if nodes_online:
            result["message"] = "Nodes %s are all authenticated" % nodes
        else:
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["authenticate"]
                execute_command(module, result, cmd, 
                            "Nodes were successfully authenticated", 
                            "Failed to authenticate one or more nodes")
    if state == "absent":
        if nodes_online:    
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["deauthenticate"]
                execute_command(module, result, cmd, 
                            "Nodes were successfully deauthenticated", 
                            "Failed to deauthenticate one or more nodes")
        else:
            result["message"] = "Nodes %s are already unauthenticated" % nodes
        

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()