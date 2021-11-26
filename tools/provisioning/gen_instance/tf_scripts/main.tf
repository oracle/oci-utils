// Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
// Licensed under the Universal Permissive License v 1.0 as shown
// at http:/oss.oracle.com/licenses/upl.

variable "os_user" {
  description = "os user."
  type = string
}

variable "os_user_home" {
  description = "operator home directory"
  type = string
}

variable "server_ip" {
  description = "this server ipv4 address"
  type = string
}

variable "tenancy_ocid" {
  description = "tencancy identification."
  type = string
}

variable "compartment_ocid" {
  description = "compartment identification."
  type = string
}

variable "availability_domain" {
  description = "availability domain name."
  type = string
}

variable "user_ocid" {
  description = "user identification."
  type = string
}

variable "oci_private_key" {
  description = "path to use private key for OCI."
  type = string
}

variable "fingerprint" {
  description = "OCI key fingerprint."
  type = string
}

variable "region" {
  description = "oci region name."
  type = string
}

variable "shape" {
  description = "shape selection."
  type = string
}

//YYYYvariable "instance_flex_memory_in_gbs" {
//YYYY  description = "instance memorry size in GB."
//YYYY  type = number
//YYYY}

//YYYYvariable "instance_flex_ocpus" {
//YYYY  description = "amount of instance ocpus."
//YYYY  type = number
//YYYY}

variable "source_ocid" {
  description = "source identification."
  type = string
}

variable "source_type" {
  description = "source type identification."
  type = string
}

variable "instance_display_name" {
  description = "instance display name."
  type = string
}

variable "assign_public_ip" {
  description = "assign a public ip."
  type = bool
}

variable "vnic_display_name" {
  description = "vnic display name."
  type = string
}

variable "subnet_ocid" {
  description = "subnet identification."
  type = string
}

variable "ssh_public_key" {
  description = "user authorized keys path."
  type = string
}

variable "remote_user" {
  description = "user to connect to remote with sudo privileges."
  type = string
}

variable "ssh_private_key" {
  description = "local user private key path."
  type = string
}

variable "auth" {
  description = "authentication method."
  type = string
}

variable "log_file_path" {
  description = "path to logfile"
  type = string
}

variable "initial_script_path" {
  description = "path to initial bash script"
  type = string
}

module "base_instance"{
  source = "../base_instance"
  os_user = var.os_user
  os_user_home = var.os_user_home
  server_ip = var.server_ip
  auth = var.auth
  tenancy_ocid = var.tenancy_ocid
  compartment_ocid = var.compartment_ocid
  availability_domain = var.availability_domain
  user_ocid = var.user_ocid
  fingerprint = var.fingerprint
  region = var.region
  shape = var.shape
//YYYY  instance_flex_memory_in_gbs = var.instance_flex_memory_in_gbs
//YYYY  instance_flex_ocpus = var.instance_flex_ocpus
  source_ocid = var.source_ocid
  source_type = var.source_type
  instance_display_name = var.instance_display_name
  vnic_display_name = var.vnic_display_name
  assign_public_ip = var.assign_public_ip
  subnet_ocid = var.subnet_ocid
  ssh_public_key = var.ssh_public_key
  oci_private_key = var.oci_private_key
  remote_user = var.remote_user
  ssh_private_key = var.ssh_private_key
  log_file_path = var.log_file_path
  initial_script_path = var.initial_script_path
}
