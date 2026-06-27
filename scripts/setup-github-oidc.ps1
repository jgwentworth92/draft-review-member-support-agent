<#
  One-time setup: lets GitHub Actions deploy to the Flex Consumption Function App
  using OIDC (federated credentials) — no stored secret.

  What it does:
    1. Creates an Azure AD app registration + service principal for GitHub.
    2. Grants it Contributor on the draft-review-rg resource group (scoped — not
       the whole subscription).
    3. Adds federated credentials trusting this repo's master branch AND the
       current feature branch (so you can test via "Run workflow" before merging).
    4. Sets AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_SUBSCRIPTION_ID as GitHub
       secrets. These are identifiers, not credentials — OIDC stores no secret.

  Run it once from a fresh PowerShell window:
    ./scripts/setup-github-oidc.ps1

  Re-running is safe-ish: app/role creation will error if they already exist;
  that's fine, the federated creds and secrets will still be (re)applied.
#>

$ErrorActionPreference = "Stop"

$RG       = "draft-review-rg"
$REPO     = "jgwentworth92/draft-review-member-support-agent"
$APPNAME  = "github-deploy-draft-review"
$BRANCHES = @("master", "feat/azure-functions-option-a")

Write-Host "Creating Azure AD app registration '$APPNAME'..."
$appId = az ad app create --display-name $APPNAME --query appId -o tsv
if (-not $appId) { throw "Failed to create app registration." }
Write-Host "  appId = $appId"

Write-Host "Creating service principal..."
az ad sp create --id $appId --only-show-errors | Out-Null

$subId    = az account show --query id -o tsv
$tenantId = az account show --query tenantId -o tsv

Write-Host "Assigning Contributor on resource group '$RG'..."
az role assignment create `
  --assignee $appId `
  --role Contributor `
  --scope "/subscriptions/$subId/resourceGroups/$RG" `
  --only-show-errors | Out-Null

function New-FederatedCred([string]$name, [string]$subject) {
  $params = [ordered]@{
    name      = $name
    issuer    = "https://token.actions.githubusercontent.com"
    subject   = $subject
    audiences = @("api://AzureADTokenExchange")
  } | ConvertTo-Json -Compress
  $tmp = New-TemporaryFile
  Set-Content -Path $tmp -Value $params -Encoding utf8
  try {
    az ad app federated-credential create --id $appId --parameters "@$tmp" --only-show-errors | Out-Null
    Write-Host "  federated credential '$name' -> $subject"
  } finally {
    Remove-Item $tmp -Force
  }
}

Write-Host "Adding federated credentials..."
foreach ($b in $BRANCHES) {
  $safeName = "github-" + ($b -replace "[^a-zA-Z0-9]", "-")
  New-FederatedCred $safeName "repo:${REPO}:ref:refs/heads/$b"
}

Write-Host "Setting GitHub secrets (identifiers, not sensitive)..."
$appId    | gh secret set AZURE_CLIENT_ID       --repo $REPO
$tenantId | gh secret set AZURE_TENANT_ID       --repo $REPO
$subId    | gh secret set AZURE_SUBSCRIPTION_ID --repo $REPO

Write-Host ""
Write-Host "Done. GitHub secrets now set:"
gh secret list --repo $REPO
