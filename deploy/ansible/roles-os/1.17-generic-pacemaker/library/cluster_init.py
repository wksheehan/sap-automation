#!/usr/bin/python

# Copyright: (c) 2022, William Sheehan <willksheehan@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_init

short_description: initializes, modifies, and deletes pacemaker clusters

version_added: "1.0"

description: 
    - creates or modifies a cluster so that it contains exactly the specified node set
    - starts the cluster on all nodes (RedHat)
    - fails if not all nodes specified are online after 120 seconds
    - for use with RHEL or SUSE operating systems 

options:
    state:
        description:
            - "present" will create or modify the cluster
            - "absent" will remove the entire cluster
        required: false
        choices: ["present", "absent"]
        default: "present"
        type: str
    sid:
        description:
            - the sid to be used in the naming of the cluster
        required: false
        type: str
    existing_node:
        description:
            - may be specified in the case of SUSE operating system
            - if specified, implies a cluster is already set up, but not on the current node
            - defines the name of a node already in a cluster
            - the current node that calls this module will attempt to join this existing cluster
        required: false
        type: str
    nodes:
        description:
            - the desired nodes to exist in the cluster
            - a string of node names separated by spaces
            - module will add or remove any nodes necessary in order to ensure a cluster contains exactly these nodes
        required: false
        type: str
    tier:
        description:
            - the node tier, to be used in naming the cluster (Suse)
        required: false
        type: str
    token:
        description:
            - the token used when setting up the cluster
        required: false
        type: str

author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
- name: Create a basic two node cluster for the hana node tier on RedHat 8
  cluster_init:
    state: present
    sid: SAP01
    nodes: node1 node2
    tier: hana
    token: 30000

- name: Modify the cluster to have a different node in it
  cluster_init:
    state: present
    sid: SAP01
    nodes: node1 node3
    tier: hana
    token: 30000

- name: Remove the entire cluster
  cluster_init:
    state: absent
    sid: SAP01
    tier: hana
    token: 30000
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.helper_functions import get_os_name, get_os_version, execute_command
from distutils.spawn import find_executable
from time import sleep
import re
import socket
import os as OS


def run_module():

    # ==== SETUP ==== 

    module_args = dict(
        state=dict(required=False, default="present", choices=["present", "absent"]),
        sid=dict(required=False),
        existing_node=dict(required=False),
        nodes=dict(required=False, default=""),
        tier=dict(required=False, choices=["hana", "scs", "db2"]),
        token=dict(required=False)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
        message=""
    )

    os              = get_os_name(module, result)
    version         = get_os_version(module, result)
    state           = module.params["state"]
    sid             = module.params["sid"]
    existing_node   = module.params["existing_node"]
    nodes           = module.params["nodes"]
    nodes_set       = set(nodes.split())
    tier            = module.params["tier"]
    token           = module.params["token"]
    curr_node       = socket.gethostname()
    cluster_exists  = OS.path.isfile("/etc/corosync/corosync.conf") or OS.path.isfile("/var/lib/pacemaker/cib/cib.xml")

    # Generate the desired cluster name
    if os == "Suse":
        prefix = "hdb" if tier == "hana" else tier
        desired_cluster_name = "%s_%s" % (prefix, sid)
    else:
        desired_cluster_name = "%s_cluster" % sid


    # ==== INITIAL CHECKS ====

    if os == "RedHat":
        if find_executable("pcs") is None:
            module.fail_json(msg="'pcs' executable not found. Install 'pcs'.", **result)
        if existing_node is not None and curr_node != existing_node:
            module.fail_json(msg="Must configure the cluster from the current node when using RedHat", **result)
    if os == "Suse":
        version = "all"
    if state == "present" and len(nodes_set) == 0:
        module.fail_json(msg="No nodes will be left in the cluster. If you intend to destroy the whole cluster, re-run the module with state: absent", **result)

    
    # ==== COMMAND DICTIONARY ====

    commands                                    = {}
    commands["RedHat"]                          = {}
    commands["Suse"  ]                          = {}
    commands["RedHat"]["7"  ]                   = {}
    commands["RedHat"]["8"  ]                   = {}
    commands["Suse"  ]["all"]                   = {}
    commands["RedHat"]["7"  ]["setup"]          = "pcs cluster setup --name %s %s --token %s" % (desired_cluster_name, nodes, token)
    commands["RedHat"]["8"  ]["setup"]          = "pcs cluster setup %s %s totem token=%s" % (desired_cluster_name, nodes, token)
    commands["Suse"  ]["all"]["setup"]          = "ha-cluster-init -y --name '%s' --interface eth0 --no-overwrite-sshkey --nodes '%s'" % (desired_cluster_name, nodes) # password needs to be configured and passed into command
    commands["RedHat"]["7"  ]["destroy"]        = "pcs cluster destroy --all"
    commands["RedHat"]["8"  ]["destroy"]        = "pcs cluster destroy --all"
    commands["Suse"  ]["all"]["destroy"]        = "crm cluster remove -y -c %s %s --force" # % (curr_node, " ".join(nodes_set))
    commands["RedHat"]["7"  ]["add"]            = "pcs cluster node add "
    commands["RedHat"]["8"  ]["add"]            = "pcs cluster node add "
    commands["Suse"  ]["all"]["add"]            = "crm cluster add -y "
    commands["RedHat"]["7"  ]["remove"]         = "pcs cluster node remove %s --force"
    commands["RedHat"]["8"  ]["remove"]         = "pcs cluster node remove %s --force"
    commands["Suse"  ]["all"]["remove"]         = "crm cluster remove -y %s --force" 
    commands["RedHat"]["7"  ]["start"]          = "pcs cluster start"
    commands["RedHat"]["8"  ]["start"]          = "pcs cluster start"
    commands["Suse"  ]["all"]["start"]          = "crm cluster start" 
    commands["RedHat"]["7"  ]["stop"]           = "pcs cluster stop"
    commands["RedHat"]["8"  ]["stop"]           = "pcs cluster stop"
    commands["Suse"  ]["all"]["stop"]           = "crm cluster stop" 
    commands["RedHat"]["7"  ]["status"]         = "pcs status"
    commands["RedHat"]["8"  ]["status"]         = "pcs status"
    commands["Suse"  ]["all"]["status"]         = "crm status"
    commands["RedHat"]["7"  ]["online"]         = "pcs status | grep '^Online:'"
    commands["RedHat"]["8"  ]["online"]         = "pcs status | grep '^  \* Online:'"
    commands["Suse"  ]["all"]["online"]         = "crm status | grep 'Online:'"
    commands["Suse"  ]["all"]["join"]           = "ha-cluster-join -y -c %s --interface eth0" % existing_node
    commands["RedHat"]["regex"]                 = r"ring0_addr\s*:\s*([\w.-]+)\s*"
    commands["Suse"  ]["regex"]                 = r"host\s*([\w.-]+);"
    commands["RedHat"]["file"]                  = "/etc/corosync/corosync.conf"
    commands["Suse"  ]["file"]                  = "/etc/csync2/csync2.cfg"

    
    # ==== FUNCTIONS ====

    # Ensure cluster is running on the current node
    def start_cluster():
        rc, out, err = module.run_command(commands[os][version]["status"])
        if rc != 0:
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["start"]
                execute_command(module, result, cmd,
                                "Successfully started the cluster. ",
                                "Error starting the cluster")
        
    # Start a cluster on all nodes (for RedHat)
    def start_all():
        nodes_online = get_nodes_online(5)
        # Not all nodes are currently online
        if nodes_online != nodes_set:
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["start"] + " --all"
                execute_command(module, result, cmd, 
                                "Started the cluster on all nodes (RedHat). ",
                                "Error starting the cluster")
    
    # Stop a cluster on the current node
    def stop_cluster():
        rc, out, err = module.run_command(commands[os][version]["status"])
        if rc == 0:
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["stop"]
                execute_command(module, result, cmd, 
                                "Successfully stopped the cluster. ",
                                "Error stopping the cluster")

    # Get name of existing cluster on the current node
    def get_cluster_name():
        cmd = "grep cluster_name /etc/corosync/corosync.conf | awk -F'[:]' '{print $2}' | tr -d '[:space:]'"
        rc, out, err = module.run_command(cmd, use_unsafe_shell=True)
        if rc == 0:
            return out
        else:
            result["stdout"] = out
            result["error_message"] = err
            result["command_used"] = cmd
            module.fail_json(msg="Failed to identify current cluster name", **result)

    # Get set of existing nodes in the cluster configuration
    def get_nodes():
        corosync_conf = open(commands[os]["file"], 'r')
        node_names = re.compile(commands[os]["regex"], re.M)
        return set(node_names.findall(corosync_conf.read()))

    # Get set of nodes that are online
    def get_nodes_online(timeout):
        seconds = 0
        nodes_online = set()
        while seconds < timeout:
            # String containing which nodes are online
            rc, out, err = module.run_command(commands[os][version]["online"], use_unsafe_shell=True)
            # See which nodes are online
            for node in nodes_set:
                if node in out:
                    nodes_online.add(node)
            # All nodes online
            if nodes_online == nodes_set:
                break
            # Atleast one node not online
            sleep(5)
            seconds += 5
        return nodes_online

    # Set up the cluster
    def setup_cluster():
        result["changed"] = True
        if not module.check_mode:
            if sid is None:
                module.fail_json(msg="Must supply sid when setting up new cluster", **result)
            if os == "Suse" and tier is None:
                module.fail_json(msg="Must supply tier when setting up a new Suse cluster", **result)
            cmd = commands[os][version]["setup"]
            execute_command(module, result, cmd, 
                            "Successfully set up the cluster. ",
                            "Failed to set up the cluster")
    
    # Current node joins a cluster running on another node (Suse)
    def join_cluster():
        result["changed"] = True
        if not module.check_mode:
            cmd = commands[os][version]["join"]
            execute_command(module, result, cmd, 
                            curr_node + " successfully joined the cluster. ",
                            "Failed to join existing cluster")
    
    # Adds external nodes to existing cluster running on current node
    def add_nodes(nodes):
        result["changed"] = True
        if not module.check_mode:
            start_cluster()
            nodes_to_add = " ".join(nodes)
            cmd = commands[os][version]["add"] + nodes_to_add
            execute_command(module, result, cmd, 
                            "Successfully added the following nodes to the cluster: " + nodes_to_add + ". ",
                            "Failed to add the following nodes to the cluster: " + nodes_to_add)

    # Delete nodes from existing cluster
    def remove_nodes(nodes):
        result["changed"] = True
        if not module.check_mode:
            if os == "RedHat":
                stop_cluster()
            if curr_node in nodes:
                nodes_to_remove = " ".join(nodes - {curr_node}) + " " + curr_node
            else:
                nodes_to_remove = " ".join(nodes)
            cmd = commands[os][version]["remove"] % nodes_to_remove
            execute_command(module, result, cmd, 
                            "Successfully removed the following nodes from the cluster: " + nodes_to_remove + ". ", 
                            "Failed to remove the following nodes to the cluster: " + nodes_to_remove)
    
    # Update an existing cluster
    def update_cluster():
        # Fail if names do match
        curr_cluster_name = get_cluster_name()
        if curr_cluster_name != desired_cluster_name:
            module.fail_json(msg="A cluster with the name %s already exists on the node" % curr_cluster_name, **result)
        # Get the difference in nodes
        existing_nodes = get_nodes()
        nodes_to_add = nodes_set - existing_nodes
        nodes_to_remove = existing_nodes - nodes_set
        # Configuration is as desired
        if len(nodes_to_add) == 0 and len(nodes_to_remove) == 0:
            result["message"] += "No changes needed: cluster is already set up with the nodes specified. "
        # Add missing nodes
        if len(nodes_to_add) > 0:
            add_nodes(nodes_to_add)
        # Remove extra nodes
        if len(nodes_to_remove) > 0:
            remove_nodes(nodes_to_remove)

    # Destroy an entire cluster configuration on all nodes
    def destroy_cluster():
        # Do nothing if names do not match
        curr_cluster_name = get_cluster_name()
        if curr_cluster_name != desired_cluster_name:
            result["message"] += "No changes needed: existing cluster detected but has a different name: %s " % curr_cluster_name
        else:
            result["changed"] = True
            if not module.check_mode:
                cmd = commands[os][version]["destroy"]
                if os == "Suse":
                    other_nodes = get_nodes() - {curr_node}
                    cmd = cmd % (curr_node, " ".join(other_nodes))
                execute_command(module, result, cmd, 
                                "Succesfully destroyed the cluster. ",
                                "Failed to destroy the cluster")


    # ==== MAIN CODE ====

    # Create or modify the cluster
    if state == "present":
        if cluster_exists:
            update_cluster()
        elif existing_node is not None and curr_node != existing_node:
            join_cluster()
        else:
            setup_cluster()
        if not module.check_mode and curr_node in nodes_set:
            # Ensure cluster is started
            start_all() if os == "RedHat" else start_cluster()
            # Wait for all nodes to go online
            nodes_online = get_nodes_online(120)
            result["online_nodes"] = nodes_online
            # All nodes specified should be online
            if nodes_online != nodes_set:
                module.fail_json(msg="Could not get all nodes online after 120s. The following nodes are not online: " + " ".join(nodes_set - nodes_online), **result)
    # Remove the cluster
    else:
        if cluster_exists:
            destroy_cluster()
        else:
            result["message"] += "No changes needed: no clusters were detected on the current node. "

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()