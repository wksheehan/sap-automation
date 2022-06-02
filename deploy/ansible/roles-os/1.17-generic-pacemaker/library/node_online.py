#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: node_online

short_description: puts nodes on and offline (standby)

version_added: "1.0" 

options:
    online:
        description:
            - "true" ensures the node is online
            - "false" ensures the node is on standby
        required: false
        choices: ["true", "false"]
        default: true
        type: str
    node:
        description:
            - the name of the node
        required: true
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, get_os_version, execute_command
from distutils.spawn import find_executable
import xml.etree.ElementTree as ET


def run_module():
    
    # ==== SETUP ====
    
    module_args = dict(
        online=dict(required=False, default="true", choices=["true", "false"]),
        node=dict(required=True)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
        message=""
    )

    os                  = get_os_name(module, result)
    version             = get_os_version(module, result)
    online              = module.params["online"]
    node                = module.params["node"]
    if os == "Suse":
        version = "all"


    # ==== COMMAND DICTIONARY ====

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["Suse"  ]                              = {}
    commands["RedHat"]["status"]                    = "pcs status"
    commands["Suse"  ]["status"]                    = "crm status"
    commands["RedHat"]["7"  ]                       = {}
    commands["RedHat"]["8"  ]                       = {}
    commands["Suse"  ]["all"]                       = {}
    commands["RedHat"]["7"  ]["status"]             = f"pcs node attribute --name standby | grep '{node}: standby=on'"
    commands["RedHat"]["8"  ]["status"]             = f"pcs node attribute --name standby | grep '{node}: standby=on'"
    commands["Suse"  ]["all"]["status"]             = f"crm config show {node} | grep standby=on"
    commands["RedHat"]["7"  ]["online"]             = f"pcs node unstandby {node}"
    commands["RedHat"]["8"  ]["online"]             = f"pcs node unstandby {node}"
    commands["Suse"  ]["all"]["online"]             = f"crm node online {node}"
    commands["RedHat"]["7"  ]["standby"]            = f"pcs node standby {node}"
    commands["RedHat"]["8"  ]["standby"]            = f"pcs node standby {node}"
    commands["Suse"  ]["all"]["standby"]            = f"crm node standby {node}"


    # ==== INITIAL CHECKS ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    # Make sure we can communicate with the cluster
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== FUNCTIONS ====

    # Checks if a node is online or not
    def node_online():
        rc, out, err = module.run_command(commands[os][version]["status"], use_unsafe_shell=True)
        return rc != 0

    def bring_node_online():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][version]["online"]
            execute_command(module, result, cmd, 
                            f"Successfully brought node online. ",
                            f"Failed to bring node online")
    
    def put_node_on_standby():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][version]["standby"]
            execute_command(module, result, cmd, 
                            f"Successfully put node on standby. ",  
                            f"Failed to put node on standby")


    # ==== MAIN CODE ====

    if online == "true":
        if node_online():
            result["message"] += "No changes needed: node is already online. "
        else:
            bring_node_online()
    else:
        if node_online():
            put_node_on_standby()
        else:
            result["message"] += "No changes needed: node is already on standby. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()