#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_group

short_description: manages a cluster resource group

version_added: "1.0"

description: 
    - creates, destroys, and modifies cluster resource groups
    - for RHEL or SUSE operating systems 

options:
    state:
        description:
            - "present" ensures the resource group is exists
            - "absent" ensures the resource group doesn't exist
        required: false
        choices: ["present", "absent"]
        default: present
        type: str
    name:
        description:
            - the name of the resource group
            - module will override any existing resource group with this name
        required: true
        type: str
    resources:
        description:
            - exact list of resources desired to exist in the resource group
            - string of space-separated resources
            - the resources will start in the order you specify them
            - the resources will stop in the reverse order of their starting order
            - the module will add or remove any resources necessary to achieve this desired set
        required: false
        type: str
    options:
        description:
            - the options for the resource group
            - for use with Suse operation system
        required: true
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Ensure a resource group named my_ip_addrs exists and contains resources myipaddr1 and youripaddr2
  cluster_group:
    state: present
    name: my_ip_addrs
    resources: myipaddr1 youripaddr2 
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, execute_command
from distutils.spawn import find_executable


def run_module():
    
    # ==== Setup ====
    
    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        name=dict(required=True),
        resources=dict(required=False, default=""),
        options=dict(required=False, default="")
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
    state               = module.params["state"]
    name                = module.params["name"]
    resources           = module.params["resources"]
    options             = module.params["options"]

    resource_list       = resources.split()
    resource_set        = set(resource_list)
    last_resource       = resource_list[-1] if len(resource_list) > 0 else ""


    # ==== Command dictionary ====

    commands                               = {}
    commands["RedHat"]                     = {}
    commands["Suse"  ]                     = {}
    commands["RedHat"]["status"]           = "pcs status"
    commands["Suse"  ]["status"]           = "crm status"
    commands["RedHat"]["read"]             = f"pcs resource group list | grep {name}:"
    commands["Suse"  ]["read"]             = f"crm config show type:group | grep 'group {name}'"
    commands["RedHat"]["get"]              = "pcs resource group list | grep %s: | awk -F'[:]' '{print $2}'" % name
    commands["Suse"  ]["get"]              = "crm config show | grep 'group %s' | cut -d' ' -f 3-" % name
    commands["RedHat"]["create"]           = f"pcs resource group add {name} {resources}"
    commands["Suse"  ]["create"]           = f"crm configure group {name} {resources} {options}"
    commands["RedHat"]["add"]              = "pcs resource group add %s %s"           # % (name, resources_to_add)
    commands["Suse"  ]["add"]              = "crm configure modgroup %s add '%s'"     # % (name, resources_to_add)
    commands["RedHat"]["remove"]           = f"pcs resource group remove {name} "     # + resources_to_remove
    commands["Suse"  ]["remove"]           = f"crm configure modgroup {name} remove " # + resources_to_remove
    commands["RedHat"]["delete"]           = f"pcs resource group remove {name} "     # + " ".join(get_group_resources())
    commands["Suse"  ]["delete"]           = f"crm configure delete --force {name}"
    commands["RedHat"]["sort"]             = "pcs resource group add %s %s --before %s" % (name, " ".join(resource_list[:-1]), last_resource)
    commands["Suse"  ]["sort"]             = "crm config modgroup %s add '%s' before %s"  % (name, " ".join(resource_list[:-1]), last_resource)
    

    # ==== Initial checks ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    if state == "present" and (resources is None or len(resource_set) == 0):
        module.fail_json(msg="No resources specified. If you wish to destroy the resource group, run again with state = absent", **result)
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== Functions ====
    
    # Returns True if a resource group with the given name exists
    def resource_group_exists():
        rc, out, err = module.run_command(commands[os]["read"], use_unsafe_shell=True)
        return rc == 0
    
    # Returns the list of resources already in the specified resource group
    def get_group_resources():
        cmd = commands[os]["get"]
        rc, out, err = module.run_command(cmd, use_unsafe_shell=True)
        if rc == 0:
            return out.split()
        else:
            result["changed"] = False
            result["stdout"] = out
            result["error_message"] = err
            result["command_used"] = cmd
            module.fail_json(msg="Error while retrieving resources in group " + name, **result)
    
    # Returns True if the ordering of resources is as desired, False if different
    def is_ordered():
        return resource_list == get_group_resources()

    # Creates a new resource with the specified resources and options
    def create_resource_group():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["create"]
            execute_command(module, result, cmd, 
                            "Resource group successfully created. ", 
                            "Failed to create the resource group")
    
    # Adds resources to an existing group
    def add_resources(resources):
        result["changed"] = True
        if not module.check_mode:
            resources_to_add = " ".join(resources)
            cmd = commands[os]["add"] % (name, resources_to_add)
            execute_command(module, result, cmd,
                            "Succesfully added the following resources to the group: %s. " % resources_to_add,
                            "Failed to add the following resources to the group: " + resources_to_add)
    
    # Removes resources from the resource group
    def remove_resources(resources):
        result["changed"] = True
        if not module.check_mode:
            if os == "RedHat":
                resources_to_remove = " ".join(resources)
                cmd = commands[os]["remove"] + resources_to_remove
                execute_command(module, result, cmd,
                                "Succesfully removed the following resources from the group: %s. " % resources_to_remove,
                                "Failed to remove the following resources from the group: %s" % resources_to_remove)
            # Can only remove one resource at a time when os == "Suse"
            else:
                for resource in resources:
                    cmd = commands[os]["remove"] + resource
                    execute_command(module, result, cmd,
                                    "Succesfully removed %s from the group. " % resource,
                                    "Failed to remove %s from the group: " % resource)

    # Deletes an entire resource group
    def delete_group():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["delete"]
            if os == "RedHat":
                cmd += " ".join(get_group_resources())
            execute_command(module, result, cmd,
                            "Succesfully destroyed the resource group. ",
                            "Failed to destroy the resource group")

    # Rearranges the resources in the group to match the input order specified
    def sort_group():
        result["changed"] = True
        if not module.check_mode:
            # Can't rearrange resources already in group for os == Suse
            # ==> remove them, then add them back in the correct order
            if os == "Suse":
                for resource in resource_list[:-1]:
                    cmd = commands[os]["remove"] + resource
                    execute_command(module, result, cmd,
                                    "",
                                    "Failed to remove %s from the group: " % resource)
            cmd = commands[os]["sort"]
            execute_command(module, result, cmd,
                            "Successfully reordered the list. ",
                            "Failed to reorder the list")

    # Updates an existing resource to match the configuration specified exactly
    def update_resource_group():
        existing_resouces = set(get_group_resources())
        resources_to_add = resource_set - existing_resouces
        resources_to_remove = existing_resouces - resource_set
        # Configuration is as desired
        if len(resources_to_add) == 0 and len(resources_to_remove) == 0 and is_ordered():
            result["message"] += "No changes needed: group is already set up with the resources specified. "
        # Add missing resources
        if len(resources_to_add) > 0:
            add_resources(resources_to_add)
        # Remove extra resources
        if len(resources_to_remove) > 0:
            remove_resources(resources_to_remove)
        # Reorder the resources
        if not is_ordered():
            sort_group()


    # ==== Main code ====

    if state == "present":
        if resource_group_exists():
            update_resource_group()
        else:
            create_resource_group()
    else:
        if resource_group_exists():
            delete_group()
        else:
            result["message"] += "No changes needed: resource group does not exist. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()