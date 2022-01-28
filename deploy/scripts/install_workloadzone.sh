#!/bin/bash

#colors for terminal
boldreduscore="\e[1;4;31m"
boldred="\e[1;31m"
cyan="\e[1;36m"
resetformatting="\e[0m"

#External helper functions
#. "$(dirname "${BASH_SOURCE[0]}")/deploy_utils.sh"
full_script_path="$(realpath "${BASH_SOURCE[0]}")"
script_directory="$(dirname "${full_script_path}")"

#call stack has full scriptname when using source
source "${script_directory}/deploy_utils.sh"

#helper files
source "${script_directory}/helpers/script_helpers.sh"

force=0
called_from_ado=0

INPUT_ARGUMENTS=$(getopt -n install_workloadzone -o p:d:e:k:o:s:c:n:t:v:aifh --longoptions parameterfile:,deployer_tfstate_key:,deployer_environment:,subscription:,spn_id:,spn_secret:,tenant_id:,state_subscription:,keyvault:,storageaccountname:,ado,auto-approve,force,help -- "$@")
VALID_ARGUMENTS=$?
if [ "$VALID_ARGUMENTS" != "0" ]; then
    showhelp
fi

eval set -- "$INPUT_ARGUMENTS"
while :
do
    case "$1" in
        -p | --parameterfile)                      parameterfile="$2"               ; shift 2 ;;
        -d | --deployer_tfstate_key)               deployer_tfstate_key="$2"        ; shift 2 ;;
        -e | --deployer_environment)               deployer_environment="$2"        ; shift 2 ;;
        -k | --state_subscription)                 STATE_SUBSCRIPTION="$2"          ; shift 2 ;;
        -o | --storageaccountname)                 REMOTE_STATE_SA="$2"             ; shift 2 ;;
        -s | --subscription)                       subscription="$2"                ; shift 2 ;;
        -c | --spn_id)                             client_id="$2"                   ; shift 2 ;;
        -v | --keyvault)                           keyvault="$2"                    ; shift 2 ;;
        -n | --spn_secret)                         spn_secret="$2"                  ; shift 2 ;;
        -a | --ado)                                called_from_ado=1                ; shift ;;
        -t | --tenant_id)                          tenant_id="$2"                   ; shift 2 ;;
        -f | --force)                              force=1                          ; shift ;;
        -i | --auto-approve)                       approve="--auto-approve"         ; shift ;;
        -h | --help)                               workload_zone_showhelp
        exit 3                           ; shift ;;
        --) shift; break ;;
    esac
done
tfstate_resource_id=""
tfstate_parameter=""

deployer_tfstate_key_parameter=""
landscape_tfstate_key=""
landscape_tfstate_key_parameter=""

deployment_system="sap_landscape"

echo "Deployer environment: $deployer_environment"
if [ 1 == $called_from_ado ] ; then
    this_ip=$(curl -s ipinfo.io/ip) >/dev/null 2>&1
    export TF_VAR_Agent_IP=$this_ip
    echo "Agent IP: $this_ip"
fi

if [ 1 == $called_from_ado ] ; then
    this_ip=$(curl -s ipinfo.io/ip) >/dev/null 2>&1
    export TF_VAR_Agent_IP=$this_ip
    echo "Agent IP: $this_ip"
fi


workload_file_parametername=$(basename "${parameterfile}")

param_dirname=$(dirname "${parameterfile}")

if [ "$param_dirname" != '.' ]; then
    echo ""
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#  $boldred Please run this command from the folder containing the parameter file$resetformatting               #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    exit 3
fi

if [ ! -f "${workload_file_parametername}" ]
then
    printf -v val %-40.40s "$workload_file_parametername"
    echo ""
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#                 $boldreduscore Parameter file does not exist: ${val}$resetformatting #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    exit 3
fi

# Check that the exports ARM_SUBSCRIPTION_ID and DEPLOYMENT_REPO_PATH are defined
validate_exports
return_code=$?
if [ 0 != $return_code ]; then
    exit $return_code
fi

# Check that Terraform and Azure CLI is installed
validate_dependencies
return_code=$?
if [ 0 != $return_code ]; then
    exit $return_code
fi

# Check that parameter files have environment and location defined
validate_key_parameters "$workload_file_parametername"
if [ 0 != $return_code ]; then
    exit $return_code
fi

# Convert the region to the correct code
get_region_code "$region"

private_link_used=$(grep  "use_private_endpoint=" "${param_dirname}"/"${parameterfile}" |  cut -d'=' -f2 | tr -d '"')

key=$(echo "${workload_file_parametername}" | cut -d. -f1)
landscape_tfstate_key=${key}.terraform.tfstate



#Persisting the parameters across executions

automation_config_directory=~/.sap_deployment_automation
generic_config_information="${automation_config_directory}"/config

workload_config_information="${automation_config_directory}"/"${environment}""${region_code}"

if [ "${force}" == 1 ]
then
    if [ -f "${workload_config_information}" ]
    then
        rm "${workload_config_information}"
    fi
    rm -Rf .terraform terraform.tfstate*
fi

echo "Workload configuration file: $workload_config_information"

if [ "${force}" == 1 ]
then
    if [ -f "${workload_config_information}" ]
    then
        rm "${workload_config_information}"
    fi
    rm -Rf .terraform terraform.tfstate*
fi

if [ ! -f "${workload_config_information}" ]
then
    # Ask for deployer environment name and try to read the deployer state file and resource group details from the configuration file
    if [ -z "$deployer_environment" ]
    then
        read -p "Deployer environment name: " deployer_environment
    fi
    
    deployer_config_information="${automation_config_directory}"/"${deployer_environment}""${region_code}"
    if [ -f "$deployer_config_information" ]
    then
        load_config_vars "${deployer_config_information}" "keyvault"
        load_config_vars "${deployer_config_information}" "REMOTE_STATE_RG"
        load_config_vars "${deployer_config_information}" "REMOTE_STATE_SA"
        load_config_vars "${deployer_config_information}" "tfstate_resource_id"
        load_config_vars "${deployer_config_information}" "deployer_tfstate_key"
        load_config_vars "${deployer_config_information}" "subscription"
        
        save_config_vars "${workload_config_information}" \
        keyvault \
        subscription \
        deployer_tfstate_key \
        tfstate_resource_id \
        REMOTE_STATE_SA \
        REMOTE_STATE_RG
    fi
fi

if [ -z "$tfstate_resource_id" ]
then
    echo "No tfstate_resource_id"
    if [ -n "$deployer_environment" ]
    then
        deployer_config_information="${automation_config_directory}"/"${deployer_environment}""${region_code}"
        echo "Deployer config file $deployer_config_information"
        if [ -f "$deployer_config_information" ]
        then
            load_config_vars "${deployer_config_information}" "keyvault"
            load_config_vars "${deployer_config_information}" "REMOTE_STATE_RG"
            load_config_vars "${deployer_config_information}" "REMOTE_STATE_SA"
            load_config_vars "${deployer_config_information}" "tfstate_resource_id"
            load_config_vars "${deployer_config_information}" "deployer_tfstate_key"
            load_config_vars "${deployer_config_information}" "subscription"
            echo "tfstate_resource_id $tfstate_resource_id"
            save_config_vars "${workload_config_information}" \
                tfstate_resource_id
            
            save_config_vars "${workload_config_information}" \
            keyvault \
            subscription \
            deployer_tfstate_key \
            REMOTE_STATE_SA \
            REMOTE_STATE_RG
        fi
    fi
else
    echo "tfstate_resource_id $tfstate_resource_id"
    save_config_vars "${workload_config_information}" \
            tfstate_resource_id
fi


init "${automation_config_directory}" "${generic_config_information}" "${workload_config_information}"

param_dirname=$(pwd)
var_file="${param_dirname}"/"${parameterfile}"
export TF_DATA_DIR="${param_dirname}/.terraform"

if [ -n "$subscription" ]
then
    if is_valid_guid "$subscription"  ; then
        echo "Valid subscription format"
    else
        printf -v val %-40.40s "$subscription"
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#   The provided subscription is not valid:$boldred ${val} $resetformatting#   "
        echo "#                                                                                       #"
        echo "#########################################################################################"
        exit 65
    fi
fi

if [ -n "$STATE_SUBSCRIPTION" ]
then
    echo "Saving the state subscription"
    if is_valid_guid "$STATE_SUBSCRIPTION" ; then
        echo "Valid subscription format"
        save_config_vars "${workload_config_information}" \
            STATE_SUBSCRIPTION
    else
        printf -v val %-40.40s "$STATE_SUBSCRIPTION"
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#The provided state_subscription is not valid:$boldred ${val} $resetformatting#"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        exit 65
    fi
    
fi

if [ -n "$client_id" ]
then
    if is_valid_guid "$client_id" ; then
        echo "Valid spn id format"
    else
        printf -v val %-40.40s "$client_id"
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#         The provided spn_id is not valid:$boldred ${val} $resetformatting   #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        exit 65
    fi
fi

if [ -n "$tenant_id" ]
then
    if is_valid_guid "$tenant_id" ; then
        echo "Valid spn id format"
    else
        printf -v val %-40.40s "$tenant_id"
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#       The provided tenant_id is not valid:$boldred ${val} $resetformatting  #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        exit 65
    fi
    
fi

if [ -n "$keyvault" ]
then
    if valid_kv_name "$keyvault" ; then
        save_config_var "keyvault" "${workload_config_information}"
    else
        printf -v val %-40.40s "$keyvault"
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#       The provided keyvault is not valid:$boldred ${val} $resetformatting  #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        exit 65
    fi
    
fi


#setting the user environment variables
set_executing_user_environment_variables "none"

load_config_vars "${workload_config_information}" "REMOTE_STATE_SA"
load_config_vars "${workload_config_information}" "REMOTE_STATE_RG"
load_config_vars "${workload_config_information}" "tfstate_resource_id"
load_config_vars "${workload_config_information}" "STATE_SUBSCRIPTION"
load_config_vars "${workload_config_information}" "subscription"
load_config_vars "${workload_config_information}" "keyvault"
load_config_vars "${workload_config_information}" "deployer_tfstate_key"

if [ -n "$tfstate_resource_id" ]
then
    REMOTE_STATE_RG=$(echo "$tfstate_resource_id" | cut -d / -f5)
    REMOTE_STATE_SA=$(echo "$tfstate_resource_id" | cut -d / -f9)
    STATE_SUBSCRIPTION=$(echo "$tfstate_resource_id" | cut -d / -f3)

    save_config_vars "${workload_config_information}" \
    REMOTE_STATE_SA \
    REMOTE_STATE_RG \
    STATE_SUBSCRIPTION
else
    get_and_store_sa_details ${REMOTE_STATE_SA} ${workload_config_information}
fi

if [ -n "$STATE_SUBSCRIPTION" ]
then
    echo ""
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#       $cyan Changing the subscription to: $STATE_SUBSCRIPTION $resetformatting            #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    az account set --sub "${STATE_SUBSCRIPTION}"
    account_set=1
fi

if [ -z "$REMOTE_STATE_SA" ]
then
    if [ -z "$REMOTE_STATE_RG" ]
    then
        load_config_vars "${workload_config_information}" "tfstate_resource_id"
        if [ -n "${tfstate_resource_id}" ]
        then
            REMOTE_STATE_RG=$(echo "$tfstate_resource_id" | cut -d / -f5)
            REMOTE_STATE_SA=$(echo "$tfstate_resource_id" | cut -d / -f9)
            STATE_SUBSCRIPTION=$(echo "$tfstate_resource_id" | cut -d / -f3)
        fi
    fi
    
    tfstate_parameter=" -var tfstate_resource_id=${tfstate_resource_id}"
else
    if [ -z "$REMOTE_STATE_RG" ]
    then
        get_and_store_sa_details "${REMOTE_STATE_SA}" "${workload_config_information}"
        load_config_vars "${workload_config_information}" "STATE_SUBSCRIPTION"
        load_config_vars "${workload_config_information}" "REMOTE_STATE_RG"
        load_config_vars "${workload_config_information}" "tfstate_resource_id"
    fi
fi

if [ -n "$keyvault" ]
then
    secretname="${environment}"-client-id
    
    az keyvault secret show --name "$secretname" --vault "$keyvault" --only-show-errors 2>error.log
    if [ -s error.log ]
    then
        save_config_var "client_id" "${workload_config_information}"
        save_config_var "tenant_id" "${workload_config_information}"
        
        if [ -n "$spn_secret" ]
        then
            allParams=$(printf " --workload --environment %s --region %s --vault %s --spn_secret %s --subscription %s --spn_id %s " "${environment}" "${region_code}" "${keyvault}" "${spn_secret}" "${subscription}" "${client_id}" )
            
            "${DEPLOYMENT_REPO_PATH}"/deploy/scripts/set_secrets.sh $allParams
            if [ $? -eq 255 ]
            then
                exit $?
            fi
        else
            read -p "Do you want to specify the Workload SPN Details Y/N?"  ans
            answer=${ans^^}
            if [ $answer == 'Y' ]; then
                allParams=$(printf " --workload --environment %s --region %s --vault %s --subscription %s  --spn_id %s " "${environment}" "${region_code}" "${keyvault}" "${subscription}" "${client_id}" )
                
                "${DEPLOYMENT_REPO_PATH}"/deploy/scripts/set_secrets.sh ${allParams}
                if [ $? -eq 255 ]
                then
                    exit $?
                fi
            fi
        fi
    fi
    if [ -f error.log ]
    then
        rm error.log
    fi
    
    if [ -f kv.log ]
    then
        rm kv.log
    fi
fi

if [ -z "${deployer_tfstate_key}" ]
then
    load_config_vars "${workload_config_information}" "deployer_tfstate_key"
    if [ -n "${deployer_tfstate_key}" ]
    then
        # Deployer state was specified in ~/.sap_deployment_automation library config
        deployer_tfstate_key_parameter=" -var deployer_tfstate_key=${deployer_tfstate_key}"
    fi
else
    deployer_tfstate_key_parameter=" -var deployer_tfstate_key=${deployer_tfstate_key}"
    save_config_vars "${workload_config_information}" deployer_tfstate_key
fi

if [ -z "${REMOTE_STATE_SA}" ]; then
    read -p "Terraform state storage account name:"  REMOTE_STATE_SA
    get_and_store_sa_details "${REMOTE_STATE_SA}" "${workload_config_information}"
    load_config_vars "${workload_config_information}" "STATE_SUBSCRIPTION"
    load_config_vars "${workload_config_information}" "REMOTE_STATE_RG"
    load_config_vars "${workload_config_information}" "tfstate_resource_id"
    
    tfstate_parameter=" -var tfstate_resource_id=${tfstate_resource_id}"
    
    if [ -n "${STATE_SUBSCRIPTION}" ]
    then
        if [ $account_set == 0 ]
        then
            az account set --sub "${STATE_SUBSCRIPTION}"
            account_set=1
        fi
    fi
fi

if [ -z "${REMOTE_STATE_RG}" ]; then
    if [ -n "${REMOTE_STATE_SA}" ]; then
        get_and_store_sa_details ${REMOTE_STATE_SA} "${workload_config_information}"
        load_config_vars "${workload_config_information}" "STATE_SUBSCRIPTION"
        load_config_vars "${workload_config_information}" "REMOTE_STATE_RG"
        load_config_vars "${workload_config_information}" "tfstate_resource_id"
        
        tfstate_parameter=" -var tfstate_resource_id=${tfstate_resource_id}"
    else
        option="REMOTE_STATE_RG"
        read -p "Remote state resource group name:"  REMOTE_STATE_RG
        save_config_vars "${workload_config_information}" REMOTE_STATE_RG
    fi
fi

if [ -n "${tfstate_resource_id}" ]
then
    tfstate_parameter=" -var tfstate_resource_id=${tfstate_resource_id}"
else
    get_and_store_sa_details ${REMOTE_STATE_SA} "${workload_config_information}"
    load_config_vars "${workload_config_information}" "tfstate_resource_id"
    tfstate_parameter=" -var tfstate_resource_id=${tfstate_resource_id}"
fi

terraform_module_directory="$(realpath "${DEPLOYMENT_REPO_PATH}"/deploy/terraform/run/"${deployment_system}" )"

if [ ! -d "${terraform_module_directory}" ]
then
    printf -v val %-40.40s "$deployment_system"
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#  $boldred Incorrect system deployment type specified: ${val}$resetformatting#"
    echo "#                                                                                       #"
    echo "#     Valid options are:                                                                #"
    echo "#       sap_landscape                                                                   #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    exit 1
fi

ok_to_proceed=false
new_deployment=false

#Plugins
if [ ! -d "$HOME/.terraform.d/plugin-cache" ]
then
    mkdir -p "$HOME/.terraform.d/plugin-cache"
fi
export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
root_dirname=$(pwd)

check_output=0

if [ $account_set == 0 ]
then
    az account set --sub "${STATE_SUBSCRIPTION}"
    account_set=1
fi

if [ ! -d ./.terraform/ ];
then
    terraform -chdir="${terraform_module_directory}" init -upgrade=true  \
    --backend-config "subscription_id=${STATE_SUBSCRIPTION}"             \
    --backend-config "resource_group_name=${REMOTE_STATE_RG}"            \
    --backend-config "storage_account_name=${REMOTE_STATE_SA}"           \
    --backend-config "container_name=tfstate"                            \
    --backend-config "key=${key}.terraform.tfstate"
    return_value=$?
else
    temp=$(grep "\"type\": \"local\"" .terraform/terraform.tfstate)
    if [ -n "${temp}" ]
    then
        
        terraform -chdir="${terraform_module_directory}" init -upgrade=true -force-copy \
        --backend-config "subscription_id=${STATE_SUBSCRIPTION}"                        \
        --backend-config "resource_group_name=${REMOTE_STATE_RG}"                       \
        --backend-config "storage_account_name=${REMOTE_STATE_SA}"                      \
        --backend-config "container_name=tfstate"                                       \
        --backend-config "key=${key}.terraform.tfstate"
        return_value=$?
    else
        check_output=1
        terraform -chdir="${terraform_module_directory}" init -upgrade=true -reconfigure \
        --backend-config "subscription_id=${STATE_SUBSCRIPTION}"                         \
        --backend-config "resource_group_name=${REMOTE_STATE_RG}"                        \
        --backend-config "storage_account_name=${REMOTE_STATE_SA}"                       \
        --backend-config "container_name=tfstate"                                        \
        --backend-config "key=${key}.terraform.tfstate"
        return_value=$?
    fi
fi
if [ 0 != $return_value ]
then
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#                            $boldreduscore!!! Error when Initializing !!!$resetformatting                            #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    exit $return_value
fi

save_config_var "REMOTE_STATE_SA" "${workload_config_information}"
save_config_var "subscription" "${workload_config_information}"
save_config_var "STATE_SUBSCRIPTION" "${workload_config_information}"
save_config_var "tfstate_resource_id" "${workload_config_information}"

if [ 1 == $check_output ]
then
    outputs=$(terraform -chdir="${terraform_module_directory}" output)
    if echo "${outputs}" | grep "No outputs"; then
        ok_to_proceed=true
        new_deployment=true
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#                                  $cyan New deployment $resetformatting                                     #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
    else
        echo ""
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#                          $cyan Existing deployment was detected $resetformatting                           #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        echo ""
        
        deployed_using_version=$(terraform -chdir="${terraform_module_directory}" output automation_version)
        if [ -z "${deployed_using_version}" ]; then
            echo ""
            echo "#########################################################################################"
            echo "#                                                                                       #"
            echo -e "#   $boldred The environment was deployed using an older version of the Terrafrom templates $resetformatting    #"
            echo "#                                                                                       #"
            echo "#                               !!! Risk for Data loss !!!                              #"
            echo "#                                                                                       #"
            echo "#        Please inspect the output of Terraform plan carefully before proceeding        #"
            echo "#                                                                                       #"
            echo "#########################################################################################"
            if [ 1 == $called_from_ado ] ; then
                unset TF_DATA_DIR
                exit 1
            fi
            
            read -p "Do you want to continue Y/N?"  ans
            answer=${ans^^}
            if [ $answer == 'Y' ]; then
                ok_to_proceed=true
            else
                unset TF_DATA_DIR
                exit 1
            fi
        else
            printf -v val %-.20s "$deployed_using_version"
            echo ""
            echo "#########################################################################################"
            echo "#                                                                                       #"
            echo -e "#             $cyan Deployed using the Terraform templates version: $val $resetformatting               #"
            echo "#                                                                                       #"
            echo "#########################################################################################"
            echo ""
            #Add version logic here
        fi
    fi
fi

echo ""
echo "#########################################################################################"
echo "#                                                                                       #"
echo -e "#                           $cyan  Running Terraform plan $resetformatting                                   #"
echo "#                                                                                       #"
echo "#########################################################################################"
echo ""

terraform -chdir="${terraform_module_directory}" plan -no-color -detailed-exitcode  -var-file=${var_file} $tfstate_parameter $deployer_tfstate_key_parameter > plan_output.log
return_value=$?
if [ 1 == $return_value ]
then
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#                           $boldreduscore  Errors running plan $resetformatting                                   #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    if [ -f plan_output.log ] ; then
        cat plan_output.log
        rm plan_output.log
    fi
    unset TF_DATA_DIR
    exit $return_value
fi

ok_to_proceed=0
if [ 0 == $return_value ] ; then
    echo ""
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo -e "#                          $cyan Infrastructure is up to date $resetformatting                               #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    if [ -f plan_output.log ]
    then
        rm plan_output.log
    fi
    
    if [ "$private_link_used" == "true" ]; then
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#                             $cyan Configuring Private Link $resetformatting                                #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        echo ""
        
        app_subnet_id=$(terraform -chdir="${terraform_module_directory}" output app_subnet_id| tr -d \")
        az storage account network-rule add -g $REMOTE_STATE_RG --account-name $REMOTE_STATE_SA   --subnet $app_subnet_id  --only-show-errors  --output none
        
    fi
    
    workloadkeyvault=$(terraform -chdir="${terraform_module_directory}"  output workloadzone_kv_name | tr -d \")
    save_config_var "workloadkeyvault" "${workload_config_information}"
    save_config_vars "landscape_tfstate_key" "${workload_config_information}"
    ok_to_proceed=0
fi

if [ 2 == $return_value ] ; then
    test=$(grep kv_user plan_output.log | grep -m1 replaced)
    if [ -n "${test}" ] ; then
        echo ""
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#                              $boldred !!! Risk for Data loss !!! $resetformatting                             #"
        echo "#                                                                                       #"
        echo "#        Please inspect the output of Terraform plan carefully before proceeding        #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        echo ""
        if [ 1 == $called_from_ado ] ; then
            unset TF_DATA_DIR
            exit 1
        fi
        read -n 1 -r -s -p $'Press enter to continue...\n'
        
        cat plan_output.log
        read -p "Do you want to continue with the deployment Y/N?"  ans
        answer=${ans^^}
        if [ $answer == 'Y' ]; then
            ok_to_proceed=1
        else
            unset TF_DATA_DIR
            
            exit 0
        fi
    else
        ok_to_proceed=1
    fi
fi

if [ 1 == $ok_to_proceed ]; then
    echo ""
    echo "#########################################################################################"
    echo "#                                                                                       #"
    echo  -e "#                            $cyan Running Terraform apply $resetformatting                                  #"
    echo "#                                                                                       #"
    echo "#########################################################################################"
    echo ""
    
    terraform -chdir="${terraform_module_directory}" apply ${approve} -var-file=${var_file} $tfstate_parameter $landscape_tfstate_key_parameter $deployer_tfstate_key_parameter
    return_value=$?
fi

save_config_var "landscape_tfstate_key" "${workload_config_information}"

if [ 0 == $return_value ] ; then
    save_config_vars "landscape_tfstate_key" "${workload_config_information}"
    workloadkeyvault=$(terraform -chdir="${terraform_module_directory}"  output workloadzone_kv_name | tr -d \")
    
    temp=$(echo "${workloadkeyvault}" | grep "Warning")
    if [ -z "${temp}" ]
    then
        temp=$(echo "${workloadkeyvault}" | grep "Backend reinitialization required")
        if [ -z "${temp}" ]
        then
            
            printf -v val %-.20s "$workloadkeyvault"
            
            echo ""
            echo "#########################################################################################"
            echo "#                                                                                       #"
            echo -e "#                Keyvault to use for System details:$cyan $val $resetformatting               #"
            echo "#                                                                                       #"
            echo "#########################################################################################"
            echo ""
            
            save_config_var "workloadkeyvault" "${workload_config_information}"
        fi
    fi
    unset TF_DATA_DIR
    
    if [ "$private_link_used" == "true" ]; then
        echo "#########################################################################################"
        echo "#                                                                                       #"
        echo -e "#                             $cyan Configuring Private Link $resetformatting                                #"
        echo "#                                                                                       #"
        echo "#########################################################################################"
        echo ""
        
        app_subnet_id=$(terraform -chdir="${terraform_module_directory}" output app_subnet_id| tr -d \")
        az storage account network-rule add -g $REMOTE_STATE_RG --account-name $REMOTE_STATE_SA   --subnet $app_subnet_id  --only-show-errors  --output none
        
    fi
    
fi

now=$(date)
cat <<EOF > "${workload_config_information}".md
# Workload Zone Deployment #

Date : "${now}"

## Configuration details ##

| Item                    | Name                 |
| ----------------------- | -------------------- |
| Environment             | $environment         |
| Location                | $region              |
| Keyvault Name           | ${workloadkeyvault}  |

EOF

unset TF_DATA_DIR

exit $return_value
