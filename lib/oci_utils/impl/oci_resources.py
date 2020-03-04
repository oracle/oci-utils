#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import json
import logging
import os
import re
from time import sleep

from oci_utils.metadata import OCIMetadata
from .resources import OCIAPIAbstractResource
from .. import _configuration as oci_utils_configuration
from .. import _MAX_VOLUMES_LIMIT, OCI_ATTACHMENT_STATE, \
    OCI_COMPARTEMENT_STATE, \
    OCI_RESOURCE_STATE, OCI_INSTANCE_STATE, OCI_VOLUME_SIZE_FMT
from ..exceptions import OCISDKError

try:
    import oci as oci_sdk
except ImportError:
    # if SDK not there none of resources is instanciated;
    # i.e we never end up here
    pass


class OCICompartment(OCIAPIAbstractResource):
    """ The OCI compartment object.
    """
    _logger = logging.getLogger('oci-utils.OCICompartment')

    def __init__(self, session, compartment_data):
        """
        Initialisation of the OCICompartment instance.

        Parameters
        ----------
        session: OCISession.

        compartment_data: dict
            id: str
                The value to assign to the id property of this Compartment.
            compartment_id: str
                The value to assign to the compartment_id property of this
                Compartment.
            name: str
                The value to assign to the name property of this Compartment.
            description: str
                The value to assign to the description property of this
                Compartment.
            time_created: datetime
                The value to assign to the time_created property of this
                Compartment.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                Compartment. Allowed values for this property are:
                "CREATING", "ACTIVE", "INACTIVE", "DELETING", "DELETED",
                'UNKNOWN_ENUM_VALUE'.  Any unrecognized values returned by a
                service will be mapped to 'UNKNOWN_ENUM_VALUE'.
            inactive_status: int
                The value to assign to the inactive_status property of this
                Compartment.
            freeform_tags: dict(str, str)
                The value to assign to the freeform_tags property of this
                Compartment.
            defined_tags: dict(str, dict(str, object)
                The value to assign to the defined_tags property of this
                Compartment.
        """
        OCIAPIAbstractResource.__init__(self, compartment_data, session)
        self._tenancy_id = compartment_data.compartment_id
        self._subnets = None
        self._instances = None
        self._vcns = None
        self._vnics = None
        self._volumes = None

    def __str__(self):
        """
        Override the string representation of the instance.

        Returns
        -------
            str
                The string representation of the OCICompartment object.
        """
        return "Compartment %s" % OCIAPIAbstractResource.__str__(self)

    def get_display_name(self):
        """
        Get the display name.

        Returns
        -------
            str
                The display name.
        """
        return self._data.name

    def all_instances(self, refresh=False):
        """
        Get all instance of this compartment.

        Parameters
        ----------
        refresh: bool
            Do we refresh compartment information first ? (the default is
            False).

        Returns
        -------
            list
                list of instances as list of OCIInstance objects, can be empty.
        """
        if self._instances is not None and not refresh:
            return self._instances
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] \
                != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        instances = []
        try:
            instances_data = self._oci_session.sdk_call(
                cc.list_instances,
                compartment_id=self._ocid)
            for i_data in instances_data.data:
                if OCI_INSTANCE_STATE[i_data.lifecycle_state] \
                        == OCI_INSTANCE_STATE.TERMINATED:
                    continue
                instances.append(OCIInstance(self._oci_session, i_data))
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment
            OCICompartment._logger.debug('user has no permission to list the instances in the compartment')
            
        self._instances = instances
        return instances

    def all_subnets(self, refresh=False):
        """
        Get all subnet of this compartment.

        Parameters
        ----------
        refresh: bool
            Do we refresh compartment information first ? (the default is False)

        Returns
        -------
            list
                List of subnets as list of OCISubnet objects, can be empty.
        """
        if self._subnets is not None and not refresh:
            return self._subnets
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] \
                != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        subnets = []
        for vcn in self.all_vcns(refresh=refresh):
            vcn_subnets = vcn.all_subnets()
            if vcn_subnets is not None:
                subnets += vcn_subnets
        self._subnets = subnets
        return subnets

    def all_vnics(self, refresh=False):
        """
        Get all VNICs of this compartment.

        Parameters
        ----------
        refresh: bool
            Refresh compartment information first if set.

        Returns
        -------
            list
                List of VNICs as list of OCIVNIC objects, can be empty.
        """
        if self._vnics is not None and not refresh:
            return self._vnics
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] \
                != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        vnics = []
        for instance in self.all_instances(refresh=refresh):
            inst_vnics = instance.all_vnics(refresh=refresh)
            if inst_vnics:
                vnics += inst_vnics
        self._vnics = vnics
        return vnics

    def all_vcns(self, refresh=False):
        """
        Get all VCNs of this compartment.

        Parameters
        ----------
        refresh: bool
            Refresh compartment information first if set.

        Returns
        -------
            list
                List of VCNs as list of OCIVCN objects, can be empty.
        """
        if self._vcns is not None and not refresh:
            return self._vcns
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] \
                != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list vcns
        # in this compartment, so ignoring ServiceError exceptions
        vcns = []
        try:
            vcns_data = self._oci_session.sdk_call(
                nc.list_vcns, compartment_id=self._ocid)
            for v_data in vcns_data.data:
                if OCI_RESOURCE_STATE[v_data.lifecycle_state] \
                        != OCI_RESOURCE_STATE.AVAILABLE:
                    continue
                vcns.append(OCIVCN(self._oci_session, v_data))
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the vcns in the compartment
            OCICompartment._logger.debug('current user has no permission to list the vcns in the compartment')
            
        self._vcns = vcns
        return vcns

    def all_volumes(self, refresh=False, availability_domain=None):
        """Get all volumes of this compartment

        Parameters
        ----------
        refresh: bool
            Refresh compartment information first if set.
        availability_domain: str
            The domain name.

        Returns
        -------
            list
                List of volume as list of OCIVolume objects, can be empty.
        """
        if self._volumes is not None \
                and availability_domain is None \
                and not refresh:
            return self._volumes
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] \
                != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        bsc = self._oci_session.get_block_storage_client()
        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list volumes
        # in this compartment, so ignoring ServiceError exceptions
        bs = []
        try:
            if availability_domain:
                bs_data = self._oci_session.sdk_call(
                    bsc.list_volumes, availability_domain=availability_domain,
                    compartment_id=self._ocid)
            else:
                bs_data = self._oci_session.sdk_call(bsc.list_volumes,
                                                     compartment_id=self._ocid)
            for v_data in bs_data.data:
                if OCI_RESOURCE_STATE[v_data.lifecycle_state] \
                        != OCI_RESOURCE_STATE.AVAILABLE:
                    continue
                v_att_list = self._oci_session.sdk_call(
                    cc.list_volume_attachments,
                    compartment_id=self._ocid,
                    volume_id=v_data.id).data
                v_att_data = None
                for v_att in v_att_list:
                    if v_att_data is None:
                        v_att_data = v_att
                        continue
                    if v_att.time_created > v_att_data.time_created:
                        v_att_data = v_att
                bs.append(OCIVolume(self._oci_session,
                                    volume_data=v_data,
                                    attachment_data=v_att_data))
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the volumes in the compartment
            OCICompartment._logger.debug('current user has no permission to list the volumes in the compartment')
            pass
        if availability_domain is None:
            self._volumes = bs
        return bs

    def create_volume(self, availability_domain, size, display_name=None,
                      wait=True):
        """
        Create a new OCI Storage Volume in this compartment.

        Parameters
        ----------
        availability_domain: str
            The domain name.
        size: int
            The volume size.
        display_name: str
            The name of the volume.
        wait: bool
            Wait for completion if set.

        Returns
        -------
            OCIVolume
                The created volume.
        """
        return self._oci_session.create_volume(
            compartment_id=self.get_ocid(),
            availability_domain=availability_domain,
            size=size,
            display_name=display_name,
            wait=wait)


class OCIInstance(OCIAPIAbstractResource):
    """ The OCI instance class.
    """
    _logger = logging.getLogger('oci-utils.OCIInstance')

    # Notes: dict can be json formatted string or file.
    settable_field_type = {
        'displayName': str,
        'metadata': dict,
        'extendedMetadata': dict}

    lower_settable_fields = {key.lower(): key for key in settable_field_type}

    def __init__(self, session, instance_data):
        """
        Initialisation of the OCIInstance instance.

        Parameters
        ----------
        session: OCISession.

        instance_data: dict
            availability_domain: str
                The value to assign to the availability_domain property of
                this Instance.
            compartment_id: str
                The value to assign to the compartment_id property of this
                Instance.
            defined_tags: dict(str, dict(str, object))
                The value to assign to the defined_tags property of this
                Instance.
            display_name: str
                The value to assign to the display_name property of this
                Instance.
            extended_metadata: dict(str, object)
                The value to assign to the extended_metadata property of this
                Instance.
            freeform_tags: dict(str, str)
                The value to assign to the freeform_tags property of this
                Instance.
            id: str
                The value to assign to the id property of this Instance.
            image_id: str
                The value to assign to the image_id property of this Instance.
            ipxe_script: str
                The value to assign to the ipxe_script property of this
                Instance.
            launch_mode: str
                The value to assign to the launch_mode property of this
                Instance. Allowed values for this property are: "NATIVE",
                "EMULATED", "CUSTOM", 'UNKNOWN_ENUM_VALUE'. Any unrecognized
                values returned by a service will be mapped to
                'UNKNOWN_ENUM_VALUE'.
            launch_options: LaunchOptions
                The value to assign to the launch_options property of this
                Instance.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                Instance. Allowed values for this property are:
                "PROVISIONING", "RUNNING", "STARTING", "STOPPING", "STOPPED",
                "CREATING_IMAGE", "TERMINATING", "TERMINATED",
                'UNKNOWN_ENUM_VALUE'. Any unrecognized values returned by a
                service will be mapped to 'UNKNOWN_ENUM_VALUE'.
            metadata: dict(str, str)
                The value to assign to the metadata property of this Instance.
            region: str
                The value to assign to the region property of this Instance.
            shape: str
                The value to assign to the shape property of this Instance.
            source_details: InstanceSourceDetails
                The value to assign to the source_details property of this
                Instance.
            time_created: datetime
                The value to assign to the time_created property of this
                Instance.
        """
        OCIAPIAbstractResource.__init__(self, instance_data, session)
        self._vnics = None
        self._subnets = None
        self._volumes = None
        self._metadata = None
        self._secondary_private_ips = None

    def __str__(self):
        """
        Override the string representation of the instance.

        Returns
        -------
            str
                The string representation of the OCIInstance object.
        """
        return "Instance %s" % OCIAPIAbstractResource.__str__(self)

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                The hostname.
        """
        return self._data.display_name

    def get_state(self):
        """
        Get the state.

        Returns
        -------
             str
                 The state, one of:
                  PROVISIONING,
                  RUNNING,
                  STARTING,
                  STOPPING,
                  STOPPED,
                  CREATING_IMAGE,
                  TERMINATING,
                  TERMINATED,
                  UNKNOWN_ENUM_VALUE
        """
        return self._data.lifecycle_state

    def get_public_ip(self):
        """
        Get the public IP address of the primary VNIC.

        Returns
        -------
            str
                The public IP address.
        """
        for v in self.all_vnics():
            if v.is_primary():
                return v.get_public_ip()
        return None

    def all_public_ips(self):
        """
        Get all the public IP addresses associated with this instance.

        Returns
        -------
            list
                The list of all public IP addresses of this instance.
        """
        ips = []
        for v in self.all_vnics():
            ip = v.get_public_ip()
            if ip is not None:
                ips.append(ip)
        return ips

    def all_vnics(self, refresh=False):
        """
        Get all virtual network interfaces associated with this instance.

        Parameters
        ----------
        refresh: bool
             Refresh the cache if set.

        Returns
        -------
            list
                the list of all vnics OCIVNIC's.
        """
        if self._vnics is not None and not refresh:
            return self._vnics

        vnics = []
        cc = self._oci_session.get_compute_client()
        nc = self._oci_session.get_network_client()
        try:
            vnic_atts = self._oci_session.sdk_call(
                cc.list_vnic_attachments,
                compartment_id=self._data.compartment_id,
                instance_id=self._ocid)
        except Exception as e:
            OCIInstance._logger.debug('sdk call failed',exc_info=True)
            OCIInstance._logger.warning('sdk call failed [%s]' % str(e))
            return []
        for v_a_data in vnic_atts.data:
            if OCI_ATTACHMENT_STATE[v_a_data.lifecycle_state] \
                    != OCI_ATTACHMENT_STATE.ATTACHED:
                continue
            try:
                vnic_data = self._oci_session.sdk_call(nc.get_vnic,
                                                       v_a_data.vnic_id).data
                vnics.append(OCIVNIC(self._oci_session, vnic_data=vnic_data,
                                     attachment_data=v_a_data))
            except oci_sdk.exceptions.ServiceError:
                # ignore these, it means the current user has no
                # permission to list the instances in the compartment
                OCIInstance._logger.debug('current user has no permission to list the vcns in the compartment')
                pass
        self._vnics = vnics
        return self._vnics

    def find_private_ip(self, ip_address, refresh=False):
        """
        Find a secondary private IP based on its IP if address.

        Parameters
        ----------
        ip_address: str
            The IP address.
        refresh: bool
            Refresh the cache if set.
            # not used, kept in to avoid breaking method call.

        Returns
        -------
            str
                The private IP address if foune, None otherwise.
        """
        for priv_ip in self.all_private_ips():
            if priv_ip.get_address() == ip_address:
                return priv_ip
        return None

    def all_private_ips(self, refresh=False):
        """
        Return a list of secondary private IPs assigned to this instance.

        Parameters
        ----------
        refresh: bool
            Refresh teh cache if set.

        Returns
        -------
            list
                The list of private IP addresses associated with the instance.
        """
        if self._secondary_private_ips is not None and not refresh:
            return self._secondary_private_ips

        private_ips = []
        for vnic in self.all_vnics(refresh=refresh):
            pips = vnic.all_private_ips(refresh=refresh)
            private_ips += pips

        self._secondary_private_ips = private_ips
        return private_ips

    def all_subnets(self, refresh=False):
        """
        Get all subnets associated with the instance.

        Parameters
        ----------
        refresh: bool
            Refresh the cash if set.

        Returns
        -------
            set
                All the subnets.
        """
        if self._subnets is not None and not refresh:
            return self._subnets

        subnets = set()
        for vnic in self.all_vnics(refresh=refresh):
            # discard vnic with no subnet
            if vnic.get_subnet() is not None:
                subnets.add(vnic.get_subnet())
        self._subnets = list(subnets)
        return self._subnets

    def all_volumes(self, refresh=False):
        """
        Get all the volumes associates with this instance.

        Parameters
        ----------
        refresh: bool
            Refresh the cache if set.

        Returns
        -------
            list
                List of volumes OCIVolume's.
        """
        if self._volumes is not None and not refresh:
            return self._volumes

        bsc = self._oci_session.get_block_storage_client()
        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list volumes
        # so ignoring ServiceError exceptions
        try:
            v_att_list = self._oci_session.sdk_call(
                cc.list_volume_attachments,
                compartment_id=self._data.compartment_id,
                instance_id=self._ocid).data
        except oci_sdk.exceptions.ServiceError:
            # the user has no permission to list volumes
            OCIInstance._logger.debug('the user has no permission to list volumes', exc_info=True)
            self._volumes = []
            return self._volumes

        # multiple volume attachments may exist for the same
        # volume and instance.  For each one, we need to find
        # the most recent one
        v_att_data = {}
        for v_att in v_att_list:
            if v_att.volume_id not in v_att_data:
                v_att_data[v_att.volume_id] = v_att
                continue
            if v_att_data[v_att.volume_id].time_created < \
               v_att.time_created:
                v_att_data[v_att.volume_id] = v_att

        vols = []
        for vol_id in list(v_att_data.keys()):
            # only include volumes that are properly attached, not
            # attaching or detaching or anything like that
            if OCI_ATTACHMENT_STATE[v_att_data[vol_id].lifecycle_state] \
                    != OCI_ATTACHMENT_STATE.ATTACHED:
                continue

            try:
                vol_data = self._oci_session.sdk_call(
                    bsc.get_volume,
                    volume_id=vol_id).data
            except oci_sdk.exceptions.ServiceError:
                OCIInstance._logger.debug('exc getting volume', exc_info=True)
                continue
            vols.append(OCIVolume(self._oci_session,
                                  volume_data=vol_data,
                                  attachment_data=v_att_data[vol_id]))

        self._volumes = vols
        return vols

    def attach_volume(self, volume_id, use_chap=False,
                      display_name=None, wait=True):
        """
        Attach the given volume to this instance.

        Parameters
        ----------
        volume_id: str
            The volume id.
        use_chap: bool
            Use chap security if set.
        display_name: str
            The instance name.
        wait: bool
            Wait for completion if set.

        Returns
        -------
            OCIVolume
                The attached volume.
        """
        if self.max_volumes_reached():
            raise OCISDKError('This instance reached its max_volumes.')

        av_det = oci_sdk.core.models.AttachIScsiVolumeDetails(
            type="iscsi",
            use_chap=use_chap,
            volume_id=volume_id,
            instance_id=self.get_ocid(),
            display_name=display_name)
        cc = self._oci_session.get_compute_client()
        try:
            vol_att = self._oci_session.sdk_call(cc.attach_volume, av_det)
            if wait:
                while OCI_ATTACHMENT_STATE[vol_att.data.lifecycle_state] \
                        != OCI_ATTACHMENT_STATE.ATTACHED:
                    sleep(2)
                    vol_att = self._oci_session.sdk_call(
                        cc.get_volume_attachment,
                        vol_att.data.id)
            return self._oci_session.get_volume(vol_att.data.volume_id,
                                                refresh=True)
        except oci_sdk.exceptions.ServiceError as e:
            OCIInstance._logger.debug('Failed to attach volume', exc_info=True)
            raise OCISDKError('Failed to attach volume: %s' % e.message)

    def attach_vnic(self, private_ip=None, subnet_id=None, nic_index=0,
                    display_name=None, assign_public_ip=False,
                    hostname_label=None, skip_source_dest_check=False,
                    wait=True):
        """
        Create and attach a VNIC to this device.
        Use sensible defaults:
          - subnet_id: if None, use the same subnet as the primary VNIC.
          - private_ip: if None, the next available IP in the subnet.

        Parameters
        ----------
        private_ip: str
            The private IP address.
        subnet_id: int
            The subnet id.
        nic_index: int
            The interface index.
        display_name: str
            The name.
        assign_public_ip: bool
            Provide a public IP address if set.
        hostname_label: str
            The label.
        skip_source_dest_check: bool
            Skip source and destiantion existence check if set.
        wait: bool
            Wait for completion if set.

        Returns
        -------
            OCIVNIC
                The virtual network interface card data VNIC.

        Raises
        ------
            OCISDKError
                On any error.
        """
        if display_name is None and hostname_label is not None:
            display_name = hostname_label
        if hostname_label is None and display_name is not None:
            hostname = os.popen("/usr/bin/hostname").read().strip()
            hostname_label = hostname + "-" + display_name
            # list of acceptable chars in a host name
            hostname_chars = 'abcdefghijklmnopqrstuvwxyz' \
                             'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
                             '0123456789-'
            hostname_label = \
                ''.join([c for c in hostname_label if c in hostname_chars])
        # step 1: choose a subnet
        if subnet_id is None:
            instance_subnets = self.all_subnets()
            if len(instance_subnets) == 0:
                # subnet id is not provided, if instance has no subnet
                # no need to go further
                raise OCISDKError('No suitable subnet found for this instance')
            if private_ip is not None:
                # choose the subnet that the ip belongs to
                for sn in instance_subnets:
                    if sn._ip_matches(private_ip):
                        subnet_id = sn.get_ocid()
                if subnet_id is None:
                    # no suitable subnet found for the IP address
                    raise OCISDKError('No suitable subnet found for IP address '
                                      '%s' % private_ip)
            else:
                # choose one of the subnets the instance currently uses
                if len(instance_subnets) == 1:
                    subnet_id = instance_subnets[0].get_ocid()
                else:
                    # FIXME: for now just choose the first one,
                    # but we can probably be cleverer
                    subnet_id = instance_subnets[0].get_ocid()
        cc = self._oci_session.get_compute_client()
        create_vnic_details = oci_sdk.core.models.CreateVnicDetails(
            assign_public_ip=assign_public_ip,
            display_name=display_name,
            hostname_label=hostname_label,
            private_ip=private_ip,
            skip_source_dest_check=skip_source_dest_check,
            subnet_id=subnet_id)
        attach_vnic_details = oci_sdk.core.models.AttachVnicDetails(
            create_vnic_details=create_vnic_details,
            display_name=display_name,
            nic_index=nic_index,
            instance_id=self.get_ocid())
        try:
            resp = self._oci_session.sdk_call(cc.attach_vnic,
                                              attach_vnic_details)
            v_att = self._oci_session.sdk_call(cc.get_vnic_attachment,
                                               resp.data.id)
            if wait:
                while OCI_ATTACHMENT_STATE[v_att.data.lifecycle_state] \
                        != OCI_ATTACHMENT_STATE.ATTACHED:
                    sleep(2)
                    v_att = self._oci_session.sdk_call(cc.get_vnic_attachment,
                                                       resp.data.id)
            return self._oci_session.get_vnic(v_att.data.vnic_id, refresh=True)
        except oci_sdk.exceptions.ServiceError as e:
            OCIInstance._logger.debug('Failed to attach new VNIC', exc_info=True)
            raise OCISDKError('Failed to attach new VNIC: %s' % e.message)

    def max_volumes_reached(self):
        """
        Test if the maximum number of volumes is reached.

        Returns
        -------
            bool
                True if maximum is reached, False otherwise.
        """
        max_volumes = oci_utils_configuration.getint('iscsi', 'max_volumes')
        if max_volumes > _MAX_VOLUMES_LIMIT:
            max_volumes = _MAX_VOLUMES_LIMIT
        if len(self.all_volumes()) >= max_volumes:
            return True
        return False

    def create_volume(self, size, display_name=None):
        """
        Create a new OCI Storage Volume and attach it to this instance.

        Parameters
        ----------
        size: int
            The size of the volume.
        display_name: str
            The name.

        Returns
        -------
            OCIVolume
                The volume.
        """
        if self.max_volumes_reached():
            raise OCISDKError('This instance reached its max_volumes.')

        vol = self._oci_session.create_volume(
            compartment_id=self._data.compartment_id,
            availability_domain=self._data.availability_domain,
            size=size,
            display_name=display_name,
            wait=True)

        try:
            vol = vol.attach_to(instance_id=self.get_ocid())
        except Exception as e:
            OCIInstance._logger.debug('cannot attach BV', exc_info=True)
            OCIInstance._logger.warning('cannot attach BV [%s]' % str(e))
            vol.destroy()
            return None
        return vol

    def get_metadata(self, get_public_ip=False, refresh=False):
        """
        Get the metadata.

        Parameters
        ----------
        get_public_ip: bool
            Collect the public ip if set.
        refresh: bool
            Refresh the cache if set.

        Returns
        -------
            OCIMetadata
                The metadata.
        """
        if self._metadata is not None and not refresh:
            return self._metadata

        meta = {}
        meta['instance'] = self.__dict__()

        # get vnics
        vnics = self.all_vnics(refresh=refresh)
        vnics_l = []
        for vnic in vnics:
            vnic_i = vnic.__dict__()
            vnic_a = json.loads(vnic._att_data.__str__())
            vnic_i['nic_index'] = vnic_a['nic_index']
            vnic_i['vlan_tag'] = vnic_a['vlan_tag']
            vnics_l.append(vnic_i)
        meta['vnics'] = vnics_l

        # get public ips
        if get_public_ip:
            meta['public_ip'] = self.get_public_ip()

        self._metadata = OCIMetadata(meta, convert=True)
        return self._metadata


class OCIVCN(OCIAPIAbstractResource):
    _logger = logging.getLogger('oci-utils.OCIVCN')

    def __init__(self, session, vcn_data):
        """
        Initialisation of the OCI Virtual Cloud Network class.

        Parameters
        ----------
        session: OCISession.

        vcn_data: dict
            cidr_block: str
                The value to assign to the cidr_block property of this Vcn.
            compartment_id: str
                The value to assign to the compartment_id property of this Vcn.
            default_dhcp_options_id: str
                The value to assign to the default_dhcp_options_id property
                of this Vcn.
            default_route_table_id: str
                The value to assign to the default_route_table_id property of
                this Vcn.
            default_security_list_id: str
                The value to assign to the default_security_list_id property
                of this Vcn.
            defined_tags: dict(str, dict(str, object))
                The value to assign to the defined_tags property of this Vcn.
            display_name: str
                The value to assign to the display_name property of this Vcn.
            dns_label: str
                The value to assign to the dns_label property of this Vcn.
            freeform_tags: dict(str, str)
                The value to assign to the freeform_tags property of this Vcn.
            id: str
                The value to assign to the id property of this Vcn.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                Vcn.  Allowed values for this property are: OCI_RESOURCE_STATE
            time_created: datetime
                The value to assign to the time_created property of this Vcn.
            vcn_domain_name: str
                The value to assign to the vcn_domain_name property of this Vcn.
        """
        OCIAPIAbstractResource.__init__(self, vcn_data, session)
        self.compartment_name = None
        self.subnets = None
        self.security_lists = None

    def __str__(self):
        """
        Override the string representation of the vcn.

        Returns
        -------
            str
                The string representation of the vcn.
        """

        return "VCN %s" % OCIAPIAbstractResource.__str__(self)

    def set_compartment_name(self, name):
        """
        Set the compartment name.

        Parameters
        ----------
        name: str
            The compartment name.

        Returns
        -------
            No return value.
        """
        self.compartment_name = name

    def all_subnets(self, refresh=False):
        """
        Get all the subnets.

        Parameters
        ----------
        refresh: bool
            Refresh the cache if set.

        Returns
        -------
            list
                The list of all the subnets.
        """
        if self.subnets is not None and not refresh:
            return self.subnets

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        subnets = []
        try:
            subnets_data = self._oci_session.sdk_call(
                nc.list_subnets,
                compartment_id=self._data.compartment_id,
                vcn_id=self._ocid)
            for s_data in subnets_data.data:
                subnets.append(OCISubnet(self._oci_session, s_data))
        except oci_sdk.exceptions.ServiceError:
            OCIVCN._logger.debug('service error', exc_info=True)
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment
            pass
        self.subnets = subnets
        return subnets

    def all_security_lists(self, refresh=False):
        """
        Get all security lists.

        Parameters
        ----------
        refresh: bool
            Refresh the cache if set.

        Returns
        -------
            dict
                The security list.
        """
        if self.security_lists is not None and not refresh:
            return self.security_lists

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        security_lists = dict()
        try:
            security_list_data = self._oci_session.sdk_call(
                nc.list_security_lists,
                compartment_id=self._data.compartment_id,
                vcn_id=self._ocid)
            for s_data in security_list_data.data:
                security_lists.setdefault(s_data.id,
                                          OCISecurityList(self._oci_session,
                                                          s_data))
        except oci_sdk.exceptions.ServiceError:
            OCIVCN._logger.debug('service error', exc_info=True)
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment
            pass
        self.security_lists = security_lists
        return security_lists


class OCIVNIC(OCIAPIAbstractResource):
    _logger = logging.getLogger('oci-utils.OCIVNIC')

    def __init__(self, session, vnic_data, attachment_data):
        """
        Initialisation of the OCIVNIC class.

        Parameters
        ----------
        vnic_data: dict
            availability_domain: str
                The value to assign to the availability_domain property of
                this Vnic.
            compartment_id: str
                The value to assign to the compartment_id property of this Vnic.
            display_name: str
                The value to assign to the display_name property of this Vnic.
            hostname_label: str
                The value to assign to the hostname_label property of this Vnic.
            id: str
                The value to assign to the id property of this Vnic.
            is_primary: bool
                The value to assign to the is_primary property of this Vnic.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                Vnic. Allowed values for this are one of OCI_RESOURCE_STATE
            mac_address: str
                The value to assign to the mac_address property of this Vnic.
            private_ip: str
                The value to assign to the private_ip property of this Vnic.
            public_ip: str
                The value to assign to the public_ip property of this Vnic.
            skip_source_dest_check: bool
                The value to assign to the skip_source_dest_check property of
                this Vnic.
            subnet_id: str
                The value to assign to the subnet_id property of this Vnic.
            time_created: datetime
                The value to assign to the time_created property of this Vnic.

        attachment_data: dict
            availability_domain: str
                The value to assign to the availability_domain property of
                this VnicAttachment.
            compartment_id: str
                The value to assign to the compartment_id property of this
                VnicAttachment.
            display_name: str
                The value to assign to the display_name property of this
                VnicAttachment.
            id: str
                The value to assign to the id property of this VnicAttachment.
            instance_id: str
                The value to assign to the instance_id property of this
                VnicAttachment.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                VnicAttachment.  Allowed values are one of OCI_ATTACHMENT_STATE
            nic_index: int
                The value to assign to the nic_index property of this
                VnicAttachment.
            subnet_id: str
                The value to assign to the subnet_id property of this
                VnicAttachment.
            time_created: datetime
                The value to assign to the time_created property of this
                VnicAttachment.
            vlan_tag: int
                The value to assign to the vlan_tag property of this
                VnicAttachment.
            vnic_id: str
                The value to assign to the vnic_id property of this
                VnicAttachment.
        """
        OCIAPIAbstractResource.__init__(self, vnic_data, session)
        self._att_data = attachment_data
        self._secondary_private_ips = None

    def __str__(self):
        """
        Override the string representation of the OCIVNIC method.

        Returns
        -------
            str
                The string representation of the OCIVNIC method.
        """
        return "VNIC %s" % OCIAPIAbstractResource.__str__(self)

    def get_state(self):
        """
        Get the lifecycle state of the VNIC.

        Returns
        -------
            str
                The lifecycle state.
        """
        return "%s-%s" % (self._data.lifecycle_state,
                          self._att_data.lifecycle_state)

    def get_instance(self):
        """
        Get the instance id.

        Returns
        -------
            str
                The instance id.
        """
        return self._oci_session.get_instance(self._att_data.instance_id)

    def refresh(self):
        """
        Refresh the cache.

        Returns
        -------
            No return value.
        """
        nc = self._oci_session.get_network_client()
        cc = self._oci_session.get_compute_client()
        try:
            self._data = self._oci_session.sdk_call(
                nc.get_vnic,
                vnic_id=self._ocid).data
            self._att_data = self._oci_session.sdk_call(
                cc.get_vnic_attachment,
                vnic_attachment_id=self._att_data.id)
        except Exception as e:
            OCIVNIC._logger.debug('refresh failed', exc_info=True)
            OCIVNIC._logger.warning('refresh failed [%s]' % str(e))

    def get_private_ip(self):
        """
        Get the private IP.

        Returns
        -------
            str
                The private IP address.
        """
        return self._data.private_ip

    def get_public_ip(self):
        """
        Get the public IP.

        Returns
        -------
            str
                The public IP address.
        """
        return self._data.public_ip

    def is_primary(self):
        """
        Verify if the virtual network interface is a primary one.

        Returns
        -------
            bool
                True if the vnic is primay, False otherwise.
        """
        return self._data.is_primary

    def get_mac_address(self):
        """
        Get the MAC address of the virtual network interface.

        Returns
        -------
            str
                The MAC address.
        """
        return self._data.mac_address

    def get_subnet(self):
        """
        Get the subnet id.

        Returns
        -------
            str
                The subnet id.
        """
        return self._oci_session.get_subnet(subnet_id=self._data.subnet_id)

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                The hostname.
        """
        return self._data.hostname_label

    def add_private_ip(self, private_ip=None, display_name=None, wait=True):
        """
        Add a secondary private IP for this VNIC.

        Parameters
        ----------
        private_ip: str
            The IP address to add..
        display_name: str
            The name.
        wait: bool
            Wait for completion if set.
            # --GT-- kept in place to avoid breaking method calls.

        Returns
        -------
            str
                The private IP address if successfully added.

        Raises
        ------
            OCISDKError
                On failure to add.
        """
        cpid = oci_sdk.core.models.CreatePrivateIpDetails(
            display_name=display_name,
            ip_address=private_ip,
            vnic_id=self.get_ocid())
        nc = self._oci_session.get_network_client()
        try:
            private_ip = self._oci_session.sdk_call(
                nc.create_private_ip,
                cpid)
            return OCIPrivateIP(session=self._oci_session,
                                private_ip_data=private_ip.data)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVNIC._logger.debug('Failed to add private IP', exc_info=True)
            raise OCISDKError("Failed to add private IP: %s" % e.message)
        # FIXME: wait not implemented!

    def find_private_ip(self, ip_address, refresh=False):
        """
        Find a secondary private IP based on its IP address.

        Parameters
        ----------
        ip_address: str
            The IP address to look for.
        refresh: bool
            Flag, refresh the cache if set.
            # --GT-- not used, kept in place to avoid method call break.

        Returns
        -------
            str
               The private IP address.
        """
        for priv_ip in self.all_private_ips:
            if priv_ip.get_address() == ip_address:
                return priv_ip
        return None

    def all_private_ips(self, refresh=False):
        """
        Get all secondary private IPs assigned to this VNIC.

        Parameters
        ----------
        refresh: bool
            Flag, refresh the cache if set.

        Returns
        -------
            list
                The list of all secondary private IPs assigned to this VNIC.
        """
        if self._secondary_private_ips is not None and not refresh:
            return self._secondary_private_ips

        nc = self._oci_session.get_network_client()
        all_privips = []
        try:
            privips = self._oci_session.sdk_call(
                nc.list_private_ips,
                vnic_id=self.get_ocid()).data
        except Exception as e:
            OCIVNIC._logger.debug(
                'sdk_call failed for all_private_ips',exc_info=True)
            OCIVNIC._logger.warning(
                'sdk_call failed for all_private_ips [%s]' % str(e))
            return []

        for privip in privips:
            if privip.is_primary:
                continue
            all_privips.append(OCIPrivateIP(session=self._oci_session,
                                            private_ip_data=privip))
        self._secondary_private_ips = all_privips
        return all_privips

    def detach(self, wait=True):
        """
        Detach and delete the given VNIC.

        Parameters
        ----------
            wait: bool
                Flag, wait for completion if set.

        Returns
        -------
           bool
               True if detach is successful.

        Raises
        ------
            OCISDKError
                When detaching the VNIC fails.
        """
        if self.is_primary():
            raise OCISDKError("Cannot detach the primary VNIC.")

        cc = self._oci_session.get_compute_client()
        try:
            self._oci_session.sdk_call(cc.detach_vnic,
                                       vnic_attachment_id=self._att_data.id)
        except Exception as e:
            OCIVNIC._logger.debug(
                'Failed to detach VNIC',exc_info=True)
            raise OCISDKError("Failed to detach VNIC: %s" % e)

        if wait:
            try:
                vnic_att = self._oci_session.sdk_call(cc.get_vnic_attachment,
                                                      self._att_data.id).data
                self._att_data = vnic_att
                while OCI_ATTACHMENT_STATE[vnic_att.lifecycle_state] \
                        != OCI_ATTACHMENT_STATE.DETACHED:
                    sleep(2)
                    vnic_att = self._oci_session.sdk_call(
                        cc.get_vnic_attachment, self._att_data.id).data
                    self._att_data = vnic_att
            except Exception as e:
                OCIVNIC._logger.debug(
                    'sdk_call failed for detach() [%s]' % str(e),exc_info=True)

        return True


class OCIPrivateIP(OCIAPIAbstractResource):
    _logger = logging.getLogger('oci-utils.OCIPrivateIP')

    def __init__(self, session, private_ip_data):
        """
        Initialisation of the OCIPrivateIP class.

        Parameters
        ----------
        private_ip_data:
            availability_domain: str
                The private IP's Availability Domain.  Example: Uocm:PHX-AD-1
            compartment_id: str
                The OCID of the compartment containing the private IP.
            defined_tags: dict
                Defined tags for this resource.  Each key is predefined and
                scoped to a namespace.
                type: dict(str, dict(str, object))
                Example: {"Operations": { "CostCenter": "42"}}
            display_name: str
                A user-friendly name. Does not have to be unique, and it's
                changeable. Avoid entering confidential information.
            freeform_tags: dict
                Free-form tags for this resource.  Each tag is a simple
                key-value pair with no predefined name, type, or namespace.
                type: dict(str, str)
                Example: {"Department": "Finance"}
            hostname_label: str
                The hostname for the private IP.  Used for DNS. The value is
                the hostname portion of the private IP's fully qualified
                domain name (FQDN) (for example, bminstance-1 in FQDN
                bminstance-1.subnet123.vcn1.oraclevcn.com).  Must be unique
                across all VNICs in the subnet and comply with RFC 952 and
                RFC 1123.
                Example: bminstance-1
            id: str
                The private IP's Oracle ID (OCID).
            ip_address: str
                The private IP address of the privateIp object. The address
                is within the CIDR of the VNIC's subnet.
                Example: 10.0.3.3
            is_primary: bool
                Whether this private IP is the primary one on the VNIC.
                Primary private IPs are unassigned and deleted automatically
                when the VNIC is terminated.
            subnet_id: str
                The OCID of the subnet the VNIC is in.
            time_created: str
                The date and time the private IP was created, in the format
                defined by RFC3339.
                Example: 2016-08-25T21:10:29.600Z
            vnic_id: str
                The OCID of the VNIC the private IP is assigned to. The VNIC
                and private IP must be in the same subnet.
        """
        OCIAPIAbstractResource.__init__(self, private_ip_data, session)

    def __str__(self):
        """
        Override the string representation of the OCIPrivateIP.

        Returns
        -------
            str
                The string representation of the OCIPrivateIP.
        """
        return "Private IP %s" % OCIAPIAbstractResource.__str__(self)

    def delete(self):
        """
        Delete this private IP.

        Returns
        -------
            True for success, False otherwise.
        """
        nc = self._oci_session.get_network_client()
        try:
            self._oci_session.sdk_call(
                nc.delete_private_ip,
                self.get_ocid())
            return True
        except Exception as e:
            OCIPrivateIP._logger.debug('delete failed', exc_info=True)
            OCIPrivateIP._logger.warning('delete failed [%s]' % str(e))
            return False

    def get_vnic(self):
        """
        Get the vNIC of this private ip.

        Returns
        -------
            OCIVNIC
                The VNIC instance.
        """
        return self._oci_session.get_vnic(self._data.vnic_id)

    def get_vnic_ocid(self):
        """
        Gets the VNIC id.
        Note : return the value defined in the metadata which may differ
               from instance returned by get_vnic() method
        returns:
        --------
            str : vnic ocid
        """
        return self._data.vnic_id

    def get_address(self):
        """
        Get the IP address.

        Returns
        -------
            str
                The IP address.
        """
        return self._data.ip_address

    def is_primary(self):
        """
        Verify if this is the primary IP.

        Returns
        -------
            bool
                True if this the primary IP address, False otherwise.
        """
        return self._data.is_primary

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                THe hostname.
        """
        return self._data.hostname_label

    def get_subnet(self):
        """
        Get the subnet id.

        Returns
        -------
            str
                The subnet id.
        """
        return self._oci_session.get_subnet(subnet_id=self._data.subnet_id)


class OCISecurityList(OCIAPIAbstractResource):
    protocol = {'1': 'icmp', '4': 'ipv4', '6': 'tcp', '17': 'udp'}

    _logger = logging.getLogger('oci-utils.OCISecurityList')

    def __init__(self, session, security_list_data):
        """
        Initialisation of the OCISecurityList class.

        Parameters
        ----------

        session: OCISession
            OCI SDK session.

        security_list_data: dict
            compartment-id: str
                Compartment OCID.
            defined-tags:

            display-name: str
                name assigned to the list
            egress-security-rules: list
                list of egress rules, each has the following properties:
                    protocol(all)
                    destination("0.0.0.0/0")
                    icmp-options(null)
                    is-stateless(bool)
                    tcp-options(null),
                    udp-options(null)
            freeform-tags: dict
            id: str
                ocid1.securitylist.oc1...,
            ingress-security-rules: list
                list of ingress rules, each has the follwoing properties:
                    protocol(all)    choice of all, 17(UDP),6(TCP), 1(ICMP), etc
                    source("0.0.0.0/0")
                    icmp-options(
                        code: null,
                        type: 3)
                    is-stateless: bool
                    tcp-options(
                        destination-port-range: {
                            max: 22, min: 22
                        }
                        "source-port-range": null
                    ),
            udp-options: str
            lifecycle-state: str
                choiceOCI_RESOURCE_STATE
            time-created: datetime
                2018-01-12T17:44:05.706000+00:00
            vcn-id: str
                ocid1.vcn.oc1...
        """
        OCIAPIAbstractResource.__init__(self, security_list_data, session)

    def get_ingress_rules(self):
        """
        Get the ingress rules.

        Returns
        -------
            list
                The ingress rules.
        """
        return self._data.ingress_security_rules

    def get_egress_rules(self):
        """
        Get the egress rules.

        Returns
        -------
            list
                The egress rules.
        """
        return self._data.egress_security_rules

    def print_security_list(self, indent):
        """
        Print the security list.

        Parameters
        ----------
        indent: str
            The indentation string.

        Returns
        -------
            No return value.
        """
        print("%sSecurity List: %s" % (indent, self.get_display_name()))
        for rule in self.get_ingress_rules():
            prot = OCISecurityList.protocol.get(rule.protocol, rule.protocol)
            src = rule.source
            des = "---"
            desport = "-"
            srcport = "-"
            if rule.protocol == "6" or rule.protocol == "17":
                if rule.protocol == "6":
                    option = rule.tcp_options
                else:
                    option = rule.udp_options

                try:
                    if option.destination_port_range.min \
                            != option.destination_port_range.max:
                        desport = "%s-%s" % (option.destination_port_range.min,
                                             option.destination_port_range.max)
                    else:
                        desport = option.destination_port_range.min
                except Exception:
                    OCISecurityList._logger.debug('error during print', exc_info=True)
                    pass

                try:
                    if option.source_port_range.min \
                            != option.source_port_range.max:
                        srcport = "%s-%s" % (option.source_port_range.min,
                                             option.source_port_range.max)
                    else:
                        srcport = option.source_port_range.min
                except Exception:
                    OCISecurityList._logger.debug('error during print', exc_info=True)
                    pass
            elif rule.protocol == "1":
                srcport = "-"
                option = rule.icmp_options
                desport = "type--"
                try:
                    desport = "type-%s" % option.type
                except Exception:
                    OCISecurityList._logger.debug('error during print', exc_info=True)
                    pass
                try:
                    des = "code-%s" % option.code
                except Exception:
                    des = "code--"
            print("%s  Ingress: %-5s %20s:%-6s %20s:%s" % (
                indent, prot, src, srcport, des, desport))

        for rule in self.get_egress_rules():
            prot = OCISecurityList.protocol.get(rule.protocol, rule.protocol)
            des = rule.destination
            src = "---"
            desport = "-"
            srcport = "-"
            if rule.protocol == "6" or rule.protocol == "17":
                if rule.protocol == "6":
                    option = rule.tcp_options
                else:
                    option = rule.udp_options

                try:
                    if option.destination_port_range.min \
                            != option.destination_port_range.max:
                        desport = "%s-%s" % (option.destination_port_range.min,
                                             option.destination_port_range.max)
                    else:
                        desport = option.destination_port_range.min
                except Exception:
                    desport = "-"

                try:
                    if option.source_port_range.min \
                            != option.source_port_range.max:
                        srcport = "%s-%s" % (option.source_port_range.min,
                                             option.source_port_range.max)
                    else:
                        srcport = option.source_port_range.min

                except Exception:
                    srcport = "-"
            elif rule.protocol == "1":
                srcport = "-"
                option = rule.icmp_options
                try:
                    desport = "type-%s" % option.type
                except Exception:
                    desport = "type--"
                try:
                    des = "code-%s" % option.code
                except Exception:
                    des = "code--"
            print("%s  Egress : %-5s %20s:%-6s %20s:%s" % (
                indent, prot, src, srcport, des, desport))


class OCISubnet(OCIAPIAbstractResource):
    _logger = logging.getLogger('oci-utils.OCISubnet')

    def __init__(self, session, subnet_data):
        """
        Initialisation of the OCISubnet class.

        Parameters
        ----------
        session: OCISession
            OCI SDK session.

        subnet_data: dict
            availability_domain: str
                The value to assign to the availability_domain property of
                this Subnet.
            cidr_block: str
                The value to assign to the cidr_block property of this Subnet.
            compartment_id: str
                The value to assign to the compartment_id property of this
                Subnet.
            defined_tags: dict(str, dict(str, object))
                The value to assign to the defined_tags property of this Subnet.
            dhcp_options_id: str
                The value to assign to the dhcp_options_id property of this
                Subnet.
            display_name: str
                The value to assign to the display_name property of this Subnet.
            dns_label: str
                The value to assign to the dns_label property of this Subnet.
            freeform_tags: dict(str, str)
                The value to assign to the freeform_tags property of this
                Subnet.
            id: str
                The value to assign to the id property of this Subnet.
            lifecycle_state: str
                The value to assign to the lifecycle_state property of this
                Subnet. Allowed values for this property are: "PROVISIONING",
                "AVAILABLE", "TERMINATING", "TERMINATED",
                'UNKNOWN_ENUM_VALUE'.  Any unrecognized values returned by a
                service will be mapped to 'UNKNOWN_ENUM_VALUE'.
            prohibit_public_ip_on_vnic: bool
                The value to assign to the prohibit_public_ip_on_vnic
                property of this Subnet.
            route_table_id: str
                The value to assign to the route_table_id property of this
                Subnet.
            security_list_ids: list[str]
                The value to assign to the security_list_ids property of this
                Subnet.
            subnet_domain_name: str
                The value to assign to the subnet_domain_name property of
                this Subnet.
            time_created: datetime
                The value to assign to the time_created property of this Subnet.
            vcn_id: str
                The value to assign to the vcn_id property of this Subnet.
            virtual_router_ip: str
                The value to assign to the virtual_router_ip property of this
                Subnet.
            virtual_router_mac: str
                The value to assign to the virtual_router_mac property of
                this Subnet.
        """
        OCIAPIAbstractResource.__init__(self, subnet_data, session)
        self._vnics = None
        self._secondary_private_ips = None

    def __str__(self):
        """
        Override the string representation of the subnet volume.

        Returns
        -------
            str
                The string representation of the subnet.
        """
        return "Subnet %s" % OCIAPIAbstractResource.__str__(self)

    def get_cidr_block(self):
        """
        Get the cidr block.

        Returns
        -------
            str
                The cidr block.
        """
        return self._data.cidr_block
    def is_public_ip_on_vnic_allowed(self):
        """
        Checks if public PI allowed in vnic of this subnet
        Returns:
        --------
            bool
                True if allowed
        """
        return not self._data.prohibit_public_ip_on_vnic

    def get_vcn_id(self):
        """
        Get the virtual cn id.

        Returns
        -------
            str
               The virtual cn id.
        """
        return self._data.vcn_id

    def get_security_list_ids(self):
        """
        Get the security list ids.

        Returns
        -------
            list of security list ids.
        """
        return self._data.security_list_ids

    def get_domain_name(self):
        """
        Get the domain name.

        Returns
        -------
            str
                The domain name.
        """
        return self._data.subnet_domain_name

    def all_vnics(self, refresh=False):
        """
        Get a list of all OCIVNIC objects that are in this subnet.

        Parameters
        ----------
        refresh: bool
            Refresh cache if set.

        Returns
        -------
            list
                List of all virtual network interfaces OCIVNIC's.
        """
        if self._vnics is not None and len(self._vnics) > 0 and not refresh:
            return self._vnics
        compartment = self._oci_session.get_compartment(
            ocid=self._data.compartment_id)
        if compartment is None:
            OCISubnet._logger.warning('all_vnics() cannot get compartment')
            return []
        vnics = []
        for vnic in compartment.all_vnics(refresh=refresh):
            if vnic.get_subnet().get_ocid() == self.get_ocid():
                vnics.append(vnic)

        self._vnics = vnics
        return vnics

    def _ip_matches(self, ipaddr):
        """
        Verify if the given IP address matches the cidr block of the subnet.

        Parameters
        ----------
            ipaddr: str
                The IP address.

        Returns
        -------
            True of it does, False otherwise.
        """
        match = re.match(r'([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)',
                         ipaddr)
        if match is None:
            raise OCISDKError('Failed to parse IP address %s' % ipaddr)
        if int(match.group(1)) > 255 or \
           int(match.group(2)) > 255 or \
           int(match.group(3)) > 255 or \
           int(match.group(4)) > 255:
            raise OCISDKError('Invalid IP address: %s' % ipaddr)

        ipint = ((int(match.group(1)) * 256 +
                  int(match.group(2))) * 256 +
                 int(match.group(3))) * 256 + int(match.group(4))
        match = re.match(r'([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)/([0-9]+)',
                         self._data.cidr_block)
        if match is None:
            raise OCISDKError('Failed to parse cidr block %s' %
                              self._data.cidr_block)

        cidripint = ((int(match.group(1)) * 256 +
                      int(match.group(2))) * 256 +
                     int(match.group(3))) * 256 + int(match.group(4))
        cidrmask =\
            int("1" * int(match.group(5)) + "0" * (32 - int(match.group(5))), 2)

        return (ipint & cidrmask) == cidripint

    def all_private_ips(self, refresh=False):
        """
        Get a list of secondary private IPs in this Subnet.

        Parameters
        ----------
        refresh: bool
            Refresh cache if set.

        Returns
        -------
            list
                List of all private IP's OCIPrivateIP.
        """
        if self._secondary_private_ips is not None and not refresh:
            return self._secondary_private_ips

        nc = self._oci_session.get_network_client()
        all_privips = []
        try:
            privips = self._oci_session.sdk_call(
                nc.list_private_ips,
                subnet_id=self.get_ocid()).data
        except Exception as e:
            OCISubnet._logger.debug(
                'all_private_ips() sdk_call failed', exc_info=True)
            OCISubnet._logger.warning(
                'all_private_ips() sdk_call failed [%s]' % str(e))
            return []
        for privip in privips:
            if privip.is_primary:
                continue
            all_privips.append(OCIPrivateIP(session=self._oci_session,
                                            private_ip_data=privip))
        self._secondary_private_ips = all_privips
        return all_privips

    def all_private_ips_with_primary(self, refresh=False):
        """
        Get the list of secondary private IPs in this Subnet.

        Parameters
        ----------
        refresh: bool
            Refresh cache if set.

        Returns
        -------
            list
                List of secondary private IP's OCIPrivateIP.
        """
        if self._secondary_private_ips is not None and not refresh:
            return self._secondary_private_ips

        nc = self._oci_session.get_network_client()
        all_privips = []
        try:
            privips = self._oci_session.sdk_call(
                nc.list_private_ips,
                subnet_id=self.get_ocid()).data
        except Exception as e:
            OCISubnet._logger.debug(
                'all_private_ips() sdk_call failed', exc_info=True)
            OCISubnet._logger.warning(
                'all_private_ips() sdk_call failed [%s]' % str(e))
            return []
        for privip in privips:
            all_privips.append(OCIPrivateIP(session=self._oci_session,
                                            private_ip_data=privip))
        self._secondary_private_ips = all_privips
        return all_privips


class OCIVolume(OCIAPIAbstractResource):

    _logger = logging.getLogger('oci-utils.OCIVolume')

    def __init__(self, session, volume_data, attachment_data=None):
        """
        Initialisation fo the OCIVolume class.

        Parameters
        ----------
            session: OCISession
                OCI SDK session.

            volume_data: dict
                availability_domain: str
                    The value to assign to the availability_domain property
                    of this Volume.
                compartment_id: str
                    The value to assign to the compartment_id property of
                    this Volume.
                defined_tags: dict(str, dict(str, object))
                    The value to assign to the defined_tags property of this
                    Volume.
                display_name: str
                    The value to assign to the display_name property of this
                    Volume.
                freeform_tags: dict(str, str)
                    The value to assign to the freeform_tags property of this
                    Volume.
                id: str
                    The value to assign to the id property of this Volume.
                is_hydrated: bool
                    The value to assign to the is_hydrated property of this
                    Volume.
                volume_state: str
                    The value to assign to the lifecycle_state property of
                    this Volume. Value is one of OCI_VOLUME_STATE.
                size_in_gbs: int
                    The value to assign to the size_in_gbs property of this
                    Volume.
                size_in_mbs: int
                    The value to assign to the size_in_mbs property of this
                    Volume.
                source_details: VolumeSourceDetails
                    The value to assign to the source_details property of
                    this Volume.
                time_created: datetime
                    The value to assign to the time_created property of this
                    Volume.

            attachment_data: dict
                attachment_type: str
                    The value to assign to the attachment_type property of
                    this VolumeAttachment.
                availability_domain: str
                    The value to assign to the availability_domain property
                    of this VolumeAttachment.
                compartment_id: str
                    The value to assign to the compartment_id property of
                    this VolumeAttachment.
                display_name: str
                    The value to assign to the display_name property of this
                    VolumeAttachment.
                id: str
                    The value to assign to the id property of this
                    VolumeAttachment.
                instance_id: str
                    The value to assign to the instance_id property of this
                    VolumeAttachment.
                lifecycle_state: str
                    The value to assign to the lifecycle_state property of
                    this VolumeAttachment. valueis one of OCI_ATTACHMENT_STATE
                time_created: datetime
                    The value to assign to the time_created property of this
                    VolumeAttachment.
                volume_id: str
                    The value to assign to the volume_id property of this
                    VolumeAttachment.

        """
        OCIAPIAbstractResource.__init__(self, volume_data, session)

        self.att_data = attachment_data
        self.volume_lifecycle = OCI_ATTACHMENT_STATE.NOT_ATTACHED
        # few sanity
        if self.att_data:
            assert self.att_data.lifecycle_state in \
                OCI_ATTACHMENT_STATE.__members__, 'unknown state returned'
            self.volume_lifecycle = \
                OCI_ATTACHMENT_STATE[self.att_data.lifecycle_state]

    def __str__(self):
        """
        Override the string representation of the volume.

        Returns
        -------
            str
                The string representation of the OCIVolume object.
        """
        return "Volume %s" % OCIAPIAbstractResource.__str__(self)

    def set_volume_attachment(self, attachment_data):
        """
        Set lifecycle status.

        Parameters
        ----------
        attachment_data: str
            The new attachement status.

        Returns
        -------
            No return value.
        """
        self.att_data = attachment_data
        self.volume_lifecycle = \
            OCI_ATTACHMENT_STATE[self.att_data.lifecycle_state]

    def unset_volume_attachment(self):
        """
        Set lifecycle status to NOT_ATTACHED.

        Returns
        -------
            No return value.
        """
        # volume is not attached
        self.att_data = None
        self.volume_lifecycle = OCI_ATTACHMENT_STATE.NOT_ATTACHED

    def get_attachment_state(self):
        """
        Get the lifecycle state of the volume.

        Returns
        -------
            str
                The state.
        """
        return self.volume_lifecycle.name

    def is_attached(self):
        """
        Verify if the state if the volume is attached.

        Returns
        -------
            bool
                True if attached, False otherwise.
        """
        return self.volume_lifecycle == OCI_ATTACHMENT_STATE.ATTACHED

    def get_size(self, format_str=None):
        """
        Get the size of the volume.

        Parameters
        ----------
            format_str: str
                The format the size should be returned. Current options are
                - self.HUMAN: human readable.
                - self.GB: Gigabytes
                - self.MB: Megabytes

        Returns
        -------
            str or in
                The size of the volume.
        """
        # for compatibility raseon we check against key as string
        assert format_str in OCI_VOLUME_SIZE_FMT.__members__, 'wrong format'

        if (format_str is None) or (format_str == OCI_VOLUME_SIZE_FMT.GB):
            return self._data.size_in_gbs
        elif format_str == OCI_VOLUME_SIZE_FMT.MB:
            return self._data.size_in_mbs
        else:
            return str(self._data.size_in_gbs) + "GB"

    def get_user(self):
        """
        Get the username.

        Returns
        -------
            str
                The username on success, None otherwise.
        """
        if self.att_data is None:
            return None

        try:
            return self.att_data.chap_username
        except Exception:
            return None

    def get_password(self):
        """
        Get the pass key.

        Returns
        -------
            str
               The chap secret on success, None otherwise.
        """
        if self.att_data is None:
            return None

        try:
            return self.att_data.chap_secret
        except Exception:
            return None

    def get_portal_ip(self):
        """
        Get the IP address of the portal.

        Returns
        -------
            str
                The IPv4 address on success, None otherwise.
        """
        if self.att_data is None:
            return None

        try:
            return self.att_data.ipv4
        except Exception:
            return None

    def get_portal_port(self):
        """
        Get the attach port.

        Returns
        -------
            int
                The port number on success, None otherwise.
        """
        if self.att_data is None:
            return None

        try:
            return self.att_data.port
        except Exception:
            return None

    def get_instance(self):
        """
        Get the instance information.

        Returns
        -------
            OCIInstance
                The instance data on success, None otherwise.
        """
        if self.att_data is None:
            return None

        try:
            return self._oci_session.get_instance(self.att_data.instance_id)
        except Exception:
            return None

    def get_iqn(self):
        """
        Get the iSCSI qualified name.

        Returns
        -------
            str
                The iSCSI qualified name on succes, None on failure.
        """
        if self.att_data is None:
            return None

        try:
            return self.att_data.iqn
        except Exception:
            return None

    def attach_to(self, instance_id, use_chap=False,
                  display_name=None, wait=True):
        """
        Attach the volume to the given instance.

        Parameters
        ----------
        instance_id: str
            The instance identification.
        use_chap: bool
            Use chap security if set.
        display_name: str
            The name.
        wait: bool
            Wait for completion if set.

        Returns
        -------
            OCIVolume
                The attached volume.

        Raises
        ------
             OCISDKError
                 On failure to attach the volume.
        """
        av_det = oci_sdk.core.models.AttachIScsiVolumeDetails(
            type="iscsi",
            use_chap=use_chap,
            volume_id=self.get_ocid(),
            instance_id=instance_id,
            display_name=display_name)
        cc = self._oci_session.get_compute_client()
        try:
            vol_att = self._oci_session.sdk_call(
                cc.attach_volume,
                av_det)
            if wait:
                while OCI_ATTACHMENT_STATE[vol_att.data.lifecycle_state] \
                        != OCI_ATTACHMENT_STATE.ATTACHED:
                    sleep(2)
                    vol_att = self._oci_session.sdk_call(
                        cc.get_volume_attachment,
                        vol_att.data.id)
            return self._oci_session.get_volume(vol_att.data.volume_id,
                                                refresh=True)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVolume._logger.debug(
                'Failed to attach volume', exc_info=True)
            raise OCISDKError('Failed to attach volume: %s' % e.message)

    def detach(self, wait=True):
        """
        Detach this volume.

        Parameters
        ----------
        wait : bool, optional
            Wait for completion if set.
        Raises
        ------
        OCISDKError
            call to OCI SDK to detach the volume has failed

        Returns
        -------
            bool
                True if volume is detached, False otherwise.

        Raises
        ------
            OCISDKError
                Call to OCI SDK to detach the volume has failed.
        """
        if not self.is_attached():
            OCIVolume._logger.debug('skip detach, volume not attached')
            return True

        cc = self._oci_session.get_compute_client()

        try:
            self._oci_session.sdk_call(
                cc.detach_volume,
                volume_attachment_id=self.att_data.id)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVolume._logger.debug(
                'Failed to detach volume', exc_info=True)
            raise OCISDKError('Failed to detach volume: %s' % e.message)
        _tries = 3
        vol_att = None
        if wait:
            while _tries > 0:
                try:
                    vol_att = self._oci_session.sdk_call(
                        cc.get_volume_attachment,
                        self.att_data.id).data
                except Exception as e:
                    OCIVolume._logger.debug('sdk_call failed', exc_info=True)
                    OCIVolume._logger.warning(
                        'sdk_call failed checking state of '
                        'volume [%s]' % str(e))
                    _tries = _tries - 1
                if OCI_ATTACHMENT_STATE[vol_att.lifecycle_state] == \
                        OCI_ATTACHMENT_STATE.DETACHED:
                    break
                sleep(2)

        # TODO : can really be alwasy success ?
        self.unset_volume_attachment()
        return True

    def destroy(self):
        """
        Destroy the volume.

        Returns
        -------
            No return value.

        Raises
        ------
            OCISDKError
                On any error.
        """
        if self.is_attached():
            raise OCISDKError("Volume is currently attached, cannot destroy.")

        bsc = self._oci_session.get_block_storage_client()
        try:
            self._oci_session.sdk_call(bsc.delete_volume,
                                       volume_id=self._ocid)
        except Exception as e:
            OCIVolume._logger.debug('Failed to destroy volume', exc_info=True)
            raise OCISDKError("Failed to destroy volume: %s" % e)
