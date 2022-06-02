#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_clone

short_description: configures a clone of an existing cluster resource

version_added: "1.0"

description: 
    - configures a resource clone or
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
    clone_name:
        description:
            - the name of the cloned resource
        required: false
        default: {resource_name}-clone
        type: str
    resource_name:
        description:
            - the name of the resource to be cloned
        required: true
        type: str
    clone_type:
        description
            - specify "clone" or leave blank for a normal cloned resource
            - specify "promotable" promotable to configure a promotable (master / slave) clone
        required: false
        default: "clone"
        type: str
    options:
        description:
            - the clone options
        required: false
        type: str
author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Clone an SAPHana resource
  cluster_clone:
    state: present
    name: cln_rsc_SAPHana
    resource_name: rsc_SAPHana
    options: clone-node-max="1" target-role="Started" interleave="true"
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
        clone_name=dict(required=False),
        resource_name=dict(required=True),
        clone_type=dict(required=False, default="clone", choices=["clone", "promotable"]),
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
    clone_name          = module.params["clone_name"]
    resource_name       = module.params["resource_name"]
    clone_type          = module.params["clone_type"]
    options             = module.params["options"]

    curr_cib_path       = "/var/lib/pacemaker/cib/cib.xml"
    new_cib_name        = "shadow-cib" + str(uuid.uuid4())
    suse_promotable     = "promotable=true" if clone_type == "promotable" else ""

    if clone_name is None:
        clone_name = resource_name + "-clone"


    # ==== Command dictionary ====

    commands                                        = {}
    commands["RedHat"]                              = {}
    commands["Suse"  ]                              = {}
    commands["RedHat"]["status"]                    = "pcs status"
    commands["Suse"  ]["status"]                    = "crm status"
    commands["RedHat"]["cib"]                       = {}
    commands["Suse"  ]["cib"]                       = {}
    commands["RedHat"]["cib"]["create"]             = f"pcs cluster cib {new_cib_name}"
    commands["Suse"  ]["cib"]["create"]             = f"crm cib new {new_cib_name}"
    commands["RedHat"]["cib"]["push"]               = f"pcs cluster cib-push --config {new_cib_name}"
    commands["Suse"  ]["cib"]["push"]               = f"crm cib commit {new_cib_name}"
    commands["RedHat"]["cib"]["delete"]             = f"rm -f {new_cib_name}"
    commands["Suse"  ]["cib"]["delete"]             = f"crm cib delete {new_cib_name}"
    commands["RedHat"]["resource"]                  = {}
    commands["Suse"  ]["resource"]                  = {}
    commands["RedHat"]["resource"]["read"]          = f"pcs resource config {resource_name}"
    commands["Suse"  ]["resource"]["read"]          = f"crm config show {resource_name}" 
    commands["RedHat"]["clone"]                     = {}
    commands["Suse"  ]["clone"]                     = {}
    commands["RedHat"]["clone"]["read"]             = f"pcs resource config {clone_name}"
    commands["Suse"  ]["clone"]["read"]             = f"crm config show {clone_name}"
    commands["RedHat"]["clone"]["create"]           = f"pcs resource {clone_type} {resource_name} {options}"
    commands["Suse"  ]["clone"]["create"]           = f"crm configure clone {clone_name} {resource_name} meta {suse_promotable} {options}"
    commands["RedHat"]["clone"]["delete"]           = f"pcs resource unclone {resource_name}"
    commands["Suse"  ]["clone"]["delete"]           = f"crm configure delete --force {clone_name}"
    commands["RedHat"]["clone"]["shadow_create"]    = f"pcs -f {new_cib_name} resource {clone_type} {resource_name} {options}"
    commands["Suse"  ]["clone"]["shadow_create"]    = f"crm -F -c {new_cib_name} configure clone {clone_name} {resource_name} meta {suse_promotable} {options}"
    commands["RedHat"]["clone"]["shadow_delete"]    = f"pcs -f {new_cib_name} resource unclone {resource_name}"
    commands["Suse"  ]["clone"]["shadow_delete"]    = f"crm -F -c {new_cib_name} configure delete --force {clone_name}"
    

    # ==== Initial checks ====

    if os == "RedHat" and find_executable("pcs") is None:
        module.fail_json(msg="'pcs' executable not found. Install 'pcs'.")
    rc, out, err = module.run_command(commands[os]["status"])
    if rc != 0:
        module.fail_json(msg="Cluster is not running on current node!", **result)


    # ==== Functions ====

    # Returns true if a clone with the given name exists
    def clone_exists():
        rc, out, err = module.run_command(commands[os]["clone"]["read"])
        return rc == 0

    # Creates a new clone of a resource with the specified options
    def clone_resource():
        # Check that underlying resource exists
        cmd = commands[os]["resource"]["read"]
        execute_command(module, result, cmd,
                        "",
                        "Underlying resource to be cloned was not found")
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["clone"]["create"]
            execute_command(module, result, cmd, 
                            "Successfully cloned the resource. ", 
                            "Failed to clone the resource")
    
    # Unclones a cloned resource (does not delete the underlying resource)
    def unclone_resource():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os]["clone"]["delete"]
            execute_command(module, result, cmd, 
                            "Resource successfully uncloned. ", 
                            "Failed to unclone the resource")

    # Updates an existing clone to match the configuration specified exactly
    def update_clone():
        # Make sure current cib exists
        if not OS.path.isfile(curr_cib_path):
            module.fail_json(msg="Unable to find CIB file for existing resource", **result)

        # Initialize a shadow cib file
        cmd = commands[os]["cib"]["create"]
        execute_command(module, result, cmd,
                        "",
                        "Error creating temporary (shadow) cib file before updating clone")
        
        # Remove the existing clone using shadow cib
        cmd = commands[os]["clone"]["shadow_delete"]
        execute_command(module, result, cmd,
                        "",
                        "Error deleting existing clone using the temporary (shadow) cib file")

        # Create the desired resource using shadow cib
        cmd = commands[os]["clone"]["shadow_create"]
        execute_command(module, result, cmd,
                        "",
                        "Error updating the clone using the temporary (shadow) cib file")
        
        new_cib_path = f"/var/lib/pacemaker/cib/shadow.{new_cib_name}" if os == "Suse" else f"./{new_cib_name}"

        # Get the current and new resource XML objects
        curr_cib        = ET.parse(curr_cib_path)
        new_cib         = ET.parse(new_cib_path)
        curr_clone      = curr_cib.getroot().find(f".//clone[@id='{clone_name}']")
        new_clone       = new_cib.getroot().find(f".//clone[@id='{clone_name}']")

        is_different    = compare_clones(curr_clone, new_clone)

        if is_different:
            result["changed"] = True
            if not module.check_mode:
                # Update the live cluster with the shadow cib
                cmd = commands[os]["cib"]["push"]
                rc, out, err = module.run_command(cmd)
                if rc == 0:
                    result["message"] += "Successfully updated the clone. "
                else:
                    result["changed"] = False
                    result["stdout"] = out
                    result["error_message"] = err
                    result["command_used"] = cmd
                    # Delete shadow configuration
                    module.run_command(commands[os]["cib"]["delete"])
                    module.fail_json(msg="Failed to update the clone", **result)
        # No differences
        else:
            result["message"] += "No updates necessary: clone already configured as desired. "
        
        # Delete shadow configuration
        rc, out, err = module.run_command(commands[os]["cib"]["delete"])
    
    # Compare two primitive object xmls for differences
    # Returns 1 (True) if there is a difference, 0 (False) if not
    def compare_clones(resource1, resource2):
        # Write the clone xml to a file
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
        if clone_exists():
            update_clone()
        else:
            clone_resource()
    else:
        if clone_exists():
            unclone_resource()
        else:
            result["message"] += f"No changes needed: clone {clone_name} does not exist. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()