# OCI Utilities

Instances created using Oracle-Provided Images based on Oracle Linux include a pre-installed set of utilities that are designed
to make it easier to work with Oracle Linux images. 


These utilities consist of a service component and related command line tools that can help with managing
- block volumes (attach, remove, and automatic discovery);
- secondary VNIC configuration;
- discovering the public IP address of an instance;
- retrieving instance metadata;
- sending notification messages.

The following list summarizes the components that are included in the OCI utilities.

- `ocid` The service component of oci-utils. This normally runs as a daemon started via systemd. This service scans for changes in the iSCSI and VNIC device configurations and caches the OCI metadata and public IP address of the instance.
- `oci-growfs` Expands the root filesystem of the instance to its configured size.
- `oci-iscsi-config` Used to display and configure iSCSI devices attached to a compute instance.
- `oci-metadata` Displays metadata for the compute instance.
- `oci-network-config` Lists or configures virtual network interface cards (VNICs) attached to the Compute instance. 
- `oci-network-inspector` Displays a detailed report for a given compartment or network.
- `oci-public-ip` Displays the public IP address of the current system in either human-readable or JSON format.
- `oci-notify` Sends a message to an OCI notification service.

For usage details, see the [OCI Utilities section of the Oracle Cloud Infrastructure documentation](https://docs.oracle.com/en-us/iaas/Content/Compute/References/ociutilities.htm).