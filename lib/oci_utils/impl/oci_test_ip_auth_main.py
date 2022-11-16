#
# Copyright (c) 2021, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import sys
import traceback
import urllib
try:
    import oci as oci_sdk
except ImportError as e:
    print('OCI SDK is not installed: %s.' % str(e))
    sys.exit(1)


def get_instance_id():
    """
    Get the ocid of this instance from the metadata.

    Returns
    -------
        str: the instance ocid
    """
    url = 'http://169.254.169.254/opc/v2/instance/id'
    try:
        req = urllib.request.Request(url=url)
        req.add_header('Authorization', 'Bearer Oracle')
        response = urllib.request.urlopen(req)
        instance_ocid = response.readline().decode('utf-8')
        print('--- %-35s: %s ---' % ('This instance instance_id', instance_ocid))
        return instance_ocid
    except Exception as e:
        print('Failed to collect instance_id: %s' % str(e))
        sys.exit(1)


def get_compartment_id():
    """
    Get the ocid of the current compartment from the metadata.

    Returns
    -------
        str: the compartment ocid
    """
    url = 'http://169.254.169.254/opc/v2/instance/compartmentId'
    try:
        req = urllib.request.Request(url=url)
        req.add_header('Authorization', 'Bearer Oracle')
        response = urllib.request.urlopen(req)
        compartment_ocid = response.readline().decode('utf-8')
        print('--- %-35s: %s ---' % ('This compartment compartment_id', compartment_ocid))
        return compartment_ocid
    except Exception as e:
        print('Failed to collect compartment_id: %s' % str(e))
        sys.exit(1)


def test_collecting_instance_data(instance_ocid):
    """
    Test the collection of the instance data.

    Parameters
    ----------
    instance_ocid: str
        The instance ocid

    Returns
    -------
        instance.data on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        instance_data = compute_client.get_instance(instance_id=instance_ocid).data
        print('--- Successfully verified Instance Principal Authentication for collecting instance data on %s. ---'
              % instance_data.display_name)
        return instance_data
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the instance data '
              'with Instance Principal Authentication using OCI SDK only. Verify the configuration or switch to '
              'Direct Authentication.\n')
        print('Exception: %s' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_compartments_data():
    """
    Test the collection of the compartments data.

    Returns
    -------
        compartments.data on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        identity_client = oci_sdk.identity.IdentityClient(config={}, signer=signer)
        compartments_data = oci_sdk.pagination.list_call_get_all_results(identity_client.list_compartments,
                                                                         compartment_id=signer.tenancy_id).data
        print('--- Successfully verified Instance Principal Authentication for collecting compartments data. '
              'Found %d compartment(s). ---' % len(compartments_data))
        return compartments_data
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the compartments data '
              'with Instance Principal Authentication using OCI SDK only. Verify the configuration or switch '
              'to Direct Authentication.\n')
        print('Exception: %s' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_instances_data(compartment_ocid):
    """
    Test the collection of the instances list.

    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.

    Returns
    -------
        instances list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        list_instances_data = compute_client.list_instances(compartment_id=compartment_ocid).data
        print('--- Successfully verified Instance Principal Authentication for collecting instances data. '
              'Found %d instance(s). ---' % len(list_instances_data))
        return list_instances_data
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the instances list data '
              'with Instance Principal Authentication using OCI SDK only. Verify the configuration or switch to '
              'Direct Authentication.\n')
        print('Exception: %s' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_all_volumes_data(compartment_id):
    """
    Test the collection of the data of all volumes in the compartment.

    Parameters
    ----------
    compartment_id: str
        The compartment id.

    Returns
    -------
        volumes list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        block_storage_client = oci_sdk.core.blockstorage_client.BlockstorageClient(config={}, signer=signer)
        block_storage_data = oci_sdk.pagination.list_call_get_all_results(block_storage_client.list_volumes,
                                                                          compartment_id=compartment_id).data
        print('--- Successfully verified Instance Principal Authentication for collecting all volumes data. '
              'Found %d volume(s).' % len(block_storage_data))
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the all volumes data '
              'with Instance Principal Authentication using OCI SDK only. Verify the configuration or switch to '
              'Direct Authentication.\n')
        print('Exception: %s' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_attached_volume_data(compartment_ocid, instance_ocid, instance_name):
    """
    Test the collection of the data on attached volumes.
    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.
    instance_ocid: str
        The instance ocid
    instance_name: str
        The instance display name

    Returns
    -------
        attached volumes list on success, False otherwise
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        v_att_list = oci_sdk.pagination.list_call_get_all_results(compute_client.list_volume_attachments,
                                                                  compartment_id=compartment_ocid,
                                                                  instance_id=instance_ocid).data

        print('--- Successfully verified Instance Principal Authentication for collecting attached volumes data on %s. '
              'Found %d attached volumes. ---' % (instance_name, len(v_att_list)))
        return v_att_list
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting attached volumes data '
              'with Instance Principal Authentication using OCI SDK only. Verify the configuration or switch to '
              'Direct Authentication.\n')
        print('Exception: %s' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_notification_topics(compartment_ocid, instance_name):
    """
    Test the listing of available notification topics.

    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.
    instance_name: str
        The instance display name .

    Returns
    -------
        notification topic list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        ons_control_client = oci_sdk.ons.NotificationControlPlaneClient(config={}, signer=signer)
        topic_list = ons_control_client.list_topics(compartment_id=compartment_ocid).data
        print('--- Successfully verified Instance Principal Authentication for collecting notification '
              'topics data on %s. Found %d topics. ---' % (instance_name, len(topic_list)))
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting notification service topics '
              'with Instance Principal Authentication using OCI SDK only: %s\nVerify the configuration or switch to '
              'Direct Authentication.\n' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_vcns_data(compartment_id):
    """
    Test the listing of vcns.

    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.

    Returns
    -------
        vnc list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        network_client = oci_sdk.core.virtual_network_client.VirtualNetworkClient(config={}, signer=signer)
        vcns_list = oci_sdk.pagination.list_call_get_all_results(network_client.list_vcns,
                                                                 compartment_id=compartment_id).data
        print('--- Successfully verified Instance Principal Authentication for collecting vcn list. '
              'Found %d vcn(s). ---' % len(vcns_list))
        return vcns_list
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the vcns '
              'with Instance Principal Authentication using OCI SDK only: %s\nVerify the configuration or switch to '
              'Direct Authentication.\n' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_subnets_data(compartment_id):
    """
    Test the listing of vcns.

    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.

    Returns
    -------
        vnc list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        network_client = oci_sdk.core.virtual_network_client.VirtualNetworkClient(config={}, signer=signer)
        subnet_list = oci_sdk.pagination.list_call_get_all_results(network_client.list_subnets,
                                                                   compartment_id=compartment_id).data
        print('--- Successfully verified Instance Principal Authentication for collecting subnets list. '
              'Found %d subnet(s). ---' % len(subnet_list))
        return subnet_list
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the subnet list '
              'with Instance Principal Authentication using OCI SDK only: %s\nVerify the configuration or switch to '
              'Direct Authentication.\n' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def test_collecting_vnics_data(compartment_id):
    """
    Test the listing of vcns.

    Parameters
    ----------
    compartment_ocid: str
        The compartment ocid.

    Returns
    -------
        subnet list on success, False otherwise.
    """
    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        vnics_list = oci_sdk.pagination.list_call_get_all_results(compute_client.list_vnic_attachments,
                                                                  compartment_id=compartment_id).data
        print('--- Successfully verified Instance Principal Authentication for collecting the vnic list. '
              'Found %d vnics(s). ---' % len(vnics_list))
        return vnics_list
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly for collecting the vnic list '
              'with Instance Principal Authentication using OCI SDK only: %s\nVerify the configuration or switch to '
              'Direct Authentication.\n' % str(e))
        # traceback.print_exception(*sys.exc_info())
    return False


def main():
    """
    Test if Instance Principal Authentication is configured correctly.

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    title = 'Instance Principal Authentication tests.'
    print('\n%s\n%s\n' % (title, len(title)*'-'))
    # the instance id
    instance_id = get_instance_id()
    # the compartment id
    compartment_id = get_compartment_id()
    #
    print('')
    #
    # test the instance data collection
    instance_info = test_collecting_instance_data(instance_id)
    display_name = instance_info.display_name if instance_info else 'this instance'
    #
    # test the listing of the compartments in the tenancy.
    _ = test_collecting_compartments_data()
    #
    # test the listing of the instances in the compartment.
    _ = test_collecting_instances_data(compartment_ocid=compartment_id)
    #
    # test the listing of all volumes in the tenancy.
    _ = test_collecting_all_volumes_data(compartment_id)
    #
    # test the attached volume data collection.
    _ = test_collecting_attached_volume_data(compartment_ocid=compartment_id,
                                             instance_ocid=instance_id,
                                             instance_name=display_name)
    #
    # test the listing of notification topics.
    _ = test_collecting_notification_topics(compartment_ocid=compartment_id,
                                            instance_name=display_name)
    #
    # test the listing of vcns in the compartment
    _ = test_collecting_vcns_data(compartment_id)
    #
    # test the listing of all subnets in the compartment.
    _ = test_collecting_subnets_data(compartment_id)
    #
    # test the listing of all vnics in the compartment.
    _ = test_collecting_vnics_data(compartment_id)


if __name__ == "__main__":
    sys.exit(main())
