# main.tf
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}


provider "aws" {
  region = var.aws_region

  # access_key = "AKIAEXAMPLEACCESSKEY12345"
  # secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

  # BAD: example of putting an AWS session token in the file
  # token = "AQoEXAMPLEH4aoAH0gNCAPy..."

  # BAD: hardcoded assume role credentials
  # assume_role {
  #   role_arn = "arn:aws:iam::123456789012:role/SomeRole"
  #   session_name = "example-session"
  #   external_id = "hardcoded-external-id" # sensitive secret shouldn't be here
  # }
}

resource "aws_db_instance" "example" {
  identifier = "example-db"
  engine     = "mysql"
  instance_class = "db.t3.micro"

  # username = "db_admin"
  # password = "Sup3rS3cretP@ssw0rd"

  allocated_storage    = 20
  skip_final_snapshot  = false
}



# output "db_password" {
#   value = "Sup3rS3cretP@ssw0rd"
#   sensitive = true
# }


locals {
 
  # service_account_key = <<EOF
  # {
  #   "type": "service_account",
  #   "project_id": "my-project",
  #   "private_key_id": "somekeyid",
  #   "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkq...\n-----END PRIVATE KEY-----\n",
  #   "client_email": "svc@my-project.iam.gserviceaccount.com"
  # }
  # EOF
}


resource "null_resource" "example_provision" {
  provisioner "local-exec" {
    # command = "deploy.sh"
    # environment = {
    #   API_KEY = "hardcoded-api-key-123456"
    # }
  }
}


