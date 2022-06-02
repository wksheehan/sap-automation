#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_order

short_description: manages cluster resource ordering constraints

version_added: "1.0"

description: 
    - creates, deletes, modifies cluster resource ordering constraints
    - for RHEL or SUSE operating systems 

options:
    state:
        description:
            - "present" ensures the colocation constraint exists
            - "absent" ensures the colocation contraint does not exist
        required: false
        choices: ["present", "absent"]
        default: present
        type: str
    name:
        description:
            - the id of the order constraint
        required: false
        default: "order-{first_action}-{first_resource}-{second_action}-{second_resource}-{kind}-{symmetrical}"
        type: str
    first_resource:
        description:
            - the name of the first resource in the ordering
        required: true
        type: str
    second_resource:
        description:
            - the name of the second resource in the ordering
        required: true
        type: str
    first_action:
        description:
            - the action to perform on first_resource
        required: false
        choices: ["start","promote","demote","stop"]
        default: "start"
        type: str
    second_action:
        description:
            - the action to perform on second_resource
        required: false
        choices: ["start", "stop", "promote","demote"]
        default: "start"
        type: str
    kind:
        description:
            - how to enforce the ordering constraint
        required: false
        choices: ["Optional", "Mandatory", "Serialize"]
        default: "Mandatory"
        type: str
    symmetrical:
        description:
            - if true, stops the resources in reverse order
        required: false
        choices: ["true","false"]
        default: "true"
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: "Create order constraint rsc1 then rsc2, Optional and not symmetrical"
    cluster_order:
    state: present
    first_resource: "rsc2"
    second_resource: "rsc2"
    kind: Optional
    symmetrical: "false"
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, get_os_version, execute_command
from distutils.spawn import find_executable
import xml.etree.ElementTree as ET


def run_module():
    
    # ==== SETUP ====
    
    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        name=dict(required=False),
        first_resource=dict(required=True),
        second_resource=dict(required=True),
        first_action=dict(required=False, choices=["start", "stop", "promote", "demote"], default="start"),
        second_action=dict(required=False, choices=["start", "stop", "promote", "demote"], default="start"),
        kind=dict(required=False, choices=["Optional", "Mandatory", "Serialize"], default="Mandatory"),
        symmetrical=dict(required=False, choices=["true", "false"], default="true")
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
    state               = module.params["state"]
    name                = module.params["name"]
    first_resource      = module.params["first_resource"]
    second_resource     = module.params["second_resource"]
    first_action        = module.params["first_action"]
    second_action       = module.params["second_action"]
    kind                = module.params["kind"]
    symmetrical         = module.params["symmetrical"]
    
    if os == "Suse":
        version = "all"
    if name is None:
        name = f"order-{first_action}-{first_resource}-{second_action}-{second_resource}-{kind}-{symmetrical}"


    # ==== COMMAND DICTIONARY ====

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["Suse"  ]                              = {}
    commands["RedHat"]["status"]                    = "pcs status"
    commands["Suse"  ]["status"]                    = "crm status"
    commands["RedHat"]["7"  ]                       = {}
    commands["RedHat"]["8"  ]                       = {}
    commands["Suse"  ]["all"]                       = {}
    commands["RedHat"]["7"  ]["create"]             = f"pcs constraint order {first_action} {first_resource} then {second_action} {second_resource} kind={kind} symmetrical={symmetrical} id={name}"
    commands["RedHat"]["8"  ]["create"]             = f"pcs constraint order {first_action} {first_resource} then {second_action} {second_resource} kind={kind} symmetrical={symmetrical} id={name}"
    commands["Suse"  ]["all"]["create"]             = f"crm configure order {name} {kind}: {first_resource}:{first_action} {second_resource}:{second_action} symmetrical={symmetrical}"
    commands["RedHat"]["7"  ]["delete"]             = "pcs constraint delete %s"        # % current_constraint.attrib.get("id")
    commands["RedHat"]["8"  ]["delete"]             = "pcs constraint delete %s"        # % current_constraint.attrib.get("id")
    commands["Suse"  ]["all"]["delete"]             = "crm configure delete --force %s" # % current_constraint.attrib.get("id")


    # ==== INITIAL CHECKS ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    # Make sure we can communicate with the cluster
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== FUNCTIONS ====

    # If found, returns the xml object of the existing constraint that matches the configuration, otherwise returns None
    def get_current_constraint():
        cib = ET.parse("/var/lib/pacemaker/cib/cib.xml")
        constraint_contenders = cib.getroot().findall(f".//rsc_order[@first='{first_resource}'][@then='{second_resource}']")
         
        if constraint_contenders is None or len(constraint_contenders) == 0:
            return None

        for constraint in constraint_contenders:
            if (constraint.attrib.get("first-action", "start") == first_action and 
            constraint.attrib.get("then-action", "start") == second_action):
                return constraint
        
        return None
    
    def create_constraint():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][version]["create"]
            execute_command(module, result, cmd, 
                            f"Successfully created constraint {name}. ",  
                            f"Failed to create constraint {name}")

    def delete_constraint(current_constraint):
        result["changed"] = True
        if not module.check_mode:
            constraint_id = current_constraint.attrib.get("id")
            cmd = commands[os][version]["delete"] % constraint_id
            execute_command(module, result, cmd, 
                            f"Successfully deleted constraint {constraint_id}. ",
                            f"Failed to delete constraint {constraint_id}")
    
    def update_constraint(current_constraint):
        if (current_constraint.attrib.get("kind", "Mandatory") != kind or
        current_constraint.attrib.get("symmetrical", "true") != symmetrical):
            result["changed"] = True
            if not module.check_mode:
                delete_constraint(current_constraint)
                create_constraint()
        else:
            result["message"] += "No updates necessary: constraint already configured as desired. "


    # ==== MAIN CODE ====

    current_constraint = get_current_constraint()

    if state == "present":
        if current_constraint != None:
            update_constraint(current_constraint)
        else:
            create_constraint()
    else:
        if current_constraint != None:
            delete_constraint(current_constraint)
        else:
            result["message"] += "No changes needed: constraint does not exist. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()