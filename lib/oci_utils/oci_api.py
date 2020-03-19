# oci-utils
#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

""" High level wrapper around the OCI Python SDK.
"""

import logging
import os
import re
from time import sleep

import oci_utils
from oci_utils import metadata
from . import _configuration as OCIUtilsConfiguration
from . import OCI_RESOURCE_STATE
from .exceptions import OCISDKError
from .impl import lock_thread, release_thread
from .impl.auth_helper import OCIAuthProxy
from .impl.oci_resources import (OCICompartment, OCIInstance, OCIVolume, OCISubnet)

HAVE_OCI_SDK = True
try:
    import oci as oci_sdk
except ImportError:
    HAVE_OCI_SDK = False

# authentication methods
DIRECT = 'direct'
PROXY = 'proxy'
IP = 'ip'
AUTO = 'auto'
NONE = 'None'


_logger = logging.getLogger('oci-utils.oci_api')

__all__ = ['OCISession']


class OCISession(object):
    """
    High level OCI Cloud API operations
    """

    def __init__(self, config_file='~/.oci/config', config_profile='DEFAULT',
                 auth_method=None, debug=False):
        """
        OCISession initialisation.

        Parameters
        ----------
        config_file : str
            The oci configuration file.
        config_profile : str
            The oci profile.
        auth_method : str
            The authentication method, [None | DIRECT | PROXY | AUTO | IP].
        debug : bool
            The debug flag
            # --GT-- not used, left in to avoid class initialisation failure.

        Raises
        ------
        OCISDKError
            If there is no OCI SDK,
            if fails to authenticate.
        """

        global HAVE_OCI_SDK
        if not HAVE_OCI_SDK:
            raise OCISDKError('Package python-oci-sdk not installed')

        self.config_file = config_file
        self.config_profile = config_profile
        self._compartments = None
        self._instances = None
        # max time spent waiting for the sdk thread lock
        self._sdk_lock_timeout = int(60)
        self._vcns = None
        self._subnets = None
        self._volumes = None
        self._identity_client = None
        self._compute_client = None
        self._network_client = None
        self._block_storage_client = None
        self._object_storage_client = None

        try:
            self._metadata = oci_utils.metadata.InstanceMetadata(
                get_public_ip=False).get(silent=True).get()
        except Exception:
            self._metadata = None

        self.oci_config = {}
        self.signer = None
        self.auth_method = auth_method
        self.auth_status = ""
        try:
            # see if auth_method was set in oci-utils.conf
            self.auth_method = OCIUtilsConfiguration.get('auth', 'auth_method')
        except Exception:
            if self.auth_method is None:
                self.auth_method = AUTO
        if not self._metadata:
            # code is running outside OCI, must have direct auth:
            self.auth_method = self._get_auth_method(auth_method=DIRECT)
        else:
            self.auth_method = self._get_auth_method(self.auth_method)
        if self.auth_method == NONE:
            if self.auth_status:
                raise OCISDKError(self.auth_status)
            raise OCISDKError('Failed to authenticate with the Oracle Cloud '
                              'Infrastructure service')

        self.tenancy_ocid = None
        if 'tenancy' in self.oci_config:
            # DIRECT or PROXY auth
            self.tenancy_ocid = self.oci_config['tenancy']
        elif self.signer is not None:
            # IP auth
            self.tenancy_ocid = self.signer.tenancy_id
        elif 'instance' in self._metadata:
            # fall back to the instance's own compartment_id
            # We will only see the current compartment, but better than nothing
            self.tenancy_ocid = self._metadata['instance']['compartmentId']

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
        OCISDKError
            If the configuration file does not exist or is not readable.
        """
        full_fname = os.path.expanduser(fname)
        if os.path.exists(full_fname):
            try:
                oci_config = oci_sdk.config.from_file(full_fname, profile)
                return oci_config
            except oci_sdk.exceptions.ConfigFileNotFound as e:
                raise OCISDKError("Unable to read OCI config file: %s" % e)
        else:
            raise OCISDKError("Config file %s not found" % full_fname)

    def this_shape(self):
        try:
            return self._metadata['instance']['shape']
        except Exception:
            return None

    def set_sdk_call_timeout(self, timeout):
        """
        Set the timeout for calls to OCI SDK
        the timeout is used as a timeout to acquire the lock protecting the
        OCI sdk.

        Parameters
        ----------
        timeout : int
            The timeout value, in seconds.

        Returns
        -------
            No return value

        Raises
        ------
        OCISDKError
            If timeout is less or equal to 0.
        ValueError
            If the given timeout cannot be converted ot int.
        """
        if timeout is None or int(timeout) < 0:
            raise OCISDKError("Invalid value for timeout in sdk_call()")
        self._sdk_lock_timeout = int(timeout)

    def sdk_call(self, client_func, *args, **kwargs):
        """
        Make an SDK call in a thread-safe way. Give up acquiring the
        thread lock after timeout seconds.

        Parameters
        ----------
        client_func : func
            The SDK function call.
        args :
            Non-keyworded function call arguments.
        kwargs :
            Keyworded function call arguments.

        Returns
        -------
            The function return value.

        Raises
        ------
        OCISDKError
            If the timeout is reached.
        """
        lock_thread(timeout=self._sdk_lock_timeout)
        # for loggin purposes
        call_name = str(client_func)
        try:
            call_name = client_func.__name__
        except Exception:
            pass
        try:
            result = client_func(*args, **kwargs)
            next_res = result
            while hasattr(next_res, 'data') and next_res.has_next_page:
                next_res = client_func(*args, page=next_res.next_page, **kwargs)
                result.data.extend(next_res.data)
        except Exception as e:
            _logger.debug("API call %s failed: %s" % (call_name, e))
            raise
        finally:
            release_thread()

        return result

    def _get_auth_method(self, auth_method=None):
        """
        Determine how (or if) we can authenticate. If auth_method is
        provided, and is not AUTO then test if the given auth_method works.
        Return one of oci_api.DIRECT, oci_api.PROXY, oci_api.IP or
        oci_api.NONE (IP is instance principals).

        Parameters
        ----------
        auth_method : [NONE | DIRECT | PROXY | AUTO | IP]
            The authentication method to be tested.

        Returns
        -------
        One of the oci_api.DIRECT, oci_api.PROXY, oci_api.IP or oci_api.NONE,
        the authentication method which passed or NONE.
            [NONE | DIRECT | PROXY | AUTO | IP]
        """
        if auth_method is not None:
            # testing a specific auth method
            if auth_method == DIRECT:
                if self._direct_authenticate():
                    return DIRECT
                else:
                    return NONE
            elif auth_method == PROXY:
                if self._proxy_authenticate():
                    return PROXY
                else:
                    return NONE
            elif auth_method == IP:
                if self._ip_authenticate():
                    return IP
                else:
                    return NONE

        # Try the direct method first
        try:
            if self._direct_authenticate():
                return DIRECT
        except Exception:
            # ignore any errors and try a different method
            pass

        # If we are root, we can try proxy call through the oci_sdk_user user
        if os.geteuid() == 0:
            try:
                if self._proxy_authenticate():
                    return PROXY
            except Exception:
                # ignore any errors and try a different method
                pass

        # finally, try instance principals
        try:
            if self._ip_authenticate():
                return IP
        except Exception:
            pass

        # no options left
        return NONE

    def _proxy_authenticate(self):
        """
        Use the auth helper to get config settings and keys
        Return True for success, False for failure

        Returns
        -------
        bool
            True if proxy authentication passes, False otherwise.
        """
        sdk_user = OCIUtilsConfiguration.get('auth', 'oci_sdk_user')
        try:
            proxy = OCIAuthProxy(sdk_user)
            self.oci_config = proxy.get_config()
        except Exception as e:
            self.auth_status += "Authentication as user %s failed: %s\n" \
                                % (sdk_user, e)
            _logger.debug('Proxy auth failed: %s' % e)
            return False
        try:
            self._identity_client = self.sdk_call(
                oci_sdk.identity.IdentityClient,
                self.oci_config)
        except Exception as e:
            self.auth_status += "Cannot create identity client as user %s\n" \
                                % sdk_user
            _logger.debug('ID client with proxy auth failed: %s' % e)
            return False
        self.auth_status += "Authentication as user %s succeeded\n" % sdk_user
        return True

    def _direct_authenticate(self):
        """
        Authenticate with the OCI SDK.

        Returns
        -------
        bool
            True for success, False for failure.

        Raises
        ------
        OCISDKError
            The authentication appears to work but API calls fail
            (indicates misconfiguration).
        """
        try:
            self.oci_config = self._read_oci_config(fname=self.config_file,
                                                    profile=self.config_profile)
        except Exception as e:
            self.auth_status += "Config file authentication failed: %s\n" % e
            _logger.debug('Cannot read oci config file: %s' % e)
            return False

        try:
            self._identity_client = self.sdk_call(
                oci_sdk.identity.IdentityClient,
                self.oci_config)
            self.auth_status += "Config file (direct) authentication " \
                                "succeeded\n"
            return True
        except Exception as e:
            self.auth_status += "Cannot create identity client: %s\n" % e
            _logger.debug('Direct auth failed: %s' % e)
            return False

        # test that it works
        #
        # --GT-- unreachable code till end.
        # if not self._metadata:
        #     # not in an instance, return without test.
        #     return true

        # try:
        #     inst_id = self._metadata['instance']['id']
        #     cc = self.get_compute_client()
        #     inst = self.sdk_call(cc.get_instance, instance_id=inst_id)
        # except oci_sdk.exceptions.ServiceError as e:
        #     self.auth_status += "Cannot make OCI API calls: %s\n" % e
        #     raise OCISDKError('Cannot make OCI API calls: %s' % e.message)

        # self.auth_status += "Config file (direct) authentication succeeded\n"
        # return True

    def _ip_authenticate(self):
        """
        Authenticate with the OCI SDK.

        Returns
        -------
        bool
            True if the authentication succeeds, False otherwise.
        Raises
        ------
        OCISDKError
            If IP authentication fails.
        """
        self.signer = \
            oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        self._identity_client = self.sdk_call(
            oci_sdk.identity.IdentityClient,
            config={}, signer=self.signer)
        inst = None
        try:
            inst = self.this_instance()
        except Exception as e:
            self.auth_status += "Instance Principals authentication: %s\n" % e
            _logger.debug('IP auth failed: %s' % e)
            # reset compute client set by this_instance()
            self._compute_client = None
            return False
        if inst is not None:
            self.auth_status += "Instance Principals (IP) authentication " \
                                "succeeded\n"
            return True

        return False

    def all_compartments(self, refresh=False):
        """
        Return a list of OCICompartment objects.

        Parameters
        ----------
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            List of compartements.
        """
        if self._compartments is not None and not refresh:
            return self._compartments

        self._compartments = []
        try:
            compartments_data = oci_sdk.pagination.list_call_get_all_results(
                self._identity_client.list_compartments,
                compartment_id=self.tenancy_ocid).data
        except Exception as e:
            _logger.error('%s' % e)
            return self._compartments

        # compartments_data = self.identity_client.list_compartments(
        #    compartment_id=self.tenancy_ocid).data
        for c_data in compartments_data:
            self._compartments.append(
                OCICompartment(session=self, compartment_data=c_data))
        return self._compartments

    def find_compartments(self, display_name, refresh=False):
        """
        Return a list of OCICompartment-s with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
             A regular expression.
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            A list of matching compartments.
        """
        dn_re = re.compile(display_name)
        compartments = []
        for comp in self.all_compartments(refresh=refresh):
            res = dn_re.search(comp.get_display_name())
            if res is not None:
                compartments.append(comp)
        return compartments

    def find_vcns(self, display_name, refresh=False):
        """
        Return a list of OCIVCN-s with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
             A regular expression.
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            A list of matching vcn-s
        """
        dn_re = re.compile(display_name)
        vcns = []
        for vcn in self.all_vcns(refresh=refresh):
            res = dn_re.search(vcn.get_display_name())
            if res is not None:
                vcns.append(vcn)
        return vcns

    def all_subnets(self, refresh=False):
        """
        Return a list of OCISubnet objects.

        Parameters
        ----------
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            A list of subnets.
        """
        if self._subnets is not None and not refresh:
            return self._subnets

        subnets = []
        for compartment in self.all_compartments(refresh=refresh):
            comp_subnets = compartment.all_subnets()
            if comp_subnets is not None:
                subnets += comp_subnets
        self._subnets = subnets
        return subnets

    # TODO : developer of this method should add documentation
    def get_compute_client(self):
        """
        Get a new compute client.

        Returns
        -------
            The compute client.
        """
        if self._compute_client is None:
            if self.signer is not None:
                self._compute_client = \
                    oci_sdk.core.compute_client.ComputeClient(
                        config=self.oci_config, signer=self.signer)
            else:
                self._compute_client = \
                    oci_sdk.core.compute_client.ComputeClient(
                        config=self.oci_config)
        return self._compute_client

    # TODO : developer of this method should add documentation
    def get_network_client(self):
        """
        Get a new network client.

        Returns
        -------
            The network client.
        """
        if self._network_client is None:
            if self.signer is not None:
                self._network_client = \
                    oci_sdk.core.virtual_network_client.VirtualNetworkClient(
                        config=self.oci_config, signer=self.signer)
            else:
                self._network_client = \
                    oci_sdk.core.virtual_network_client.VirtualNetworkClient(
                        config=self.oci_config)
        return self._network_client

    # TODO : developer of this method should add documentation
    def get_block_storage_client(self):
        """
        Get a new block storage client.

        Returns
        -------
            The block storage client.
        """
        if self._block_storage_client is None:
            if self.signer is not None:
                self._block_storage_client = \
                    oci_sdk.core.blockstorage_client.BlockstorageClient(
                        config=self.oci_config, signer=self.signer)
            else:
                self._block_storage_client = \
                    oci_sdk.core.blockstorage_client.BlockstorageClient(
                        config=self.oci_config)
        return self._block_storage_client

    # TODO : developer of this method should add documentation
    def get_object_storage_client(self):
        """
        Get a new object storage client.

        Returns
        -------
            The new object storage client.
        """
        if self._object_storage_client is None:
            if self.signer is not None:
                self._object_storage_client = \
                    oci_sdk.object_storage.object_storage_client.\
                    ObjectStorageClient(
                        config=self.oci_config, signer=self.signer)
            else:
                self._object_storage_client = \
                    oci_sdk.object_storage.object_storage_client.\
                    ObjectStorageClient(
                        config=self.oci_config)
        return self._object_storage_client

    def all_instances(self, refresh=False):
        """Get all compartements intances across all compartments.
        Parameters
        ----------
        refresh : bool
            Flag, refresh the compartments and instances information if set.

        Returns
        -------
        list
            List of OCIInstance object, can be empty
        """
        if self._instances is not None and not refresh:
            return self._instances

        instances = []
        for compartment in self.all_compartments(refresh=refresh):
            comp_instances = compartment.all_instances()
            if comp_instances is not None:
                instances += comp_instances
        self._instances = instances
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
        if instance_id is None:
            try:
                instance_id = self._metadata['instance']['id']
            except Exception:
                _logger.error('No instance id. Please run inside an instance '
                              'or provide instance-id.\n')
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
            result = self.sdk_call(
                cc.update_instance, instance_id=instance_id,
                update_instance_details=details,).data
        except Exception as e:
            _logger.error('Failed to set metadata: %s. ' % e.message)
            return None

        return OCIInstance(self, result).get_metadata()

    def find_instances(self, display_name, refresh=False):
        """
        Return a list of OCI instances with a matching display_name regexp.

        Parameters
        ----------
        display_name : str
            A regular expression.
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            The list of instances.
        """
        dn_re = re.compile(display_name)
        instances = []
        for instance in self.all_instances(refresh=refresh):
            res = dn_re.search(instance.get_display_name())
            if res is not None:
                instances.append(instance)
        return instances

    def find_volumes(self, display_name=None,
                     iqn=None, refresh=False):
        """
        Return a list of OCIVolume-s with a matching display_name regexp
        and/or IQN.

        Parameters
        ----------
        display_name : str
            A regular expression.
        iqn : str
            An iSCSI qualified name.
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            The list of matching volumes
        """
        if display_name is None and iqn is None:
            return []
        dn_re = None
        if display_name is not None:
            dn_re = re.compile(display_name)
        volumes = []
        for volume in self.all_volumes(refresh=refresh):
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

    def find_subnets(self, display_name, refresh=False):
        """
        Return a list of OCISubnet-s with matching the display_name regexp

        Parameters
        ----------
        display_name : str
            A regular expression.
        refresh : bool
            The refresh flag.

        Returns
        -------
        list
            The list of matching subnets.
        """
        dn_re = re.compile(display_name)
        subnets = []
        for subnet in self.all_subnets(refresh=refresh):
            res = dn_re.search(subnet.get_display_name())
            if res is not None:
                subnets.append(subnet)
        return subnets

    def all_vcns(self, refresh=False):
        """Get all VCNs intances across all compartments
        Parameters
        ----------
        refresh : bool
            Flag, refresh compartments and VNCs information if set.

        Returns
        -------
        list
            list of OCIVCN object, can be empty
        """
        if self._vcns is not None and not refresh:
            return self._vcns

        self._vcns = []
        for compartment in self.all_compartments(refresh=refresh):
            self._vcns.extend(compartment.all_vcns())

        return self._vcns

    def all_volumes(self, refresh=False):
        """
        Get all volume intances across all compartments

        Parameters
        ----------
        refresh : bool
            Flag, refresh compartments and volumes information if set

        Returns
        -------
        list
            list of OCIVolume object, can be empty
        """
        if self._volumes is not None and not refresh:
            return self._volumes

        volumes = []
        for compartment in self.all_compartments(refresh=refresh):
            comp_volumes = compartment.all_volumes()
            if comp_volumes is not None:
                volumes += comp_volumes
        self._volumes = volumes
        return volumes

    def this_instance(self, refresh=False):
        """
        Get the current instance

        Parameters
        ----------
        refresh : bool, optional
            Flag, refresh  information if set.
        Returns
        -------
        OCIInstance
            The intance we are running on,or None if we cannot find
            information for it.
        """

        if self._metadata is None:
            _logger.warning('metadata is None !')
            return None
        try:
            my_instance_id = self._metadata['instance']['id']
        except Exception as e:
            _logger.error('Cannot find my instance ID: %s' % e)
            return None

        return self.get_instance(instance_id=my_instance_id,
                                 refresh=refresh)

    def this_compartment(self, refresh=False):
        """
        Get the current compartment

        Parameters
        ----------
        refresh : bool
        #   --GT-- not used
            Flag, refresh  information if set.

        Returns
        -------
        OCICompartment
            A OCICompartment instance or None if no compartement
            information is found or refresh has failed.
        """

        if self._metadata is None:
            _logger.warning('metadata is None !')
            # TODO: should it severe error case instead ??
            return None
        try:
            my_compartment_id = self._metadata['instance']['compartmentId']
        except Exception:
            _logger.error('no compartement ID information in metadata')
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
        return self.tenancy_ocid

    def this_region(self):
        """
        Get the current region of the instance.

        Returns
        -------
        str
            The region name or None if no information is found in metadata.
        """
        if self._metadata is None:
            _logger.warning('metadata is None !')
            # TODO: should it severe error case instead ??
            return None
        try:
            return self._metadata['instance']['region']
        except Exception:
            _logger.warning('no region information in metadata')
            return None

    def get_instance(self, instance_id, refresh=False):
        """
        Get instance by ID

        Parameters
        ----------
        instance_id : str
            The ID of the wanted instance.
        refresh : bool, optional
            Flag, refresh information if set.

        Returns
        -------
        OCIInstance
            The OCI instance or None if it is not found.
        """
        if not refresh and self._instances:
            # return from cache
            for i in self._instances:
                if i.get_ocid() == instance_id:
                    return i
        try:
            cc = self.get_compute_client()
            instance_data = self.sdk_call(cc.get_instance,
                                          instance_id=instance_id).data
            return OCIInstance(self, instance_data)
        except Exception as e:
            _logger.error('Failed to fetch instance: %s. \n'
                          'Check your connection and settings.' % e)

        return None

    def get_subnet(self, subnet_id, refresh=False):
        """
        Get the subnet.

        Parameters
        ----------
        subnet_id: str
            The subnet id.
        refresh : bool
            Flag, refresh the information if set.

        Returns
        -------
            The subnet object or None if not found.
        """
        nc = self.get_network_client()
        try:
            sn_data = self.sdk_call(nc.get_subnet,
                                    subnet_id=subnet_id).data
            return OCISubnet(self, subnet_data=sn_data)
        except oci_sdk.exceptions.ServiceError:
            _logger.debug('failed to get subnet', exc_info=True)
            return None

        return None

    def get_volume(self, volume_id, refresh=False):
        """
        Get an OCIVolume object representing the volume with the given OCID.

        Parameters
        ----------
        volume_id : str
            The volume id.
        refresh : bool
            Flag, refresh the information if set.
        Returns
        -------
        dict
            The volume object or None if not found.
        """
        if self._volumes is not None and not refresh:
            for vol in self._volumes:
                if vol.get_ocid() == volume_id:
                    return vol

        bsc = self.get_block_storage_client()
        cc = self.get_compute_client()

        try:
            vol_data = self.sdk_call(bsc.get_volume,
                                     volume_id=volume_id).data
        except oci_sdk.exceptions.ServiceError:
            _logger.debug('failed to get volume', exc_info=True)
            return None

        if OCI_RESOURCE_STATE[vol_data.lifecycle_state] \
                == OCI_RESOURCE_STATE.TERMINATED:
            return None

        try:
            v_att_list = self.sdk_call(cc.list_volume_attachments,
                                       compartment_id=vol_data.compartment_id,
                                       volume_id=vol_data.id).data
        except Exception:
            # can't find any attachments for this volume
            return OCIVolume(self, volume_data=vol_data)

        # find the latest attachment entry for this volume
        v_att_data = None
        for v_att in v_att_list:
            if v_att_data is None:
                v_att_data = v_att
                continue
            if v_att.time_created > v_att_data.time_created:
                v_att_data = v_att

        return OCIVolume(self,
                         volume_data=vol_data,
                         attachment_data=v_att_data)

    def get_compartment(self, **kargs):
        if 'ocid' not in kargs:
            # for now make it mandatory
            raise Exception('ocid must be provided')

        try:
            c_data = self._identity_client.get_compartment(compartment_id=kargs['ocid']).data
            return OCICompartment(session=self, compartment_data=c_data)
        except Exception as e:
            _logger.error('error getting compartment: %s' % e)
            return None

    def get_vcn(self, vcn_id, refresh=False):
        """
        Get VCN by ID.

        Parameters
        ----------
        vcn_id : str
            The ID of the wanted vcn.
        refresh : bool
            Flag, refresh the information if set.

        Returns
        -------
        OCIVCN
            The OCI VCN  or None if it is not found.
        """
        if not refresh and self._vcns:
            # return from cache
            for i in self._vcns:
                if i.get_ocid() == vcn_id:
                    return i
        for c in self.all_vcns(refresh=refresh):
            if c.get_ocid() == vcn_id:
                return c
        return None

    def get_vnic(self, vnic_id, refresh=False):
        """
        Get VNIC by ID.

        Parameters
        ----------
        vnic_id : str
            The ID of the wanted vnic.
        refresh : bool
            Flag, refresh the information if set.

        Returns
        -------
        OCIVNIC
            The OCI VNIC  or None if it is not found.
        """
        # FIXME: use list_vnic_attachments and get_vnic directly
        for c in self.all_compartments(refresh=refresh):
            for v in c.all_vnics(refresh=refresh):
                if v.get_ocid() == vnic_id:
                    return v
        return None

    def create_volume(self, compartment_id, availability_domain,
                      size, display_name=None, wait=True):
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
        OCISDKError
            If the creation of the volume fails for any reason.
        """
        bsc = self.get_block_storage_client()
        cvds = oci_sdk.core.models.CreateVolumeDetails(
            availability_domain=availability_domain,
            compartment_id=compartment_id,
            size_in_gbs=size,
            display_name=display_name)
        try:
            vol_data = self.sdk_call(bsc.create_volume,
                                     create_volume_details=cvds)
            if wait:
                while OCI_RESOURCE_STATE[vol_data.data.lifecycle_state] \
                        != OCI_RESOURCE_STATE.AVAILABLE:
                    sleep(2)
                    vol_data = self.sdk_call(bsc.get_volume,
                                             volume_id=vol_data.data.id)
            return OCIVolume(self, vol_data.data)
        except oci_sdk.exceptions.ServiceError as e:
            raise OCISDKError('Failed to create volume: %s' % e.message)
