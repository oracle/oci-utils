#
# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import json
import logging
import re
import socket
import oci as oci_sdk
from oci_utils.metadata import OCIMetadata
from .resources import OCIAPIAbstractResource

from .. import OCI_ATTACHMENT_STATE, \
    OCI_COMPARTEMENT_STATE, \
    OCI_RESOURCE_STATE, OCI_INSTANCE_STATE, OCI_VOLUME_SIZE_FMT


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
        #
        # GT
        # self._tenancy_id = compartment_data['compartment_id']
        self._tenancy_id = compartment_data.compartment_id
        self._subnets = None
        self._instances = None
        self._vcns = None

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
        #
        # GT return self._data['name']
        return self._data.name

    def all_instances(self):
        """
        Get all instance of this compartment.


        Returns
        -------
            list
                list of instances as list of OCIInstance objects, can be empty.
        """
        if self._instances is not None:
            return self._instances
        #
        # GT
        # if OCI_COMPARTEMENT_STATE[self._data['lifecycle_state']] != OCI_COMPARTEMENT_STATE.ACTIVE:
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        instances = []
        try:
            instances_data = oci_sdk.pagination.list_call_get_all_results(cc.list_instances, compartment_id=self._ocid)
            for i_data in instances_data.data:
                if OCI_INSTANCE_STATE[i_data.lifecycle_state] \
                        == OCI_INSTANCE_STATE.TERMINATED:
                    continue
                #
                # GT 
                # instances.append(OCIInstance(self._oci_session, oci_sdk.util.to_dict(i_data)))
                instances.append(OCIInstance(self._oci_session, i_data))
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment
            OCICompartment._logger.debug('user has no permission to list the instances in the compartment')

        self._instances = instances
        return instances

    def all_subnets(self):
        """
        Get all subnet of this compartment.


        Returns
        -------
            list
                List of subnets as list of OCISubnet objects, can be empty.
        """
        if self._subnets is not None:
            return self._subnets
        #
        # GT
        # if OCI_COMPARTEMENT_STATE[self._data['lifecycle_state']] \
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []
        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        subnets = []
        try:
            #
            # GT
            #subnets_data = oci_sdk.pagination.list_call_get_all_results(nc.list_subnets, compartment_id=self._data['compartment_id'])
            #
            # GT square
            # subnets_data = oci_sdk.pagination.list_call_get_all_results(nc.list_subnets, compartment_id=self._data.compartment_id)
            subnets_data = oci_sdk.pagination.list_call_get_all_results(nc.list_subnets, compartment_id=self._data.id)
            for s_data in subnets_data.data:
                #
                # GT
                # subnets.append(OCISubnet(self._oci_session, oci_sdk.util.to_dict(s_data)))
                subnets.append(OCISubnet(self._oci_session, s_data))
        except oci_sdk.exceptions.ServiceError:
            OCICompartment._logger.debug('service error', exc_info=True)
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment

        return subnets

    def all_vnics(self):
        """
        Get all VNICs of this compartment.


        Returns
        -------
            list
                List of VNICs as list of OCIVNIC objects, can be empty.
        """
        #
        # GT 
        # if OCI_COMPARTEMENT_STATE[self._data['lifecycle_state']] != OCI_COMPARTEMENT_STATE.ACTIVE:
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        cc = self._oci_session.get_compute_client()
        vnic_ids = []
        try:
            vnic_att_data = oci_sdk.pagination.list_call_get_all_results(cc.list_vnic_attachments,
                                                                         compartment_id=self._ocid)
            for v_data in vnic_att_data.data:
                vnic_ids.append(v_data['vnic_id'])
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the vcns in the compartment
            OCICompartment._logger.debug(
                'current user has no permission to list the vnic attachment in the compartment')

        vnics = []
        for vid in vnic_ids:
            vnics.append(self._oci_session.get_vnic(vid))

        return vnics

    def all_vcns(self):
        """
        Get all VCNs of this compartment.


        Returns
        -------
            list
                List of VCNs as list of OCIVCN objects, can be empty.
        """
        if self._vcns is not None:
            return self._vcns
        #
        #  GT
        # if OCI_COMPARTEMENT_STATE[self._data['lifecycle_state']] != OCI_COMPARTEMENT_STATE.ACTIVE:
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list vcns
        # in this compartment, so ignoring ServiceError exceptions
        vcns = []
        try:
            vcns_data = oci_sdk.pagination.list_call_get_all_results(nc.list_vcns,
                                                                     compartment_id=self._ocid,
                                                                     lifecycle_state=OCI_RESOURCE_STATE.AVAILABLE.name)
            for v_data in vcns_data.data:
                #
                # GT
                # vcns.append(OCIVCN(self._oci_session, oci_sdk.util.to_dict(v_data)))
                vcns.append(OCIVCN(self._oci_session, v_data))
        except oci_sdk.exceptions.ServiceError:
            # ignore these, it means the current user has no
            # permission to list the vcns in the compartment
            OCICompartment._logger.debug('current user has no permission to list the vcns in the compartment')

        return vcns

    def all_volumes(self, availability_domain=None):
        """Get all volumes of this compartment

        Parameters
        ----------
        availability_domain: str
            The domain name.

        Returns
        -------
            list
                List of volume as list of OCIVolume objects, can be empty.
        """

        #
        # GT
        # if OCI_COMPARTEMENT_STATE[self._data['lifecycle_state']] != OCI_COMPARTEMENT_STATE.ACTIVE:
        if OCI_COMPARTEMENT_STATE[self._data.lifecycle_state] != OCI_COMPARTEMENT_STATE.ACTIVE:
            OCICompartment._logger.debug('current state not active')
            return []

        bsc = self._oci_session.get_block_storage_client()
        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list volumes
        # in this compartment, so ignoring ServiceError exceptions
        bs = []
        bs_data = None
        try:
            if availability_domain:
                bs_data = oci_sdk.pagination.list_call_get_all_results(
                    bsc.list_volumes, availability_domain=availability_domain,
                    compartment_id=self._ocid,
                    lifecycle_state=OCI_RESOURCE_STATE.AVAILABLE.name)
            else:
                bs_data = oci_sdk.pagination.list_call_get_all_results(
                    bsc.list_volumes,
                    compartment_id=self._ocid,
                    lifecycle_state=OCI_RESOURCE_STATE.AVAILABLE.name)
        except oci_sdk.exceptions.ServiceError as e:
            raise Exception('Cannot list compartement volumes') from e

        for v_data in bs_data.data:
            try:
                if availability_domain:
                    v_att_list = oci_sdk.pagination.list_call_get_all_results(
                        cc.list_volume_attachments,
                        compartment_id=self._ocid,
                        availability_domain=availability_domain,
                        volume_id=v_data.id).data
                else:
                    v_att_list = oci_sdk.pagination.list_call_get_all_results(
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
                #
                # GT
                # bs.append(OCIVolume(self._oci_session, volume_data=oci_sdk.util.to_dict(v_data), attachment_data=oci_sdk.util.to_dict(v_att_data)))
                bs.append(OCIVolume(self._oci_session, volume_data=v_data, attachment_data=v_att_data))
            except oci_sdk.exceptions.ServiceError:
                # ignore these, it means the current user has no
                # permission to list the volumes in the compartment
                OCICompartment._logger.debug(
                    'current user has no permission to list the volume attachement', exc_info=True)

        return bs


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
        self._subnets = None
        self._metadata = None

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                The hostname.
        """
        #
        # GT
        # return self._data['display_name']
        OCIInstance._logger.debug('_GT_ %s ', self._data)
        return self._data.display_name

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
        """
        try:
            nc = self._oci_session.get_network_client()
            vnic_data = nc.get_vnic(vnic_id).data
            cc = self._oci_session.get_compute_client()
            vnic_att_data = cc.list_vnic_attachments(compartment_id=self.get_compartment_id(),
                                                     instance_id=self.get_ocid(),
                                                     vnic_id=vnic_data.id).data
            #
            # GT
            # return OCIVNIC(self._oci_session, oci_sdk.util.to_dict(vnic_data), oci_sdk.util.to_dict(vnic_att_data[0]))
            return OCIVNIC(self._oci_session, vnic_data, vnic_att_data[0])
        except Exception as e:
            OCIInstance._logger.debug('Failed to fetch VNIC: %s', e)
            raise Exception('Failed to fetch VNIC [%s]' % vnic_id) from e

    def all_vnics(self):
        """
        Get all virtual network interfaces associated with this instance.


        Returns
        -------
            list
                the list of all vnics OCIVNIC's.
        """

        vnics = []
        cc = self._oci_session.get_compute_client()
        nc = self._oci_session.get_network_client()
        try:
            vnic_atts = oci_sdk.pagination.list_call_get_all_results(cc.list_vnic_attachments, compartment_id=self._data.compartment_id, instance_id=self._ocid)
            # GT
            # vnic_atts = oci_sdk.pagination.list_call_get_all_results(cc.list_vnic_attachments, compartment_id=self._data['compartment_id'], instance_id=self._ocid)
        except oci_sdk.exceptions.ServiceError as e:
            OCIInstance._logger.debug('sdk call failed', exc_info=True)
            OCIInstance._logger.warning('sdk call failed [%s]', str(e))
            return []
        for v_a_data in vnic_atts.data:
            try:
                vnic_data = nc.get_vnic(v_a_data.vnic_id).data
                # GT
                # vnics.append(OCIVNIC(self._oci_session, vnic_data=oci_sdk.util.to_dict(vnic_data), attachment_data=oci_sdk.util.to_dict(v_a_data)))
                vnics.append(OCIVNIC(self._oci_session, vnic_data=vnic_data, attachment_data=v_a_data))
            except oci_sdk.exceptions.ServiceError:
                # ignore these, it means the current user has no
                # permission to list the instances in the compartment
                OCIInstance._logger.debug('current user has no permission to list the vcns in the compartment')

        return vnics

    def find_private_ip(self, ip_address):
        """
        Find a secondary private IP based on its IP if address.

        Parameters
        ----------
        ip_address: str
            The IP address.

        Returns
        -------
            str
                The private IP address if found, None otherwise.
        """
        for priv_ip in self.all_private_ips():
            if priv_ip.get_address() == ip_address:
                return priv_ip
        return None

    def all_private_ips(self):
        """
        Return a list of secondary private IPs assigned to this instance.

        Returns
        -------
            list
                The list of private IP addresses associated with the instance.
        """

        private_ips = []
        for vnic in self.all_vnics():
            pips = vnic.all_private_ips()
            private_ips += pips
        return private_ips

    def all_volumes(self):
        """
        Get all the volumes associates with this instance.

        Returns
        -------
            list
                List of volumes OCIVolume's.
        """

        bsc = self._oci_session.get_block_storage_client()
        cc = self._oci_session.get_compute_client()

        # Note: the user may not have permission to list volumes
        # so ignoring ServiceError exceptions
        try:
            #
            # GT
            # v_att_list = oci_sdk.pagination.list_call_get_all_results(cc.list_volume_attachments, compartment_id=self._data['compartment_id'],instance_id=self._ocid).data
            v_att_list = oci_sdk.pagination.list_call_get_all_results(cc.list_volume_attachments, compartment_id=self._data.compartment_id, instance_id=self._ocid).data
        except oci_sdk.exceptions.ServiceError:
            # the user has no permission to list volumes
            OCIInstance._logger.debug('the user has no permission to list volumes', exc_info=True)
            # TODO : shouln't be an error ?
            return []

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
                vol_data = bsc.get_volume(volume_id=vol_id).data
            except oci_sdk.exceptions.ServiceError:
                OCIInstance._logger.debug('exc getting volume', exc_info=True)
                continue
            #
            # GT
            # vols.append(OCIVolume(self._oci_session, volume_data=oci_sdk.util.to_dict(vol_data), attachment_data=oci_sdk.util.to_dict(v_att_data[vol_id])))
            vols.append(OCIVolume(self._oci_session, volume_data=vol_data, attachment_data=v_att_data[vol_id]))

        return vols

    @staticmethod
    def _create_vnic_hostname_label(d_name):
        """
        Creates a hostname labrle for a vnic
        Parameter
        ---------
          d_name : display name to use
        Return
        -------
          <hostname>-<display_name>
        """
        hostname_label = '%s-%s' % (socket.gethostname(), d_name)
        # list of acceptable chars in a host name
        return ''.join([c for c in hostname_label
                        if c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'])

    def attach_vnic(self, **kargs):
        """
        Create and attach a VNIC to this device.
        Use sensible defaults:
          - private_ip: if None, the next available IP in the subnet will be picked up by OCI service.

        Parameters
        ----------
        kargs: accepted keyword
            private_ip: str
                The private IP address.
            subnet_id: str (mandatory)
                The subnet id.
            nic_index: int (optional)
                The interface index.
            display_name: str (optional)
                The name.
            assign_public_ip: bool (default False)
                Provide a public IP address if set.
            hostname_label: str (optional)
                The label.
            skip_source_dest_check: bool (default False)
                Skip source and destiantion existence check if set.
            wait: bool (default True)
                Wait for completion if set.

        Returns
        -------
            OCIVNIC
                The virtual network interface card data VNIC.

        Raises
        ------
            Exception
                On any error.
        """
        display_name = kargs.get('display_name', None)
        subnet_id = kargs.get('subnet_id')
        private_ip = kargs.get('private_ip', None)
        nic_index = int(kargs.get('nic_index', 0))
        display_name = kargs.get('display_name', None)
        assign_public_ip = kargs.get('assign_public_ip', False)
        hostname_label = kargs.get('hostname_label', None)
        skip_source_dest_check = kargs.get('skip_source_dest_check', False)
        wait = kargs.get('wait', True)

        if display_name is None and hostname_label is not None:
            display_name = hostname_label
        if hostname_label is None and display_name is not None:
            hostname_label = OCIInstance._create_vnic_hostname_label(display_name)

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
            resp = cc.attach_vnic(attach_vnic_details)
            v_att = cc.get_vnic_attachment(resp.data.id)
            if wait:
                v_att = oci_sdk.wait_until(cc, v_att, 'lifecycle_state', 'ATTACHED')
            _new_vnic = self._oci_session.get_network_client().get_vnic(v_att.data.vnic_id)
            #
            # GT
            # return OCIVNIC(self._oci_session, oci_sdk.util.to_dict(_new_vnic.data), oci_sdk.util.to_dict(v_att.data))
            return OCIVNIC(self._oci_session, _new_vnic.data, v_att.data)
        except oci_sdk.exceptions.ServiceError as e:
            OCIInstance._logger.debug('Failed to attach new VNIC', exc_info=True)
            raise Exception('Failed to attach new VNIC: %s' % e.message) from e

    def get_metadata(self, get_public_ip=False):
        """
        Get the metadata.

        Parameters
        ----------
        get_public_ip: bool
            Collect the public ip if set.

        Returns
        -------
            OCIMetadata
                The metadata.
        """
        if self._metadata is not None:
            return self._metadata

        meta = {}
        meta['instance'] = self.__dict__()

        # get vnics
        vnics = self.all_vnics()
        vnics_l = []
        for vnic in vnics:
            vnic_i = vnic.__dict__()
            vnic_a = json.loads(vnic._att_data.__str__())
            # vnic_i['nic_index'] = vnic_a['nic_index']
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

    def all_subnets(self):
        """
        Get all the subnets.

        Returns
        -------
            list
                The list of all the subnets.
        """

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        subnets = []
        try:
            #
            # GT
            # subnets_data = oci_sdk.pagination.list_call_get_all_results( nc.list_subnets, compartment_id=self._data['compartment_id'], vcn_id=self._ocid)
            subnets_data = oci_sdk.pagination.list_call_get_all_results( nc.list_subnets, compartment_id=self._data.compartment_id, vcn_id=self._ocid)
            for s_data in subnets_data.data:
                #
                # GT
                # subnets.append(OCISubnet(self._oci_session, oci_sdk.util.to_dict(s_data)))
                subnets.append(OCISubnet(self._oci_session, s_data))
        except oci_sdk.exceptions.ServiceError:
            OCIVCN._logger.debug('service error', exc_info=True)
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment

        return subnets

    def all_security_lists(self):
        """
        Get all security lists.

        Returns
        -------
            dict
                The security list.
        """

        nc = self._oci_session.get_network_client()

        # Note: the user may not have permission to list instances
        # in this compartment, so ignoring ServiceError exceptions
        security_lists = dict()
        try:
            #
            # GT
            # security_list_data = oci_sdk.pagination.list_call_get_all_results(nc.list_security_lists, compartment_id=self._data.compartment_id, vcn_id=self._ocid)
            security_list_data = oci_sdk.pagination.list_call_get_all_results(nc.list_security_lists, compartment_id=self._data.compartment_id, vcn_id=self._ocid)
            for s_data in security_list_data.data:
                #
                # GT
                # security_lists.setdefault(s_data.id, OCISecurityList(self._oci_session, oci_sdk.util.to_dict(s_data)))
                security_lists.setdefault(s_data.id, OCISecurityList(self._oci_session, s_data))
        except oci_sdk.exceptions.ServiceError:
            OCIVCN._logger.debug('service error', exc_info=True)
            # ignore these, it means the current user has no
            # permission to list the instances in the compartment
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
        #
        # GT
        # return "%s-%s" % (self._data['lifecycle_state'], self._att_data['lifecycle_state'])
        return "%s-%s" % (self._data.lifecycle_state, self._att_data.lifecycle_state)

    def get_instance(self):
        """
        Get the instance id.

        Returns
        -------
            OCIInstance
                The associated instance.
        """
        #
        # GT
        # return self._oci_session.get_instance(self._att_data['instance_id'])
        return self._oci_session.get_instance(self._att_data.instance_id) 

    def get_private_ip(self):
        """
        Get the private IP.

        Returns
        -------
            str
                The private IP address.
        """
        #
        # GT
        # return self._data['private_ip']
        return self._data.private_ip

    def get_nic_index(self):
        """
        Gets the NIC index of this vnic
        """
        #
        # GT
        # return self._att_data['nic_index']
        return self._att_data.nic_index if bool(self._att_data) else None

    def get_public_ip(self):
        """
        Get the public IP.

        Returns
        -------
            str
                The public IP address.
        """
        #
        # GT
        # return self._data['public_ip']
        return self._data.public_ip

    def is_primary(self):
        """
        Verify if the virtual network interface is a primary one.

        Returns
        -------
            bool
                True if the vnic is primay, False otherwise.
        """
        #
        # GT
        # return self._data['is_primary']
        return self._data.is_primary

    def get_mac_address(self):
        """
        Get the MAC address of the virtual network interface.

        Returns
        -------
            str
                The MAC address.
        """
        #
        # GT
        # return self._data['mac_address']
        return self._data.mac_address

    def get_subnet(self):
        """
        Get the subnet id.

        Returns
        -------
            OCISubnet
                The subnet obj.
        """
        #
        # GT
        # return self._oci_session.get_subnet(subnet_id=self._data['subnet_id'])
        return self._oci_session.get_subnet(subnet_id=self._data.subnet_id)

    def get_subnet_id(self):
        """
        Get the subnet id.

        Returns
        -------
            OCISubnet
                The subnet obj.
        """
        #
        # GT
        # return self._data['subnet_id']
        return self._data.subnet_id

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                The hostname.
        """
        #
        # GT
        # return self._data['hostname_label']
        return self._data.hostname_label

    def add_private_ip(self, private_ip=None, display_name=None):
        """
        Add a secondary private IP for this VNIC.

        Parameters
        ----------
        private_ip: str
            The IP address to add..
        display_name: str
            The name.

        Returns
        -------
            str
                The private IP address if successfully added.

        Raises
        ------
            Exception
                On failure to add.
        """
        cpid = oci_sdk.core.models.CreatePrivateIpDetails(
            display_name=display_name,
            ip_address=private_ip,
            vnic_id=self.get_ocid())
        nc = self._oci_session.get_network_client()
        try:
            private_ip = nc.create_private_ip(cpid)
        #
        # GT
            # return OCIPrivateIP(session=self._oci_session, private_ip_data=oci_sdk.util.to_dict(private_ip.data))
            return OCIPrivateIP(session=self._oci_session, private_ip_data=private_ip.data)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVNIC._logger.debug('Failed to add private IP', exc_info=True)
            raise Exception("Failed to add private IP: %s" % e.message) from e

    def find_private_ip(self, ip_address):
        """
        Find a secondary private IP based on its IP address.

        Parameters
        ----------
        ip_address: str
            The IP address to look for.

        Returns
        -------
            str
               The private IP address.
        """
        for priv_ip in self.all_private_ips():
            if priv_ip.get_address() == ip_address:
                return priv_ip
        return None

    def all_private_ips(self):
        """
        Get all secondary private IPs assigned to this VNIC.

        Returns
        -------
            list
                The list of all secondary private IPs assigned to this VNIC.
        """

        nc = self._oci_session.get_network_client()
        all_privips = []
        try:
            privips = oci_sdk.pagination.list_call_get_all_results(
                nc.list_private_ips,
                vnic_id=self.get_ocid()).data
        except oci_sdk.exceptions.ServiceError as e:
            OCIVNIC._logger.debug('sdk call failed for all_private_ips', exc_info=True)
            OCIVNIC._logger.warning('sdk call failed for all_private_ips [%s]', e.message)
            return []

        for privip in privips:
            #
            # GT
            # all_privips.append(OCIPrivateIP(session=self._oci_session, private_ip_data=oci_sdk.util.to_dict(privip)))
            all_privips.append(OCIPrivateIP(session=self._oci_session, private_ip_data=privip))
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
            Exception
                When detaching the VNIC fails.
        """
        if self.is_primary():
            raise Exception("Cannot detach the primary VNIC.")

        cc = self._oci_session.get_compute_client()
        try:
            #
            # GT
            # cc.detach_vnic(vnic_attachment_id=self._att_data['id'])
            cc.detach_vnic(vnic_attachment_id=self._att_data.id) if bool(self._att_data) else None
        except oci_sdk.exceptions.ServiceError as e:
            OCIVNIC._logger.debug( 'Failed to detach VNIC', exc_info=True)
            raise Exception("Failed to detach VNIC: %s" % e.message) from e

        if wait:
            try:
                #
                # GT
                # get_vnic_att = cc.get_vnic_attachment(self._att_data['id'])
                get_vnic_att = cc.get_vnic_attachment(self._att_data.id) if bool(self._att_data) else None
                oci_sdk.wait_until(cc, get_vnic_att, 'lifecycle_state', 'DETACHED')
            except oci_sdk.exceptions.ServiceError as e:
                OCIVNIC._logger.debug('sdk call failed for detach() [%s]', e.message, exc_info=True)

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
            nc.delete_private_ip(self.get_ocid())
            return True
        except oci_sdk.exceptions.ServiceError as e:
            OCIPrivateIP._logger.debug('delete failed', exc_info=True)
            OCIPrivateIP._logger.warning('delete failed [%s]', e.message)
            return False

    def get_vnic(self):
        """
        Get the vNIC of this private ip.

        Returns
        -------
            OCIVNIC
                The VNIC instance.
        """
        #
        # GT
        # return self._oci_session.get_vnic(self._data['vnic_id'])
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
        #
        # GT
        # return self._data['vnic_id']
        return self._data.vnic_id

    def get_address(self):
        """
        Get the IP address.

        Returns
        -------
            str
                The IP address.
        """
        #
        # GT
        # return self._data['ip_address']
        return self._data.ip_address

    def is_primary(self):
        """
        Verify if this is the primary IP.

        Returns
        -------
            bool
                True if this the primary IP address, False otherwise.
        """
        #
        # GT
        # return self._data['is_primary']
        return self._data.is_primary

    def get_hostname(self):
        """
        Get the hostname.

        Returns
        -------
            str
                THe hostname.
        """
        #
        # GT
        # return self._data['hostname_label']
        return self._data.hostname_label

    def get_subnet(self):
        """
        Get the subnet id.

        Returns
        -------
            str
                The subnet id.
        """
        #
        # GT
        # return self._oci_session.get_subnet(subnet_id=self._data['subnet_id'])
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
        #
        # GT
        # return self._data['ingress_security_rules']
        return self._data.ingress_security_rules

    def get_egress_rules(self):
        """
        Get the egress rules.

        Returns
        -------
            list
                The egress rules.
        """
        #
        # GT
        # return self._data['egress_security_rules']
        return self._data.egress_security_rules


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
        #
        # GT
        # return self._data['cidr_block']
        return self._data.cidr_block

    def is_public_ip_on_vnic_allowed(self):
        """
        Checks if public PI allowed in vnic of this subnet
        Returns:
        --------
            bool
                True if allowed
        """
        #
        # GT
        # return not self._data['prohibit_public_ip_on_vnic']
        return not self._data.prohibit_public_ip_on_vnic

    def get_vcn_id(self):
        """
        Get the virtual cn id.

        Returns
        -------
            str
               The virtual cn id.
        """
        #
        # GT
        # return self._data['vcn_id']
        return self._data.vcn_id

    def get_security_list_ids(self):
        """
        Get the security list ids.

        Returns
        -------
            list of security list ids.
        """
        #
        # GT
        # return self._data['security_list_ids']
        return self._data.security_list_ids

    def get_domain_name(self):
        """
        Get the domain name.

        Returns
        -------
            str
                The domain name.
        """
        #
        # GT
        # return self._data['subnet_domain_name']
        return self._data.subnet_domain_name

    def all_vnics(self):
        """
        Get a list of all OCIVNIC objects that are in this subnet.


        Returns
        -------
            list
                List of all virtual network interfaces OCIVNIC's.
        """
        #
        # GT
        # compartment = self._oci_session.get_compartment(ocid=self._data['compartment_id'])
        compartment = self._oci_session.get_compartment(ocid=self._data.compartment_id)
        if compartment is None:
            OCISubnet._logger.warning('all_vnics() cannot get compartment')
            return []
        vnics = []
        for vnic in compartment.all_vnics():
            if vnic.get_subnet_id() == self.get_ocid():
                vnics.append(vnic)

        return vnics

    def is_suitable_for_ip(self, ipaddr):
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
            raise Exception('Failed to parse IP address %s' % ipaddr)
        if int(match.group(1)) > 255 or \
           int(match.group(2)) > 255 or \
           int(match.group(3)) > 255 or \
           int(match.group(4)) > 255:
            raise Exception('Invalid IP address: %s' % ipaddr)

        ipint = ((int(match.group(1)) * 256 +
                  int(match.group(2))) * 256 +
                 int(match.group(3))) * 256 + int(match.group(4))
        #
        # GT
        # match = re.match(r'([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)/([0-9]+)', self._data['cidr_block'])
        match = re.match(r'([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)/([0-9]+)', self._data.cidr_block)
        if match is None:
            #
            # GT
            # raise Exception('Failed to parse cidr block %s' % self._data['cidr_block'])
            raise Exception('Failed to parse cidr block %s' % self._data.cidr_block)

        cidripint = ((int(match.group(1)) * 256 +
                      int(match.group(2))) * 256 +
                     int(match.group(3))) * 256 + int(match.group(4))
        cidrmask =\
            int("1" * int(match.group(5)) + "0" * (32 - int(match.group(5))), 2)

        return (ipint & cidrmask) == cidripint

    def all_private_ips(self):
        """
        Get the list of secondary private IPs in this Subnet.


        Returns
        -------
            list
                List of secondary private IP's OCIPrivateIP.
        """

        nc = self._oci_session.get_network_client()
        all_privips = []
        try:
            privips = oci_sdk.pagination.list_call_get_all_results(
                nc.list_private_ips,
                subnet_id=self.get_ocid()).data
        except oci_sdk.exceptions.ServiceError as e:
            OCISubnet._logger.debug(
                'all_private_ips() sdk call failed', exc_info=True)
            OCISubnet._logger.warning('all_private_ips() sdk call failed [%s]', e.message)
            return []
        for privip in privips:
            #
            # GT
            # all_privips.append(OCIPrivateIP(session=self._oci_session, private_ip_data=oci_sdk.util.to_dict(privip)))
            all_privips.append(OCIPrivateIP(session=self._oci_session, private_ip_data=privip))
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
            #
            # GT
            # assert self.att_data['lifecycle_state'] in  OCI_ATTACHMENT_STATE.__members__, 'unknown state returned'
            assert self.att_data.lifecycle_state in  OCI_ATTACHMENT_STATE.__members__, 'unknown state returned'
            # self.volume_lifecycle = OCI_ATTACHMENT_STATE[self.att_data['lifecycle_state']]
            self.volume_lifecycle = OCI_ATTACHMENT_STATE[self.att_data.lifecycle_state]

    def __str__(self):
        """
        Override the string representation of the volume.

        Returns
        -------
            str
                The string representation of the OCIVolume object.
        """
        return "Volume %s" % OCIAPIAbstractResource.__str__(self)

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
                The format the size should be returned. Current options are one of OCI_VOLUME_SIZE_FMT value as string
                - OCI_VOLUME_SIZE_FMT.HUMAN: human readable.
                - OCI_VOLUME_SIZE_FMT.GB: Gigabytes
                - OCI_VOLUME_SIZE_FMT.MB: Megabytes

        Returns
        -------
            str or in
                The size of the volume.
        """
        # for compatibility raseon we check against key as string
        assert format_str in [OCI_VOLUME_SIZE_FMT.HUMAN.name,
                              OCI_VOLUME_SIZE_FMT.GB.name, OCI_VOLUME_SIZE_FMT.MB.name], 'wrong format'

        if (format_str is None) or (format_str == OCI_VOLUME_SIZE_FMT.GB.name):
        #
        # GT
        #    return self._data['size_in_gbs']
            return self._data.size_in_gbs
        if format_str == OCI_VOLUME_SIZE_FMT.MB.name:
        #
        # GT
        #    return self._data['size_in_mbs']
            return self._data.size_in_mbs
        #
        # GT
        # return str(self._data['size_in_gbs']) + "GB"
        return str(self._data.size_in_gbs) + "GB"

    def get_user(self):
        """
        Get the username.

        Returns
        -------
            str
                The username on success, None otherwise.
        """
        #
        # GT
        # return self.att_data['chap_username']
        return self.att_data.chap_username

    def get_password(self):
        """
        Get the pass key.

        Returns
        -------
            str
               The chap secret on success, None otherwise.
        """
        #
        # GT
        # return self.att_data['chap_secret']
        return self.att_data.chap_secret

    def get_portal_ip(self):
        """
        Get the IP address of the portal.

        Returns
        -------
            str
                The IPv4 address on success, None otherwise.
        """
        #
        # GT
        # return self.att_data['ipv4']
        return self.att_data.ipv4

    def get_portal_port(self):
        """
        Get the attach port.

        Returns
        -------
            int
                The port number on success, None otherwise.
        """
        #
        # GT
        # return self.att_data['port']
        return self.att_data.port

    def get_instance(self):
        """
        Get the instance information.

        Returns
        -------
            OCIInstance
                The instance data on success, None otherwise.
        """
        #
        # GT
        # return self._oci_session.get_instance(self.att_data['instance_id'])
        return self._oci_session.get_instance(self.att_data.instance_id)

    def get_iqn(self):
        """
        Get the iSCSI qualified name.

        Returns
        -------
            str
                The iSCSI qualified name on succes, None on failure.
        """
        #
        # GT
        # return self.att_data['iqn']
        return self.att_data.iqn

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
             Exception
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
            vol_att = cc.attach_volume(av_det)
            if wait:
                get_attachement = cc.get_volume_attachment(vol_att.data.id)
                oci_sdk.wait_until(cc, get_attachement, 'lifecycle_state', 'ATTACHED')

            return self._oci_session.get_volume(vol_att.data.volume_id)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVolume._logger.debug(
                'Failed to attach volume', exc_info=True)
            raise Exception('Failed to attach volume') from e

    def detach(self, wait=True):
        """
        Detach this volume.

        Parameters
        ----------
        wait : bool, optional
            Wait for completion if set.
        Raises
        ------
        Exception
            call to OCI SDK to detach the volume has failed

        Returns
        -------
            bool
                True if volume is detached, False otherwise.

        Raises
        ------
            Exception
                Call to OCI SDK to detach the volume has failed.
        """
        if not self.is_attached():
            OCIVolume._logger.debug('skip detach, volume not attached')
            return True

        cc = self._oci_session.get_compute_client()

        try:
            #
            # GT
            # cc.detach_volume(volume_attachment_id=self.att_data['id'])
            cc.detach_volume(volume_attachment_id=self.att_data.id)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVolume._logger.debug('Failed to detach volume', exc_info=True)
            raise Exception('Failed to detach volume: %s' % e.message) from e

        _tries = 3

        if wait:
            #
            # GT
            #get_vol_attachment = cc.get_volume_attachment(self.att_data['id'])
            get_vol_attachment = cc.get_volume_attachment(self.att_data.id)
            oci_sdk.wait_until(cc, get_vol_attachment, 'lifecycle_state', 'DETACHED')

        self.att_data = None
        self.volume_lifecycle = OCI_ATTACHMENT_STATE.NOT_ATTACHED
        return True

    def destroy(self):
        """
        Destroy the volume.

        Returns
        -------
            No return value.

        Raises
        ------
            Exception
                On any error.
        """
        if self.is_attached():
            raise Exception("Volume is currently attached, cannot destroy.")

        bsc = self._oci_session.get_block_storage_client()
        try:
            bsc.delete_volume(volume_id=self._ocid)
        except oci_sdk.exceptions.ServiceError as e:
            OCIVolume._logger.debug('Failed to destroy volume', exc_info=True)
            raise Exception("Failed to destroy volume: %s" % e.message) from e
