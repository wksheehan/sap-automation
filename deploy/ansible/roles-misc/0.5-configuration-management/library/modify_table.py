#!/usr/bin/env

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: modify_table

short_description: Performs a CRUD operation to Azure Table Storage.

version_added: "1.0.0"

description: This module can create, update, read, and delete one or many entities in Azure Table Storage.

options:
    conn_str:
        description: The connection string for the storage account.
        required: true
        type: str
    table_name:
        description: The name of the table to modify.
        required: true
        type: str
    partition_key:
        description: The partition key of the entity to modify.
        required: true
        type: str
    id:
        description: The id or row key of the entity to modify
        required: true
        type: str
    crud:
        description: 
            - The operation to perform
            - Accepted values: ("create", "read", "delete", "upsert-merge", "upsert-replace", "update-merge", "update-replace")
            - Upsert => merge or replace an entity in the table; if it does not exist, create the entity
            - Update => merge or replace an entity in the table; if it does not exist, fail
        required: true
        type: str
    entity:
        description:
            - The entity parameters that will be added or modified 
            - Dictionary mapping parameter names to their values
        required: false
        type: dict
    sap_object:
        description:
            - The workload zone or system parameters to be added or modified
            - Dictionary mapping parameter names to their values
        required: false
        type: dict

author:
    - William Sheehan (@wksheehan)
'''

EXAMPLES = r'''
# Create a new system entity 
- name: Create system
  modify_table:
    conn_str: "<myconn_str>"
    table_name: "Systems"
    partition_key: "DEV"
    id: "DEV-WEEU-SAP-100"
    crud: "create"
    sap_object: { "environment": "DEV", "location": "westeurope" }

# Update an existing system entity
- name: Update system
  modify_table:
    conn_str: "<myconn_str>"
    table_name: "Systems"
    partition_key: "DEV"
    id: "DEV-WEEU-SAP-100"
    crud: "update-merge"
    sap_object: { "use_prefix": false }

# Read an existing system object
- name: Read a system entity
  modify_table:
    conn_str: "<myconn_str>"
    table_name: "Systems"
    partition_key: "DEV"
    id: "DEV-WEEU-SAP-100"
    crud: "read"

# Delete a system object
- name: Delete entire system entity
  modify_table:
    conn_str: "<myconn_str>"
    table_name: "Systems"
    partition_key: "DEV"
    id: "DEV-WEEU-SAP-100"
    crud: "delete"
'''

RETURN = r'''
# These are examples of possible return values, and in general should use other names for return values.
changed:
    description: Whether or not a modification to the database was made
    type: boolean
    returned: always
    sample: True
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'Successfully added DEV-WEEU-SAP-100 to Systems'
object:
    description: A JSON representation of the object during a read operation.
    type: JSON
    returned: sometimes
    sample: {'partition_key': PROD, 'RowKey': 'PROD-WEEU-SAP-123', 'environment': 'PROD', 'location': 'westeurope'}
'''

from ansible.module_utils.basic import AnsibleModule
from azure.core.exceptions import ResourceExistsError, HttpResponseError, ResourceNotFoundError
from azure.data.tables import TableServiceClient
from azure.data.tables import UpdateMode
import json


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        conn_str=dict(type='str', required=True),
        table_name=dict(type='str', required=True),
        partition_key=dict(type='str', required=True),
        id=dict(type='str', required=True),
        crud=dict(type='str', required=True, choices=["create", "read", "delete", "upsert-merge", "upsert-replace", "update-merge", "update-replace"]),
        entity=dict(type='dict', required=False, default={}),
        sap_object=dict(type='dict', required=False, default={})
    )

    # seed the result dict in the object
    result = dict(
        changed=False,
        message="",
        object=None
    )

    # abstraction object to work with ansible
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # ================= MAIN CODE HERE ======================

    # capture the input values
    conn_str = module.params["conn_str"]
    table_name = module.params["table_name"]
    partition_key = module.params["partition_key"]
    id = module.params["id"]
    crud = module.params["crud"].lower()
    entity = module.params["entity"]
    sap_object = module.params["sap_object"]

    sap_object_key = "Landscape" if table_name == "Landscapes" else "System"

    entity["PartitionKey"] = partition_key
    entity["RowKey"] = id

    table_service_client = TableServiceClient.from_connection_string(conn_str)
    table = table_service_client.create_table_if_not_exists(table_name)

    def persist(existingEntity):
        existing_sap_object = json.loads(existingEntity[sap_object_key])
        for i,j in enumerate(sap_object):
            existing_sap_object[j] = sap_object[j]
        
        return json.dumps(existing_sap_object)

    try:
        if crud == "create":
            entity[sap_object_key] = json.dumps(sap_object)
            table.create_entity(entity=entity)
            result["changed"] = True
            result["message"] = "Successfully added " + id + " to " + table_name
        elif crud == "read":
            existingEntity = table.get_entity(partition_key=partition_key, row_key=id)
            result["object"] = existingEntity
            result["message"] = "Successfully read " + id + " from " + table_name
        elif crud == "upsert-merge":
            try:
                existingEntity = table.get_entity(partition_key=partition_key, row_key=id)
                entity[sap_object_key] = persist(existingEntity)
            except ResourceNotFoundError:
                entity[sap_object_key] = json.dumps(sap_object)
            table.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
            result["changed"] = True
            result["message"] = "Successfully upserted " + id + " into " + table_name
        elif crud == "upsert-replace":
            entity[sap_object_key] = json.dumps(sap_object)
            table.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            result["changed"] = True
            result["message"] = "Successfully upserted " + id + " into " + table_name
        elif crud == "update-merge":
            existingEntity = table.get_entity(partition_key=partition_key, row_key=id)
            entity[sap_object_key] = persist(existingEntity)
            table.update_entity(mode=UpdateMode.MERGE, entity=entity)
            result["changed"] = True
            result["message"] = "Successfully updated " + id + " in " + table_name
        elif crud == "update-replace":
            entity[sap_object_key] = json.dumps(sap_object)
            table.update_entity(mode=UpdateMode.REPLACE, entity=entity)
            result["changed"] = True
            result["message"] = "Successfully updated " + id + " in " + table_name
        elif crud == "delete":
            table.delete_entity(partition_key=partition_key, row_key=id)
            result["changed"] = True
            result["message"] = "Successfully deleted " + id + " from " + table_name
        else:
            module.fail_json(msg="Invalid CRUD operation", **result)
    except Exception as e:
        result["changed"] = False
        result["message"] = "Error during " + crud
        module.fail_json(msg=repr(e), **result)

    # Success
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
