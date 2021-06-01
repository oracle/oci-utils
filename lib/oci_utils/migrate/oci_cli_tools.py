# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

""" Module to handle oci-cli commands.
"""
import json
import logging

from oci_utils.migrate import console_msg
from oci_utils.migrate import pause_msg
from oci_utils.migrate import system_tools
from oci_utils.migrate.exception import OciMigrateException

_logger = logging.getLogger('oci-utils.oci-cli-utils')


def bucket_exists(bucket_name):
    """
    Verify if bucket_name exits.

    Parameters
    ----------
    bucket_name: str
        The bucket_name.

    Returns
    -------
        dict: The bucket on success, raise an exception otherwise
    """
    cmd = ['oci', 'os', 'object', 'list', '--all', '--bucket-name', bucket_name]
    _logger.debug('__ Running %s.', cmd)
    pause_msg(cmd)
    try:
        bucket_result = json.loads(system_tools.run_popen_cmd(cmd)['output'].decode('utf-8'))
        _logger.debug('Result: \n%s', bucket_result)
        return bucket_result
    except Exception as e:
        _logger.debug('Bucket %s does not exists or the authorisation is missing: %s.', bucket_name, str(e))
        raise OciMigrateException('Bucket %s does not exists or the authorisation is missing:' % bucket_name) from e


def display_name_exists(display_name, compartment_id):
    """
    Verify if the image with display_name exist in compartment.

    Parameters
    ----------
    display_name: str
        The display name.
    compartment_id: str
        The ocid of the compartment.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Verify if %s exists in compartment %s', display_name, compartment_id)
    cmd = ['oci', 'compute', 'image', 'list',
           '--compartment-id', '%s' % compartment_id,
           '--display-name', '%s' % display_name]
    object_status = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8')
    if bool(object_status):
        _logger.debug('Object %s is present in %s', display_name, compartment_id)
        return True
    _logger.debug('Object %s is not present in %s', display_name, compartment_id)
    return False


def find_compartment_id(compartment, compartment_dict):
    """
    Find the compartment ocid for compartment in the compartment dictinary.

    Parameters
    ----------
    compartment: str
        The compartment name.
    compartment_dict: dict
        The dictionary containing data for all? compartments in this tenancy.

    Returns
    -------
        str: the ocid of the compartment on success, raises an exception
             on failure.
    """
    _logger.debug('__ Looking for the ocid of compartment %s', compartment)
    for _, v in list(compartment_dict.items()):
        for x in v:
            if x['name'] == compartment:
                compartment_data = x
                console_msg(msg='Compartment: %s' % compartment_data['name'])
                compartment_id = compartment_data['id']
                return compartment_id
    raise OciMigrateException('Failed to find the ocid for %s' % compartment)


def get_lifecycle_state(display_name, compartment_id):
    """
    Collect the lifecycle state of on object in a compartment.

    Parameters
    ----------
    display_name: str
        The object name.
    compartment_id: str
        The compartment ocid.

    Returns
    -------
        str: the lifecycle state.
    """
    _logger.debug('__ Retrieving the lifecycle state of %s', display_name)
    cmd = ['oci', 'compute', 'image', 'list',
           '--compartment-id', '%s' % compartment_id,
           '--display-name', '%s' % display_name]
    try:
        object_list = json.loads(system_tools.run_popen_cmd(cmd)['output'].decode('utf-8'))
        for object_x in object_list['data']:
            if object_x['display-name'] == display_name:
                return object_x['lifecycle-state']

            _logger.debug('object %s not found.', display_name)
            return None
    except Exception as e:
        raise OciMigrateException('Failed to collect the compute image list:') from e


def get_os_namespace():
    """
    Collect the object storage namespace name.

    Returns
    -------
       str: object storage namespace name
       raises an exception on failure.
    """
    _logger.debug('__ Collect the object storage namespace name.')
    cmd = ['oci', 'os', 'ns', 'get']
    try:
        ns_dict = json.loads(system_tools.run_popen_cmd(cmd)['output'].decode('utf-8'))
        return ns_dict['data']
    except Exception as e:
        raise OciMigrateException('Failed to collect object storage namespace name:') from e


def get_tenancy_data(tenancy):
    """
    Collect the compartment data for a tenancy.

    Parameters
    ----------
    tenancy: str
        The tenancy ocid

    Returns
    -------
        dict: a dictionary with the data of all compartments in this tenancy.
        raises an exception on failure.
    """
    _logger.debug('__ Collecting compartment data for tenancy %s', tenancy)
    cmd = ['oci', 'iam', 'compartment', 'list', '-c', '%s' % tenancy, '--all']
    _logger.debug('Running %s', cmd)
    try:
        return json.loads(system_tools.run_popen_cmd(cmd)['output'].decode('utf-8'))
    except Exception as e:
        raise OciMigrateException('Failed to collect compartment data for tenancy %s:' % tenancy) from e


def import_image(image_name, display_name, compartment_id, os_namespace, os_name, launch_mode):
    """
    Import an os image from object storage in the custom images repository from the OCI.

    Parameters
    ----------
    image_name: str
        The name of the image in the object storage.
    display_name: str
        The name the image will be stored in the custom images repository.
    compartment_id: str
        The ocid of the compartment the image will be stored.
    os_namespace: str
        The name of the object storage namespace used.
    os_name: str
        The object storage name.
    launch_mode: str
        The mode the instance created from the custom image will be started.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    # _logger.debug('__ Importing image %s to %s as %s'
    #              % (image_name, compartment_id, display_name))
    cmd = ['oci', 'compute', 'image', 'import', 'from-object', '--bucket-name',
           '%s' % os_name, '--compartment-id', '%s' % compartment_id,
           '--name', '%s' % image_name, '--namespace', '%s' % os_namespace,
           '--launch-mode', launch_mode, '--display-name', '%s' % display_name]
    _logger.debug('__ Running %s', cmd)
    try:
        _ = system_tools.run_popen_cmd(cmd)['output']
        _logger.debug('Successfully started import of %s', image_name)
        return True
    except Exception as e:
        raise OciMigrateException('Failed to start import of %s:' % image_name) from e


def object_exists(bucket, object_name):
    """
    Verify if the object object_name already exists in the object storage.

    Parameters
    ----------
    bucket: dict
        The bucket.
    object_name: str
        The object name.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('__ Testing if %s already exists in %s.', object_name, bucket)
    bucket_data = bucket
    _logger.debug('Result: \n%s', bucket_data)
    if 'data' in bucket_data:
        for res in bucket_data['data']:
            if str(res['name']) == object_name:
                _logger.debug('%s found', object_name)
                return True

            _logger.debug('%s not found', object_name)
    else:
        _logger.debug('Bucket %s is empty.', bucket)
    return False


def upload_image(imgname, bucket_name, ociname):
    """
    Upload the validated and updated image imgname to the OCI object storage
    bucket_name as ociname.

    Parameters
    ----------
    imgname: str
        The on-premise custom image.
    bucket_name: str
        The OCI object storage name.
    ociname:
        The OCI image name.

    Returns
    -------
        bool: True on success, raises an exception otherwise.
    """
    cmd = ['oci', 'os', 'object', 'put',
           '--bucket-name', bucket_name,
           '--file', imgname,
           '--name', ociname,
           '--part-size', '100',
           '--parallel-upload-count', '6']
    _logger.debug('__ Running %s', cmd)
    pause_msg(cmd)
    try:
        upload_result = system_tools.run_popen_cmd(cmd)['output'].decode('utf-8')
        _logger.debug('Successfully uploaded %s to %s as %s: %s.', imgname, bucket_name, ociname, upload_result)
        return True
    except Exception as e:
        _logger.critical('   Failed to upload %s to object storage %s as %s: %s.',
                         imgname, bucket_name, ociname, str(e))
        raise OciMigrateException('Failed to upload %s to object storage %s as %s:'
                                  % (imgname, bucket_name, ociname)) from e
