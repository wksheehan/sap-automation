[CmdletBinding()]
Param(
    [Parameter(Mandatory=$true)][string] $ConnStr,
    [Parameter(Mandatory=$true)][string] $TableName,
    [Parameter(Mandatory=$true)][string] $PartitionKey,
    [Parameter(Mandatory=$true)][string] $Id,
    [Parameter(Mandatory=$true)][string] $Crud,
    [Parameter(Mandatory=$false)][array] $Entity=@(),
    [Parameter(Mandatory=$false)][string] $SapObj="{}"
)

$env:AZURE_STORAGE_CONNECTION_STRING=$ConnStr

$SapObjKey=$TableName.Substring(0,$TableName.Length-1)
$IdJson = '{"Id": "' + $Id + '"}'
$SapObj = ($SapObj, $IdJson | jq --slurp 'add' | ConvertFrom-Json | ConvertTo-Json -Compress)

# Modify or read the database
if ($Crud -eq "create") {
    $SapObj = (ConvertTo-Json $SapObj -Compress)
    az storage entity insert --table-name $TableName --entity $Entity PartitionKey=$PartitionKey RowKey=$Id $SapObjKey=$SapObj
}
elseif ($Crud -eq "read") {
    az storage entity show --table-name $TableName --partition-key $PartitionKey --row-key $Id
}
elseif ($Crud -eq "read_sap") {
    $ExistingEntity=(az storage entity show --table-name $TableName --partition-key $PartitionKey --row-key $Id)
    $ExistingEntity | ConvertFrom-Json | Select-Object -exp $SapObjKey
}
elseif ($Crud -eq "update") {
    $ExistingEntity = (az storage entity show --table-name $TableName --partition-key $PartitionKey --row-key $Id 2>&1)
    if ( $lastExitCode -ne 0 ) {
        $SapObj = (ConvertTo-Json $SapObj -Compress)
        az storage entity insert --table-name $TableName --entity $Entity PartitionKey=$PartitionKey RowKey=$Id $SapObjKey=$SapObj
    }
    else {
        $ExistingSapObj = ($ExistingEntity | ConvertFrom-Json | Select-Object -exp $SapObjKey)
        $UpdatedSapObj = ($ExistingSapObj, $SapObj | jq --slurp 'add' | ConvertFrom-Json | ConvertTo-Json -Compress)
        $UpdatedSapObj = (ConvertTo-Json $UpdatedSapObj -Compress)
        az storage entity merge --table-name $TableName --entity $Entity PartitionKey=$PartitionKey RowKey=$Id $SapObjKey="$UpdatedSapObj"
    }
}
elseif ($Crud -eq "delete") {
    az storage entity delete --table-name $TableName --partition-key $PartitionKey --row-key $Id
}
else {
    Write-Output "InvalId crud operation supplied"
}

if ($LASTEXITCODE -ne 0) {
    Write-Output "FAILURE"
}
else {
    if (!$Crud.StartsWith("read")) {
        Write-Output "SUCCESS"
    }
}