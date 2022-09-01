#!/bin/bash

<<instructions
 
 Accepted inputs
 CRUD: create, read / read_entity, read_sap, update, delete
 ENTITY: Key=Value pairs space separated
 SAP_OBJECT: Json string, e.g. '{"Id": "QA-WEEU-SAP-INFRASTRUCTURE"}' 

 Example queries
    READ: ./modify_table.sh --conn_str "conn_str" --table_name "Landscapes" --partition_key "PROD" --id "PROD-EUS2-SAP0262-INFRASTRUCTURE" --crud "read_sap"
    CREATE: ./modify_table.sh --conn_str "conn_str" --table_name "Landscapes" --partition_key "PROD" --id "PROD-EUS2-SAP0262-INFRASTRUCTURE" --crud "create" \
            --entity "IsDefault=False RandomGuy=102" --sap_object '{"Id":"DEV-WEEU-SAP01-INFRASTRUCTURE","IsDefault":true,"environment":"DEV","location":"westeurope","network_logical_name":"SAP01","automation_username":"azureadm"}'
    UPDATE: ./modify_table.sh --conn_str "conn_str" --table_name "Landscapes" --partition_key "PROD" --id "PROD-EUS2-SAP0262-INFRASTRUCTURE" --crud "update" \
            --entity "NewValue=100" --sap_object '{"newParam": "I am brand new"}'
    DELETE: ./modify_table.sh --conn_str "conn_str" --table_name "Landscapes" --partition_key "PROD" --id "PROD-EUS2-SAP0262-INFRASTRUCTURE" --crud "delete"
instructions

# Assign the options to variables
ARGS=$(getopt -a -n modify_table --options c:t:p:i:o:e:s --long "conn_str:,table_name:,partition_key:,id:,crud:,entity:,sap_object:" -- "$@")
VALID_ARGUMENTS=$?
if [ "${VALID_ARGUMENTS}" != 0 ]; then
    exit 1
fi

eval set -- "$ARGS"
while true; do
    case "$1" in
        -c | --conn_str)       
            conn_str="$2"
            if [ ${conn_str::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2 
            ;;
        -t | --table_name)
            table_name="$2"
            if [ ${table_name::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2 
            ;;
        -p | --partition_key)
            partition_key="$2"
            if [ ${partition_key::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2 
            ;;
        -i | --id)
            id="$2"
            if [ ${id::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2
            ;;
        -o | --crud)
            crud="$2"
            if [ ${crud::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2
            ;;
        -e | --entity)
            entity="$2"
            if [ ${entity::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            fi
            shift 2 
            ;;
        -s | --sap_object)
            sap_object="$2"
            if [ ${sap_object::1} == "-" ]; then
                echo "ERROR: option '$1' requires an argument"
                exit 1
            elif [ ${sap_object::1} != "{" ]; then
                echo "ERROR: expected JSON string for option '$1'"
                exit 1
            fi
            shift 2 
            ;;
        --)
            break 
            ;;
    esac
done

# Required variable check
params_missing=0
if [ -z "${conn_str}" ]; then
    echo "ERROR: the --conn_str flag is required"
    params_missing=1
fi
if [ -z "${table_name}" ]; then
    echo "ERROR: the --table_name flag is required"
    params_missing=1
fi
if [ -z "${partition_key}" ]; then
    echo "ERROR: the --partition_key flag is required"
    params_missing=1
fi
if [ -z "${id}" ]; then
    echo "ERROR: the --id flag is required"
    params_missing=1
fi
if [ -z "${crud}" ]; then
    echo "ERROR: the --crud flag is required"
    params_missing=1
fi
if [ -z "${entity}" ]; then
    entity=""
fi
if [ -z "${sap_object}" ]; then
    sap_object="{}"
fi
if [ $params_missing -eq 1 ]; then
    echo "Please try again"
    exit 1
fi

# Export the connection string
export AZURE_STORAGE_CONNECTION_STRING="$conn_str"

# Get the object name from table name by removing last character (e.g. "Landscapes" => "Landscape")
sap_obj_key=${table_name%?}


# Modify or read the database
# Default behavior for update will be upsert-merge
if [[ "$crud" == "create" ]]; then
    az storage entity insert --table-name $table_name --entity PartitionKey=$partition_key RowKey=$id $entity $sap_obj_key="$sap_object"
elif [[ "$crud" == "read_entity" || "$crud" == "read" ]]; then
    az storage entity show --table-name $table_name --partition-key $partition_key --row-key $id
elif [[ "$crud" == "read_sap" ]]; then
    entity=$(az storage entity show --table-name $table_name --partition-key $partition_key --row-key $id 2>&1)
    rc=$?
    if [ $rc != 0 ]; then
        echo -e "$entity"
        echo "FAILURE"
        exit $rc
    else
        echo "$entity" | jq ".$sap_obj_key | fromjson"
    fi
elif [[ "$crud" == "update" ]]; then
    existing_sap_obj=$(az storage entity show --table-name $table_name --partition-key $partition_key --row-key $id 2>&1)
    return_code=$?
    # create new object if it doesn't exist
    if [ $return_code != 0 ]; then
        az storage entity insert --table-name $table_name --entity PartitionKey=$partition_key RowKey=$id $entity $sap_obj_key="$sap_object"
    # else update existing object
    else
        existing_sap_obj=$(echo "$existing_sap_obj" | jq ".$sap_obj_key | fromjson")
        updated_sap_obj=$(echo "$existing_sap_obj" "$sap_object" | jq --slurp 'add')
        az storage entity merge --table-name $table_name --entity PartitionKey=$partition_key RowKey=$id $entity $sap_obj_key="$updated_sap_obj"
    fi
elif [[ "$crud" == "delete" ]]; then
    az storage entity delete --table-name $table_name --partition-key $partition_key --row-key $id
else
    echo "Invalid crud operation supplied"
    exit 1
fi

# Exit gracefully
return_code=$?
if [ $return_code != 0 ]; then
    echo "FAILURE"
else
    if [[ "$crud" != "read"* ]]; then
        echo "SUCCESS"
    fi
fi

unset AZURE_STORAGE_CONNECTION_STRING

exit $return_code