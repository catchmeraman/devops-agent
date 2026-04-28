variable "region"           { type = string; default = "us-east-1" }
variable "identifier"       { type = string; default = "prod-aurora" }
variable "db_name"          { type = string; default = "appdb" }
variable "master_username"  { type = string; default = "dbadmin" }
variable "instance_class"   { type = string; default = "db.r7g.large" }
variable "reader_count"     { type = number; default = 1 }
variable "vpc_id"           { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "app_cidr"         { type = string; default = "10.0.0.0/8" }
variable "environment"      { type = string; default = "production" }
