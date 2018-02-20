# oci_utils.oci_api high level OCI API

## Introduction

Oci-utils includes a high level API for using OCI services.  You are welcome
to use this API in other projects.
While this API is now and is subject to change, I won't break it unless it's
really necessary.

This document provides an overview and examples for using oci_api.

## Classes

Oci_api provides the following classes, most of which correspond to OCI
artifacts:

* OCISession: represents a connection to the OCI services.  You need an
  OCISession object to start interacting with OCI.

* OCICompartment: represents an OCI Compartment.  You can use it to list
  artifacts within the Compartment, such as Instances, Volumes, Subnets.

* OCIInstance: represents an OCI Instance.  In addition to querying details
  of the Instance, you can attach Volumes, VNICs and Secondary Private IPs.
  Managing the Instance (e.g. starting, stopping, changing details) is not
  currently implemented but is planned.

* OCIVCN: an OCI Virtual Cloud Network

* OCISubnet: an OCI Subnet

* OCIVNIC: represents a VNIC

* OCIPrivateIP: a secondary Private IP address.

* OCIVolume: A block storage (iSCSI) volume.  Supports attaching/detaching and
  querying details.

## Session

## Object details

## Exceptions

## Future Plans

* Managing Instances: start, stop, change name, etc