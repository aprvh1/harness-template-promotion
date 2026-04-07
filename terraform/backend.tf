# Remote state configuration (optional)
#
# Uncomment and configure based on your backend preference:
#
# Option 1: Terraform Cloud
# terraform {
#   cloud {
#     organization = "your-org-name"
#     workspaces {
#       name = "harness-template-promotion"
#     }
#   }
# }
#
# Option 2: S3 Backend
# terraform {
#   backend "s3" {
#     bucket         = "your-terraform-state-bucket"
#     key            = "harness/template-promotion/terraform.tfstate"
#     region         = "us-east-1"
#     encrypt        = true
#     dynamodb_table = "terraform-state-lock"
#   }
# }
#
# Option 3: Azure Storage
# terraform {
#   backend "azurerm" {
#     resource_group_name  = "your-rg-name"
#     storage_account_name = "yourstorageaccount"
#     container_name       = "tfstate"
#     key                  = "harness-template-promotion.tfstate"
#   }
# }
#
# Option 4: GCS Backend
# terraform {
#   backend "gcs" {
#     bucket = "your-tf-state-bucket"
#     prefix = "harness/template-promotion"
#   }
# }

# By default, state is stored locally in terraform.tfstate
# For team collaboration, configure a remote backend above
