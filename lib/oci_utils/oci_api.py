# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

""" High level wrapper around the OCI Python SDK.
"""

import logging
import os
import re
import oci as oci_sdk
from oci_utils import where_am_i
from . import metadata
from . import _configuration as OCIUtilsConfiguration
from . import OCI_RESOURCE_STATE
from .impl.auth_helper import OCIAuthProxy
from .impl.oci_resources import (OCICompartment, OCIInstance, OCIVolume, OCISubnet, OCIVNIC)

# authentication methods
DIRECT = 'direct'
PROXY = 'proxy'
IP = 'ip'
AUTO = 'auto'
NONE = 'None'


_logger = logging.getLogger('oci-utils.oci_api')

__all__ = ['OCISession']


class OCISession:
    """
    High level OCI Cloud API operations
    """
    def __init__(self, config_file='~/.oci/config', config_profile='DEFAULT', authentication_method=None):
        """
        OCISession initialisation.

        Parameters
        ----------
        config_file : str
            The oci configuration file.
        config_profile : str
            The oci profile.
        authentication_method : str
            The authentication method, [None | DIRECT | PROXY | AUTO | IP].

        Raises
        ------
        Exception
            if fails to authenticate.
        """

        assert authentication_method in (None, NONE, DIRECT, IP, PROXY, AUTO), 'Invalid auth method'

        self.config_file = config_file
        self.config_profile = config_profile
        self._identity_client = None
        self._compute_client = None
        self._network_client = None
        self._block_storage_client = None
        self._object_storage_client = None
        self._metadata = metadata.InstanceMetadata().refresh().get().get()
        self.oci_config = {}
        self.signer = None
        self.auth_method = NONE
        #
        # get auth method from oci-utils conf. default is auto (to find one)
        self.auth_method = self._get_auth_method(authentication_method)

        if self.auth_method == NONE:
            raise Exception('Failed to authenticate with the Oracle Cloud Infrastructure service')

        self.tenancy_ocid = self._get_tenancy_ocid()
        _logger.debug('Tenancy id used: %s', self.tenancy_ocid)

    def _get_tenancy_ocid(self):
        """
        Get the tenancy ocid, use compartment ocid if this fails.

        Returns
        -------
            str: the tenancy ocid
        """
        _logger.debug('%s', where_am_i())
        #
        # try the oci sdk config file
        if bool(self.oci_config):
            if 'tenancy' in self.oci_config:
                return self.oci_config['tenancy']
            _logger.debug('SDK config file exists but tenancy is missing')
        #
        # if oci sdk config file fails. try IP data
        if self.signer is not None:
            return self.signer.tenancy_id
        _logger.debug('Signer is missing tenancy')
        #
        # fall back to the instance's own compartment_id
        # We will only see the current compartment, but better than nothing
        if 'instance' in self._metadata:
            return self._metadata['instance']['compartmentId']
        # this means trouble
        _logger.debug('Failed to get tenancy and compartment ocid.')
        return None

    @staticmethod
    def _read_oci_config(fname, profile='DEFAULT'):
        """
        Read the OCI config file.

        Parameters
        ----------
        fname : str
            The OCI configuration file name.
            # the file name should be ~/<fname> ?
        profile : str
            The user profile.

        Returns
        -------
        dictionary
            The oci configuration.

        Raises
        ------
        Exception
            If the configuration file does not exist or is not readable.
        """
        _logger.debug('%s', where_am_i())
        full_fname = os.path.expanduser(fname)
        try:
            oci_config = oci_sdk.config.from_file(full_fname, profile)
            return oci_config
        except oci_sdk.exceptions.ConfigFileNotFound as e:
            _logger.debug("Unable to read OCI config file: %s", str(e))
            raise Exception('Unable to read OCI config file') from e

    def this_shape(self):
        """
        Returns the current shape.
        Returns:
        --------
          shape as with content of metadata as string
        """
        _logger.debug('%s', where_am_i())
        return self._metadata['instance']['shape']

    def _get_auth_method(self, authentication_method=None):
        """
        Determine how (or if) we can authenticate. If auth_method is
        provided, and is not AUTO then test if the given auth_method works.
        Return one of oci_api.DIRECT, oci_api.PROXY, oci_api.IP or
        oci_api.NONE (IP is instance principals).

        Parameters
        ----------
        authentication_method : [NONE | DIRECT | PROXY | AUTO | IP]
            if specified, the authentication method to be tested.

        Returns
        -------
        One of the oci_api.DIRECT, oci_api.PROXY, oci_api.IP or oci_api.NONE,
        the authentication method which passed or NONE.
            [NONE | DIRECT | PROXY | AUTO | IP]
        """
        _logger.debug('%s', where_am_i())
        if authentication_method is None:
            auth_method = OCIUtilsConfiguration.get('auth', 'auth_method')
        else:
            auth_method = authentication_method

        _logger.debug('Authentication method retrieved from conf: %s', auth_method)

        # order matters
        _auth_mechanisms = {
            DIRECT: self._direct_authenticate,
            IP: self._ip_authenticate,
            PROXY: self._proxy_authenticate}

        if auth_method in _auth_mechanisms.keys():
            # user specified something, respect that choice
            try:
                _logger.debug('Trying %s auth', auth_method)
                _auth_mechanisms[auth_method]()
                _logger.debug('%s auth ok', auth_method)
                return auth_method
            except Exception as e:
                _logger.debug(' %s auth has failed: %s', auth_method, str(e))
                return NONE

        _logger.debug('Nothing specified trying to find an auth method')
        for method in _auth_mechanisms:
            try:
                _logger.debug('Trying %s auth', method)
                _auth_mechanisms[method]()
                _logger.debug('%s auth ok', method)
                return method
            except Exception as e:
                _logger.debug('%s auth has failed: %s', method, str(e))

        # no options left
        return NONE

    def _proxy_authenticate(self):
        """
        Use the auth helper to get config settings and keys
        Return True for success, False for failure

        Returns
        -------
        None

        Raises
        ------
        Exception
            The authentication using direct mode is noit possible
        """
        _logger.debug('%s', where_am_i())
        if os.geteuid() != 0:
            raise Exception("Must be root to use Proxy authentication")

        sdk_user = OCIUtilsConfiguration.get('auth', 'oci_sdk_user')
        try:
            proxy = OCIAuthProxy(sdk_user)
            self.oci_config = proxy.get_config()
            self._identity_client = oci_sdk.identity.IdentityClient(self.oci_config)
        except Exception as e:
            _logger.debug("Proxy authentication failed: %s", str(e))
            raise Exception("Proxy authentication failed") from e

    def _direct_authenticate(self):
        """
        Authenticate with the OCI SDK.

        Returns
        -------
        None

        Raises
        ------
        Exception
            The authentication using direct mode is not possible
        """
        _logger.debug('%s', where_am_i())
        try:
            self.oci_config = self._read_oci_config(fname=self.config_file, profile=self.config_profile)
            self._identity_client = oci_sdk.identity.IdentityClient(self.oci_config)
        except Exception as e:
            _logger.debug('Direct authentication failed: %s', str(e))
            raise Exception("Direct authentication failed") from e

    def _ip_authenticate(self):
        """
        Authenticate with the OCI SDK using instance principal .

        Returns
        -------
        None

        Raises
        ------
        Exception
            If IP authentication fails.
        """
        _logger.debug('%s', where_am_i())
        try:
            self.signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
            self._identity_client = oci_sdk.identity.IdentityClient(config={}, signer=self.signer)
        except Exception as e:
            _logger.debug('Instance Principals authentication failed: %s', str(e))
            raise Exception('Instance Principals authentication failed') from e

    def all_compartments(self):
        """
        Return a list of OCICompartment objects.

        Returns
        -------
        list
            List of compartements.
        """
        _logger.debug('%s', where_am_i())
        _compartments = []
        try:
            compartments_data = oci_sdk.pagination.list_call_get_all_results(self._identity_client.list_compartments,
                                                                             compartment_id=self.tenancy_ocid).data
        except Exception as e:
            _logger.error('%s', e)
            return _compartments

        for c_data in compartments_data:
            _compartments.append(OCICompartment(session=self, compartment_data=c_data))
        return _compartments

    def find_compartments(self, display_name):
        """
        Return a list of OCICompartment-s with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
             A regular expression.

        Returns
        -------
        list
            A list of matching compartments.
        """
        dn_re = re.compile(display_name)
        compartments = []
        for comp in self.all_compartments():
            res = dn_re.search(comp.get_display_name())
            if res is not None:
                compartments.append(comp)
        return compartments

    def find_vcns(self, display_name):
        """
        Return a list of OCIVCN-s with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
             A regular expression.

        Returns
        -------
        list
            A list of matching vcn-s
        """
        _logger.debug('%s', where_am_i())
        dn_re = re.compile(display_name)
        vcns = []
        for vcn in self.all_vcns():
            res = dn_re.search(vcn.get_display_name())
            if res is not None:
                vcns.append(vcn)
        return vcns

    def get_compute_client(self):
        """
        Get a new compute client.

        Returns
        -------
            A instance of oci.core.ComputeClient
        """
        _logger.debug('%s', where_am_i())
        if self._compute_client is None:
            if self.signer is not None:
                self._compute_client = \
                    oci_sdk.core.compute_client.ComputeClient(config={}, signer=self.signer)
            else:
                self._compute_client = \
                    oci_sdk.core.compute_client.ComputeClient(config=self.oci_config)
        return self._compute_client

    def get_network_client(self):
        """
        Get a new network client.

        Returns
        -------
            A instance of oci.core.VirtualNetworkClient
        """
        _logger.debug('%s', where_am_i())
        if self._network_client is None:
            if self.signer is not None:
                self._network_client = \
                    oci_sdk.core.virtual_network_client.VirtualNetworkClient(config={}, signer=self.signer)
            else:
                self._network_client = \
                    oci_sdk.core.virtual_network_client.VirtualNetworkClient(config=self.oci_config)
        return self._network_client

    def get_block_storage_client(self):
        """
        Get a new block storage client.

        Returns
        -------
            A instance of oci.core.blockstorage_client.BlockStorageClient
        """
        _logger.debug('%s', where_am_i())
        if self._block_storage_client is None:
            if self.signer is not None:
                self._block_storage_client = \
                    oci_sdk.core.blockstorage_client.BlockstorageClient(config={}, signer=self.signer)
            else:
                self._block_storage_client = \
                    oci_sdk.core.blockstorage_client.BlockstorageClient(config=self.oci_config)
        return self._block_storage_client

    def get_object_storage_client(self):
        """
        Get a new object storage client.

        Returns
        -------
            An instance of oci.object_storage.object_storage_client.ObjectStorageClient.
        """
        _logger.debug('%s', where_am_i())
        if self._object_storage_client is None:
            if self.signer is not None:
                self._object_storage_client = \
                    oci_sdk.object_storage.object_storage_client.ObjectStorageClient(config=self.oci_config,
                                                                                     signer=self.signer)
            else:
                self._object_storage_client = \
                    oci_sdk.object_storage.object_storage_client.ObjectStorageClient(config=self.oci_config)
        return self._object_storage_client

    def all_instances(self):
        """
        Get all compartments instances across all compartments.

        Returns
        -------
        list
            List of OCIInstance object, can be empty
        """
        _logger.debug('%s', where_am_i())
        instances = []
        for compartment in self.all_compartments():
            comp_instances = compartment.all_instances()
            if comp_instances is not None:
                instances += comp_instances

        return instances

    def update_instance_metadata(self, instance_id=None, **kwargs):
        """
        Update the instance metadata.

        Parameters
        ----------
        instance_id : str
             The instance id (OCID).
        kwargs : dictionary
            The key-value list of new metadata data.

        Returns
        -------
        Oci_Metadata:
            Updated metadata.
        """
        _logger.debug('%s', where_am_i())
        if instance_id is None:
            try:
                instance_id = self._metadata['instance']['id']
            except Exception as e:
                _logger.error('No instance id. Please run inside an instance '
                              'or provide instance-id. - %s\n', str(e))
                return None
        if not kwargs:
            _logger.error('No set parameters are provided.\n')
            return None

        details = {}
        for key in OCIInstance.settable_field_type:
            if key in list(kwargs.keys()):
                details[key] = kwargs[key]

        if not details:
            _logger.error('Nothing needs to be set.\n')
            return None

        cc = self.get_compute_client()

        try:
            result = cc.update_instance(instance_id=instance_id, update_instance_details=details,).data
        except Exception as e:
            _logger.error('Failed to set metadata: %s. ', str(e))
            return None

        return OCIInstance(self, result).get_metadata()

    def find_instances(self, display_name):
        """
        Return a list of OCI instances with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
            A regular expression.
        Returns
        -------
        list
            The list of instances.
        """
        _logger.debug('%s', where_am_i())
        dn_re = re.compile(display_name)
        instances = []
        for instance in self.all_instances():
            res = dn_re.search(instance.get_display_name())
            if res is not None:
                instances.append(instance)
        return instances

    def find_volumes(self, display_name=None, iqn=None):
        """
        Return a list of OCIVolume-s with a matching display_name regexp
        and/or IQN.

        Parameters
        ----------
        display_name : str
            A regular expression.
        iqn : str
            An iSCSI qualified name.

        Returns
        -------
        list
            The list of matching volumes
        """
        _logger.debug('%s', where_am_i())
        if display_name is None and iqn is None:
            return []
        dn_re = None
        if display_name is not None:
            dn_re = re.compile(display_name)
        volumes = []
        for volume in self.all_volumes():
            if dn_re is not None:
                # check if display_name matches
                res = dn_re.search(volume.get_display_name())
                if res is None:
                    # no match
                    continue
            if iqn is not None:
                if volume.get_iqn() != iqn:
                    # iqn doesn't match
                    continue
            # all filter conditions match
            volumes.append(volume)
        return volumes

    def all_subnets(self):
        """
        Return a list of OCISubnet objects.
        Returns
        -------
        list
            A list of subnets.
        """
        _logger.debug('%s', where_am_i())
        subnets = []
        for compartment in self.all_compartments():
            comp_subnets = compartment.all_subnets()
            if comp_subnets is not None:
                subnets += comp_subnets
        return subnets

    def find_subnets(self, display_name):
        """
        Return a list of OCISubnet-s with matching the display_name regexp

        Parameters
        ----------
        display_name : str
            A regular expression.

        Returns
        -------
        list
            The list of matching subnets.
        """
        _logger.debug('%s', where_am_i())
        dn_re = re.compile(display_name)
        subnets = []
        for subnet in self.all_subnets():
            res = dn_re.search(subnet.get_display_name())
            if res is not None:
                subnets.append(subnet)
        return subnets

    def all_vcns(self):
        """
        Get all VCNs instances across all compartments

        Returns
        -------
        list
            list of OCIVCN object, can be empty
        """
        _logger.debug('%s', where_am_i())
        _vcns = []
        for compartment in self.all_compartments():
            _vcns.extend(compartment.all_vcns())

        return _vcns

    def all_volumes(self):
        """
        Get all volume instances across all compartments

        Returns
        -------
        list
            list of OCIVolume object, can be empty
        """
        _logger.debug('%s', where_am_i())
        volumes = []
        for compartment in self.all_compartments():
            comp_volumes = compartment.all_volumes()
            if comp_volumes is not None:
                volumes += comp_volumes
        return volumes

    def this_instance(self):
        """
        Get the current instance

        Returns
        -------
        OCIInstance
            The intance we are running on,or None if we cannot find
            information for it.
        Raises
        ------
        Exception : fetching instance has failed
        """
        _logger.debug('%s', where_am_i())
        try:
            my_instance_id = self._metadata['instance']['id']
        except Exception as e:
            _logger.error('Cannot find my instance ID: %s', e)
            return None
        try:
            my_instance = self.get_instance(instance_id=my_instance_id)
            return my_instance
        except Exception as e:
            _logger.debug('Failed to get this instance data: %s', str(e))
            return None

    def this_compartment(self):
        """
        Get the current compartment

        Returns
        -------
        OCICompartment
            A OCICompartment instance or None if no compartement
            information is found.
        """
        _logger.debug('%s', where_am_i())
        if self._metadata is None:
            _logger.warning('Metadata is None !')
            # TODO: should it severe error case instead ??
            return None
        try:
            my_compartment_id = self._metadata['instance']['compartmentId']
        except Exception as e:
            _logger.error('No compartment ID information in metadata: %s', str(e))
            return None

        return self.get_compartment(ocid=my_compartment_id)

    def this_availability_domain(self):
        """
        Get the availability domain

        Returns
        -------
        str
            The availability domain name or None if no information
            is found in metadata.
        """
        _logger.debug('%s', where_am_i())
        if self._metadata is None:
            # TODO: should it severe error case instead ??
            return None
        return self._metadata['instance']['availabilityDomain']

    def get_tenancy_ocid(self):
        """
        Get the OCID of the tenancy.

        Returns
        -------
        str
            The OCID.
        """
        _logger.debug('%s', where_am_i())
        return self.tenancy_ocid

    def this_region(self):
        """
        Get the current region of the instance.

        Returns
        -------
        str
            The region name or None if no information is found in metadata.
        """
        _logger.debug('%s', where_am_i())
        if self._metadata is None:
            _logger.warning('metadata is None !')
            # TODO: should it severe error case instead ??
            return None
        try:
            return self._metadata['instance']['region']
        except Exception as e:
            _logger.warning('No region information in metadata: %s', str(e))
            return None

    def get_instance(self, instance_id):
        """
        Get instance by ID

        Parameters
        ----------
        instance_id : str
            The ID of the wanted instance.

        Returns
        -------
        OCIInstance
            The OCI instance or None if it is not found.
        Raises
        ------
        Exception : fetching instance has failed
        """
        _logger.debug('%s', where_am_i())
        try:
            cc = self.get_compute_client()
            instance_data = cc.get_instance(instance_id=instance_id).data
            return OCIInstance(self, instance_data)
        except Exception as e:
            _logger.debug('Failed to fetch instance: %s. Check your connection and settings.', e)
            raise Exception('Failed to fetch instance [%s]' % instance_id) from e

    def get_subnet(self, subnet_id):
        """
        Get the subnet.

        Parameters
        ----------
        subnet_id: str
            The subnet id.

        Returns
        -------
            OCISubnet
            The subnet object or None if not found.
        """
        _logger.debug('%s', where_am_i())
        nc = self.get_network_client()
        try:
            sn_data = nc.get_subnet(subnet_id=subnet_id).data
            return OCISubnet(self, subnet_data=sn_data)
        except oci_sdk.exceptions.ServiceError:
            _logger.debug('failed to get subnet', exc_info=True)
            # return None

        return None

    def get_volume(self, volume_id):
        """
        Get an OCIVolume object representing the volume with the given OCID.

        Parameters
        ----------
        volume_id : str
            The volume id.

        Returns
        -------
        dict
            The volume object or None if not found.
        """
        _logger.debug('%s', where_am_i())
        bsc = self.get_block_storage_client()
        cc = self.get_compute_client()

        try:
            vol_data = bsc.get_volume(volume_id=volume_id).data
        except oci_sdk.exceptions.ServiceError:
            _logger.debug('Failed to get volume', exc_info=True)
            return None

        if OCI_RESOURCE_STATE[vol_data.lifecycle_state] == OCI_RESOURCE_STATE.TERMINATED:
            return None

        try:
            v_att_list = oci_sdk.pagination.list_call_get_all_results(cc.list_volume_attachments,
                                                                      compartment_id=vol_data.compartment_id,
                                                                      volume_id=vol_data.id).data
        except Exception:
            _logger.debug('Cannot find any attachments for this volume', exc_info=True)
            #
            #
            # return OCIVolume(self, volume_data=oci_sdk.util.to_dict(vol_data))
            return OCIVolume(self, volume_data=vol_data)

        # find the latest attachment entry for this volume
        v_att_data = None
        for v_att in v_att_list:
            if v_att_data is None:
                v_att_data = v_att
                continue
            if v_att.time_created > v_att_data.time_created:
                v_att_data = v_att
        # attachment_data=oci_sdk.util.to_dict(v_att_data))
        return OCIVolume(self, volume_data=vol_data, attachment_data=v_att_data)

    def get_compartment(self, **kargs):
        """
        Get compartment data.

        Parameters
        ----------
        kargs: argument dictionary, only ocid for now.

        Returns
        -------
            OCICompartment
        """
        _logger.debug('%s', where_am_i())
        if 'ocid' not in kargs:
            # for now make it mandatory
            raise Exception('ocid must be provided')

        try:
            c_data = self._identity_client.get_compartment(compartment_id=kargs['ocid']).data
            return OCICompartment(session=self, compartment_data=c_data)
        except Exception as e:
            if hasattr(e, 'code'):
                _logger.debug('Error getting compartment %s: %s', kargs['ocid'], getattr(e, 'code'))
                _logger.error('Error getting compartment: %s', getattr(e, 'code'))
            else:
                _logger.debug('Failed to get compartment %s: %s', kargs['ocid'], str(e))
                _logger.error('Failed to get compartment: %s', str(e))
            return None

    def get_vcn(self, vcn_id):
        """
        Get VCN by ID.

        Parameters
        ----------
        vcn_id : str
            The ID of the wanted vcn.

        Returns
        -------
        OCIVCN
            The OCI VCN  or None if it is not found.
        """
        _logger.debug('%s', where_am_i())
        for c in self.all_vcns():
            if c.get_ocid() == vcn_id:
                return c
        return None

    def get_vnic(self, vnic_id):
        """
        Get VNIC by ID.

        Parameters
        ----------
        vnic_id : str
            The ID of the wanted vnic.

        Returns
        -------
        OCIVNIC
            The OCI VNIC  or None if it is not found.
            The returned VNIC does not have any attachment information
        """
        _logger.debug('%s', where_am_i())
        nc = self.get_network_client()
        cc = self.get_compute_client()
        all_comps = self.all_compartments()
        for comp in all_comps:
            try:
                comp_id = comp.get_compartment_id()
                vnic_atts = oci_sdk.pagination.list_call_get_all_results(cc.list_vnic_attachments,
                                                                         compartment_id=comp_id)
                for vnic_att in vnic_atts.data:
                    try:
                        vnic_dat = nc.get_vnic(vnic_att.vnic_id).data
                        if vnic_id == vnic_dat.id:
                            return OCIVNIC(self, vnic_data=vnic_dat, attachment_data=vnic_att)
                    except Exception as e:
                        if hasattr(e, 'code'):
                            _logger.debug('Failed to collect vnic data for %s: %s',
                                          vnic_att.vnic_id,
                                          getattr(e, 'code'))
                            pass
            except Exception as e:
                if hasattr(e, 'code'):
                    _logger.debug('Failed to collect compartment data for %s: %s', comp_id, getattr(e, 'code'))
                    pass
        _logger.debug('Failed to fetch vnic: %s', vnic_id)
        raise Exception('Failed to fetch VNIC [%s]' % vnic_id)

    def create_volume(self, compartment_id, availability_domain, size, display_name=None, wait=True):
        """
        Create a new OCI Storage Volume in the given compartment and
        availability_domain, of the given size (GBs, >=50), and with
        the given display_name.

        Parameters
        ----------
        compartment_id : str
            The compartment id.
        availability_domain : str
            The availability domain.
        size : int
            The size in GB.
        display_name : str
            The display name.
        wait : bool
            Flag for waiting on completion if set.

        Returns
        -------
            An OCI Volume object.

        Raises
        ------
        Exception
            If the creation of the volume fails for any reason.
        """
        _logger.debug('%s', where_am_i())
        bsc = self.get_block_storage_client()
        cvds = oci_sdk.core.models.CreateVolumeDetails(availability_domain=availability_domain,
                                                       compartment_id=compartment_id,
                                                       size_in_gbs=size,
                                                       display_name=display_name)
        try:
            vol_data = bsc.create_volume(create_volume_details=cvds).data
            if wait:
                get_vol_state = bsc.get_volume(volume_id=vol_data.id)
                oci_sdk.wait_until(bsc, get_vol_state, 'lifecycle_state', 'AVAILABLE')
            ocivol = OCIVolume(self, vol_data)
            return ocivol
        except oci_sdk.exceptions.ServiceError as e:
            raise Exception('Failed to create volume') from e
