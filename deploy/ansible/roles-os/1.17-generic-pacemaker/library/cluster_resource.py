#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_resource

short_description: configures a cluster resource

version_added: "1.0"

description: 
    - creates, modifies, or deletes a cluster resource
    - for RHEL or SUSE operating systems 

options:
    state:
        description:
            - "present" ensures the resource is exists
            - "absent" ensures the resource doesn't exist
        required: false
        choices: ["present", "absent"]
        default: present
        type: str
    name:
        description:
            - the name of the cluster resource
            - module will override any existing resource with this name, unless:
                - existing resource is type stonith, and you are configuring a primitive (failure)
                - existing resource is type primitive, and you are configuring a stonith (failure)
        required: true
        type: str
    resource_class:
        description:
            - the class of resource to configure
        required: false
        choices: ["stonith", "ocf",...]
        type: str
    resource_provider:
        description:
            - the provider of resource to configure
        required: false
        choices: ["heartbeat",...]
        type: str
    resource_type:
        description:
            - the type of resource to configure (the resource agent)
        required: false
        choices: ["azure-events", "fence_azure_arm", "IPaddr2",...]
        type: str
    options:
        description:
            - the instance attributes, operations, and meta attributes for the resource
            - specify the exact list you wish to be present
            - the module will add or remove any extraneous parameters necessary
        required: false
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Create a stonith resource
  cluster_resource:
    state: present
    name: my_stonith_resource
    resource-type: stonith
    options: op monitor interval=3600s
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, execute_command
from distutils.spawn import find_executable
import xml.etree.ElementTree as ET
import uuid
import os as OS
import tempfile


def run_module():
    
    # ==== Setup ====
    
    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        name=dict(required=True),
        resource_class=dict(required=False),
        resource_provider=dict(required=False),
        resource_type=dict(required=False),
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
    resource_class      = module.params["resource_class"]
    resource_provider   = module.params["resource_provider"]
    resource_type       = module.params["resource_type"]
    options             = module.params["options"]

    # Formats the class:provider:type parameter for cluster creation
    def format_class_provider_type():
        class_provider_type = ""
        if resource_class is not None:
            class_provider_type += resource_class + ":" 
        if resource_provider is not None:
            class_provider_type += resource_provider + ":" 
        if resource_type is not None:
            class_provider_type += resource_type + ":"
        if resource_class or resource_provider or resource_type:
            class_provider_type = class_provider_type[:-1]
        if resource_class == "stonith" and os == "RedHat":
            class_provider_type = resource_type
        return class_provider_type

    class_provider_type = format_class_provider_type()
    read_type           = "stonith" if resource_class == "stonith" else "resource"
    curr_cib_path       = "/var/lib/pacemaker/cib/cib.xml"
    new_cib_name        = "shadow-cib" + str(uuid.uuid4())


    # ==== Command dictionary ====

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["Suse"  ]                              = {}
    commands["RedHat"]["status"]                    = "pcs status"
    commands["Suse"  ]["status"]                    = "crm status"
    commands["RedHat"]["cib"]                       = {}
    commands["Suse"  ]["cib"]                       = {}
    commands["RedHat"]["cib"]["push"]               = "pcs cluster cib-push --config %s" # % new_cib_name
    commands["Suse"  ]["cib"]["push"]               = "crm cib commit %s"    # % new_cib_name
    commands["RedHat"]["cib"]["delete"]             = "rm -f %s" # % new_cib_name
    commands["Suse"  ]["cib"]["delete"]             = "crm cib delete %s"    # % new_cib_name
    commands["RedHat"]["resource"]                  = {}
    commands["Suse"  ]["resource"]                  = {}
    commands["RedHat"]["resource"]["read"]          = f"pcs {read_type} config {name}"
    commands["Suse"  ]["resource"]["read"]          = f"crm config show {name}" 
    commands["RedHat"]["resource"]["create"]        = f"pcs {read_type} create {name} {class_provider_type} {options}"
    commands["Suse"  ]["resource"]["create"]        = f"crm configure primitive {name} {class_provider_type} {options}"
    commands["RedHat"]["resource"]["update"]        = f"pcs -f {new_cib_name} {read_type} create {name} {class_provider_type} {options}"
    commands["Suse"  ]["resource"]["update"]        = f"crm -F -c {new_cib_name} configure primitive {name} {class_provider_type} {options}"
    commands["RedHat"]["resource"]["delete"]        = f"pcs resource delete {name}"
    commands["Suse"  ]["resource"]["delete"]        = f"crm configure delete --force {name}"
    

    # ==== Initial checks ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    if state == "present" and resource_type is None:
        module.fail_json(msg="Must specify resource_type when state is present", **result)
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== Functions ====
    
    # Returns true if a resource with the given name exists
    def resource_exists():
        rc, out, err = module.run_command(commands[os]["resource"]["read"])
        return rc == 0

    # Creates a new resource with the specified options
    def create_resource():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["resource"]["create"]
            execute_command(module, result, cmd, 
                            "Resource successfully created. ", 
                            "Failed to create the resource")
    
    # Deletes an existing resource
    def remove_resource():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["resource"]["delete"]
            execute_command(module, result, cmd, 
                            "Resource successfully removed. ", 
                            "Failed to remove the resource")

    # Updates an existing resource to match the configuration specified exactly
    def update_resource():
        # Make sure current cib exists
        if not OS.path.isfile(curr_cib_path):
            module.fail_json(msg="Unable to find CIB file for existing resource", **result)

        if os == "Suse":
            # Need to initialize an empty shadow cib file in os == Suse case
            cmd = "crm cib new %s empty" % new_cib_name
            rc, out, err = module.run_command(cmd)
            if rc != 0:
                result["stdout"] = out
                result["error_message"] = err
                result["command_used"] = cmd
                module.fail_json(msg="Error creating shadow cib file before updating resource", **result)
        
        # Create the desired resource, without affecting the current cluster, by using temporary (shadow) cib file
        cmd = commands[os]["resource"]["update"]
        rc, out, err = module.run_command(cmd) 
        if rc != 0:
            result["stdout"] = out
            result["error_message"] = err
            result["command_used"] = cmd
            module.fail_json(msg="Error creating resource using the temporary (shadow) cib file", **result)
        
        new_cib_path = f"/var/lib/pacemaker/cib/shadow.{new_cib_name}" if os == "Suse" else f"./{new_cib_name}"

        # Get the current and new resource XML objects
        curr_cib        = ET.parse(curr_cib_path)
        new_cib         = ET.parse(new_cib_path)
        curr_resource   = curr_cib.getroot().find(f".//primitive[@id='{name}']")
        new_resource    = new_cib.getroot().find(f".//primitive[@id='{name}']")

        is_different    = compare_resources(curr_resource, new_resource)

        if is_different:
            result["changed"] = True
            if not module.check_mode:
                # Update the current resource to match the desired resource
                curr_resource.clear()
                curr_resource.text = new_resource.text
                curr_resource.tail = new_resource.tail
                curr_resource.tag = new_resource.tag
                curr_resource.attrib = new_resource.attrib
                curr_resource[:] = new_resource[:]
                
                # Write the new XML to shadow cib / temporary cib file
                updated_xml = ET.ElementTree(curr_cib.getroot()) # Get the updated xml
                updated_xml.write(new_cib_path)  # Write the xml to the temporary (shadow) cib

                # Update the live cluster
                cmd = commands[os]["cib"]["push"] % new_cib_name
                rc, out, err = module.run_command(cmd)
                if rc == 0:
                    result["message"] += "Successfully updated the resource. "
                else:
                    result["changed"] = False
                    result["stdout"] = out
                    result["error_message"] = err
                    result["command_used"] = cmd
                    # Delete shadow configuration
                    module.run_command(commands[os]["cib"]["delete"] % new_cib_name)
                    module.fail_json(msg="Failed to update the resource", **result)
        # No differences
        else:
            result["message"] += "No updates necessary: resource already configured as desired. "
        
        # Delete shadow configuration
        rc, out, err = module.run_command(commands[os]["cib"]["delete"] % new_cib_name)
    
    # Compare two primitive object xmls for differences
    # Returns 1 (True) if there is a difference, 0 (False) if not
    def compare_resources(resource1, resource2):
        # Write the resource xml to a file
        r1_file_fd, r1_file_path = tempfile.mkstemp()
        r2_file_fd, r2_file_path = tempfile.mkstemp()
        r1_file = open(r1_file_path, 'w')
        r2_file = open(r2_file_path, 'w')
        r1_file.write(ET.tostring(resource1, "unicode"))
        r2_file.write(ET.tostring(resource2, "unicode"))
        r1_file.close()
        r2_file.close()
        
        # Compare difference
        rc, diff, err = module.run_command(f"diff -w {r1_file_path} {r2_file_path}")

        # Delete temporary files
        module.run_command(f"rm -f {r1_file_path} {r2_file_path}")

        return rc


    # ==== Main code ====

    if state == "present":
        if resource_exists():
            update_resource()
        else:
            create_resource()
    else:
        if resource_exists():
            remove_resource()
        else:
            result["message"] += "No changes needed: resource does not exist. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()