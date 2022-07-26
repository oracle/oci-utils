# oci_utils.oci_api high level OCI API

## Introduction

Oci-utils includes a high level API for using OCI services.  You are welcome
to use this API in other projects.
While this API is new and is subject to change, I won't break it unless it's
really necessary.

This document provides an overview and examples for using oci_api.

To use oci_api import oci_utils.oci_api:

```python
import oci_utils.oci_api
```

Creating an OCISession() object will fail if the SDK isn't properly
configured or authentication failed.

```python
import sys
import oci_utils.oci_api

try:
    sess = oci_utils.oci_api.OCISession()
except Exception as e:
    sys.stderr.write("Failed to access OCI services: %s\n" % e)
```

OCISession uses one of 3 authentication methods:
* OCI SDK config file and keys (~/.oci/config)
* [when used by root] a designated user's OCI SDK config
* Instance Principals

By default, OCISession will try them in the above order and retuns an OCISession
object when one of them succeeds.

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

The OCISession class is the main entry point of oci_api.  You only need one
OCISession object (though it is OK to create more than one).  When you create
an OCISession object, oci_api reads the OCI config file (by default:
~/.oci/config) and attempts to authenticate using OCI Python APIs.
You can specify a non-default configuration file and non-default configuration
profile:

```python
import oci_utils.oci_api

sess = oci_utils.oci_api.OCISession(config_file='/path/to/file',
                                    config_profile='PROFILE',
				    auth_method=None)
```

Valid values for auth_method are:
 * oci_utils.oci_api.AUTO = choose a method that works
 * oci_utils.oci_api.DIRECT = use the OCI SDK config file
 * oci_utils.oci_api.PROXY = use a designated user's config files; the user is defined in the OCI config files and defaults to 'opc'
 * oci_utils.oci_api.IP = use instance principals


The OCISession object allows you to list or find various OCI artifacts.
Unless otherwise noted, these methods have an optional "refresh" argument,
which you can use to force refreshing the cached data.

The all_* methods return an empty list if no matching objects are found.
The get_* methods return None if no object with the given ID is found.

* all_compartments(): returns a list of OCICompartment objects

* all_subnets(): returns a list of OCISubnet objects.  All Subnets are
  returned from all Compartments that the user has access to.

* all_instances(): similarly to all_subnets(), returns the list of all
  OCIInstance objects from all Compartments that the user has access to.

* all_vcns(): same again for VCNs

* all_volumes(): same again for block storage OCIVolume objects

* find_compartments(display_name): returns a list of OCICompartment objects
  with a matching display name ("display_name" regular expression)

* find_instances(display_name): returns a list of OCIInstance objects with a
  display name matching the regular expression "display_name".

* find_volumes(display_name=None, iqn=None): returns all OCIVolume objects
  with a matching display name ("display_name" regular expression) or iSCSI
  IQN (exact match of "iqn").  You can specify either or both arguments.
  If both arguments are given, they both have to match.

* find_subnets(display_name): returns a list of OCISubnet object with a
  matching display name ("display_name" regular expression)

* get_compartment(compartment_id): returns an OCICompartment object with the
  given "compartment_id" OCID

* get_instance(instance_id): same again for Instances

* get_subnet(subnet_id): same again for Subnets

* get_volume(volume_id): same again for Volumes

* get_vnic(vnic_id): same again for VNICs

* this_compartment(): when run on an OCI Instance, return the OCICompartment
  object representing the Compartment that the Instance belongs to

* this_instance(): when run on an OCI Instance, return the OCIInstance
  object representing the Instance

* this_availability_domain(): when run on an OCI Instance, return the
  availability domain (str).  Note: this method has no "refresh" argument
  as the availability domain of the instance does not change.

* this_region(): when run on an OCI Instance, return the region code (str).
  Note: this method has no "refresh" argument as the region of the Instance
  does not change.

Other methods:

* create_volume(compartment_id, availability_domain, size,
  display_name=None, wait=True): create a new OCI Volume in the given
  compartment (specified with the "compartment_id" OCID), availability domain
  (str, "availability_domain" argument), size (int, in gigabytes),
  optional display name (str, "display_name" argument).  By default
  this method blocks until the volume is created and is available.  You can
  override this behaviour using the "wait=False" argument.

* get_compute_client(): returns an oci.core.compute_client.ComputeClient()
  object, which allows you to make API calls directly using the OCI identity
  established by the OCISession.

* get_network_client(): returns an
  oci.core.virtual_network_client.VirtualNetworkClient() object.

* get_block_storage_client(): return an
  oci.core.blockstorage_client.BlockstorageClient() object.

* get_object_storage_client(): return an
  oci.object_storage.object_storage_client.ObjectStorageClient() object.

## Class details

This section describes the methods of the various classes representing OCI
artifacts.  Each of these classes have the following methods:

* get_display_name(): returns the display name of the object
* get_compartment(): returns the OCICompartment object of the Compartment
  that the given object belongs to
* get_ocid(): returns the OCID of the object

Several of the methods of these classes have the same names as methods
in the OCISession class, for instance all_subnets() or all_volumes().
The general idea is that these methods return of list of Objects that
belong to the object you are running it on.  For example calling
all_volumes() on an OCICompartment object will return the volumes in that
Compartment only, while running all_volumes() on an OCIInstance object
returns the block storage Volumes attached to the given Instance.

Do not create instances of these classes directly, they are meant to
represent existing OCI artifacts.  Instantiating these classes does not
create a new OCI artifact.  Creating most of these OCI artifacts is not
currently supported by oci_api, but I am planning to add them.
Use the following methods for creating/destroying OCI artifacts:

* new Volume: OCISession.create_volume(), OCICompartment.create_volume(),
  OCIInstance.create_volume()

* new VNIC: OCIInstance.attach_vnic()

* new Private IPv4: OCIVNIC.add_private_ipv4()

* new Private IPv6: OCIVNIC.add_private_ipv6()

* delete Private IP: OCIPrivateIP.delete()


## Future Plans

* Managing Instances: start, stop, change name, etc
* Creating more kinds of OCI artifacts, e.g. Instances, Subnets
