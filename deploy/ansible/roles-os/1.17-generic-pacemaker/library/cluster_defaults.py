#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_defaults

short_description: sets and unsets cluster resource and operation defaults

version_added: "1.0"

description: 
    - sets or unsets cluster resource and operation defaults
    - for RHEL or SUSE operating systems 

options:
    state:
        description:
            - "present" ensures the default value is set
            - "absent" ensures a default value has not been set
        required: false
        choices: ["present", "absent"]
        default: present
        type: str
    name:
        description:
            - the name of the resource default to set or unset
        required: true
        type: str
    value:
        description:
            - the value of the resource default to set
            - not needed when unsetting (state=absent)
        required: false
        type: str
    defaults_type:
        description:
            - "rsc" specifies managing resource defaults
            - "op" specifies managing operation defaults
        required: false
        choices: ["rsc", "op"]
        default: "rsc"
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Set the default resource-stickiness to 100
  cluster_defaults:
    state: present
    name: resource-stickiness
    value: 100
    defaults_type: rsc
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, execute_command
from distutils.spawn import find_executable


def run_module():
    
    # ==== SETUP ====
    
    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        node=dict(required=False),
        name=dict(required=True),
        value=dict(required=False),
        defaults_type=dict(required=False, default="rsc", choices=["rsc", "op"])
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
        message=""
    )

    os      = get_os_name(module, result)
    state   = module.params["state"]
    name    = module.params["name"]
    value   = module.params["value"]
    dtype   = module.params["defaults_type"]


    # ==== COMMAND DICTIONARY ====

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["Suse"  ]                              = {}
    commands["RedHat"]["status"]                    = "pcs status"
    commands["Suse"  ]["status"]                    = "crm status"
    commands["RedHat"]["rsc"]                       = {}
    commands["Suse"  ]["rsc"]                       = {}
    commands["RedHat"]["op"]                        = {}
    commands["Suse"  ]["op"]                        = {}
    commands["RedHat"]["rsc"]["set"]                = f"pcs resource defaults {name}={value}"
    commands["Suse"  ]["rsc"]["set"]                = f"crm configure rsc_defaults {name}={value}"
    commands["RedHat"]["op" ]["set"]                = f"pcs resource op defaults {name}={value}"
    commands["Suse"  ]["op" ]["set"]                = f"crm configure op_defaults {name}={value}"
    commands["RedHat"]["rsc"]["unset"]              = f"pcs resource defaults {name}="
    commands["Suse"  ]["rsc"]["unset"]              = f"crm_attribute --type rsc_defaults --name {name} --delete"
    commands["RedHat"]["op" ]["unset"]              = f"pcs resource op defaults {name}="
    commands["Suse"  ]["op" ]["unset"]              = f"crm_attribute --type op_defaults --name {name} --delete"
    commands["RedHat"]["rsc"]["get"]                = "pcs resource defaults | grep %s | awk -F'[=]' '{print $2}' | tr -d '[:space:]'"  % name
    commands["Suse"  ]["rsc"]["get"]                = f"crm_attribute --type rsc_defaults --name {name} --query --quiet | tr -d '[:space:]'"
    commands["RedHat"]["op" ]["get"]                = "pcs resource op defaults | grep %s | awk -F'[=]' '{print $2}' | tr -d '[:space:]'"  % name
    commands["Suse"  ]["op" ]["get"]                = f"crm_attribute --type op_defaults --name {name} --query --quiet | tr -d '[:space:]'"
    commands["RedHat"]["rsc"]["check"]              = f"pcs resource defaults | grep {name}"
    commands["Suse"  ]["rsc"]["check"]              = f"crm_attribute --type rsc_defaults --name {name} --query"
    commands["RedHat"]["op" ]["check"]              = f"pcs resource op defaults | grep {name}"
    commands["Suse"  ]["op" ]["check"]              = f"crm_attribute --type op_defaults --name {name} --query"


    # ==== INITIAL CHECKS ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    if state == "present" and value is None:
        module.fail_json(msg="value parameter must be supplied when state is present")
    # Make sure we can communicate with the cluster
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== FUNCTIONS ====

    # Get the current value
    def get_value():
        rc, out, err = module.run_command(commands[os][dtype]["get"], use_unsafe_shell=True)
        if rc != 0:
            return None
        else:
            return out
    
    # Check if a default value has been configured
    def check_default():
        rc, out, err = module.run_command(commands[os][dtype]["check"], use_unsafe_shell=True)
        return rc == 0
    
    def set_property():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][dtype]["set"]
            execute_command(module, result, cmd, 
                            "Successfully set " + name + " to " + value, 
                            "Failed to set " + name + " to " + value)

    def unset_property():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][dtype]["unset"]
            execute_command(module, result, cmd, 
                            "Successfully unset " + name, 
                            "Failed to unset " + name)


    # ==== MAIN CODE ====

    if state == "present":
        if get_value() != value:
            set_property()
        else:
            result["message"] += "No changes needed: %s is already set to %s. " % (name, value)
    else:
        if check_default():
            unset_property()
        else:
            result["message"] += "No changes needed: %s has not been modified. " % name

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()