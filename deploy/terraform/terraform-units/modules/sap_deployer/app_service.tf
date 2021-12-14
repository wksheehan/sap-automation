data "azuread_client_config" "current" {}

resource "azuread_application" "app_registration" {
    display_name     = "SAP-Automation-Form-${random_integer.priority.result}"
    owners           = [data.azuread_client_config.current.object_id]
    sign_in_audience = "AzureADMyOrg" # This may need to change
    
    api {
        oauth2_permission_scope {
            admin_consent_description  = "Allows users to sign in to the app, and allows the app to read the profile of signed-in users. It also allow the app to read basic company information of signed-in users."
            admin_consent_display_name = "Sign in and read user profile"
            enabled                    = true
            id                         = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
            type                       = "User"
            user_consent_description   = "Allows you to sign in to the app with your work account and let the app read your profile. It also allows the app to read basic company information."
            user_consent_display_name  = "Sign you in and read your profile"
            value                      = "User.Read"
        }
    }

    required_resource_access {
        resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph

        resource_access {
            id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read
            type = "Scope"
        }
    }

    web {
        homepage_url  = "https://sapdeployment-${random_integer.priority.result}.azurewebsites.net"
        logout_url    = "https://sapdeployment-${random_integer.priority.result}.azurewebsites.net/.auth/logout"
        redirect_uris = [
            "https://sapdeployment-${random_integer.priority.result}.azurewebsites.net/", 
            "https://sapdeployment-${random_integer.priority.result}.azurewebsites.net/.auth/login/aad/callback"
        ]
        implicit_grant {
            id_token_issuance_enabled = true
        }
    }
}

# For use with Azure AD
resource "azuread_application_password" "clientsecret" {
    application_object_id = azuread_application.app_registration.object_id
}

# Create the Linux App Service Plan
resource "azurerm_app_service_plan" "appserviceplan" {
    name                = "service-plan-${random_integer.priority.result}"
    resource_group_name = local.rg_name
    location            = local.rg_appservice_location
    kind = "Linux"
    reserved = true

    sku {
        tier = "Standard"
        size = "S1"
    }
}


# Create the web app, pass in the App Service Plan ID, and deploy code from a public GitHub repo
resource "azurerm_app_service" "webapp" {
    count               = var.configure ? 1 : 0
    name                = "sapdeployment-${random_integer.priority.result}"
    resource_group_name = local.rg_name
    location            = local.rg_appservice_location
    app_service_plan_id = azurerm_app_service_plan.appserviceplan.id
    
    site_config {
        linux_fx_version = "DOTNETCORE|3.1"
        app_command_line = "dotnet AutomationForm.dll"
    }

    # source_control {
    #     repo_url = "https://azurecat-sapdeploy@dev.azure.com/azurecat-sapdeploy/sap_deployment_automation/_git/persius"
    #     branch = "main"
    # }

    auth_settings {
        enabled = true
        issuer = "https://sts.windows.net/${data.azurerm_client_config.deployer.tenant_id}/v2.0"
        active_directory {
            client_id = azuread_application.app_registration.application_id
            client_secret = azuread_application_password.clientsecret.value
        }
    }

    connection_string {
        name  = "CMDB"
        type  = "Custom"
        value = var.cmdb_connection_string
    }
}