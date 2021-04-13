# oci-utils
#
# Copyright (c) 2019, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle QCOW2 formatted virtual disk images.
"""
import logging
import os
import struct

from oci_utils.migrate import result_msg
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.imgdevice import DeviceData
from oci_utils.migrate.migrate_data import gigabyte

"""
  typedef struct QCowHeader {
      uint32_t magic;
      uint32_t version;
      uint64_t backing_file_offset;
      uint32_t backing_file_size;
      uint32_t cluster_bits;
      uint64_t size; /* in bytes */
      uint32_t crypt_method;
      uint32_t l1_size;
      uint64_t l1_table_offset;
      uint64_t refcount_table_offset;
      uint32_t refcount_table_clusters;
      uint32_t nb_snapshots;
      uint64_t snapshots_offset;
  } QCowHeader;
"""

format_data = {'514649fb': {'name': 'qcow2',
                            'module': 'qcow2',
                            'clazz': 'Qcow2Head',
                            'prereq': {'MAX_IMG_SIZE_GB': 400.0}}}

_logger = logging.getLogger('oci-utils.qcow2')


class Qcow2Head(DeviceData):
    """
    Class to analyse header of qcow2 image file

    Attributes
    ----------
        stat: tuple
            The image file stat data.
        img_tag: str
            The bare file name.
        qcowhead_dict: dict
            The qcow2 file header as a dictionary.
    """
    #
    # qcow2 header definition:
    uint32_t = 'I'  # 32bit unsigned int
    uint64_t = 'Q'  # 64bit unsigned long
    header2_structure = [[uint32_t, '%#x', 'magic'],
                         [uint32_t, '%d',  'version'],
                         [uint64_t, '%#x', 'backing_file_offset'],
                         [uint32_t, '%#x', 'backing_file_size'],
                         [uint32_t, '%d',  'cluster_bits'],
                         [uint64_t, '%d',  'size'],
                         [uint32_t, '%d',  'crypt_method'],
                         [uint32_t, '%d',  'l1_size'],
                         [uint64_t, '%#x', 'l1_table_offset'],
                         [uint64_t, '%d',  'refcount_table_offset'],
                         [uint32_t, '%d',  'refcount_table_clusters'],
                         [uint32_t, '%d',  'nb_snapshots'],
                         [uint64_t, '%#x', 'snapshots_offset'],
                         [uint64_t, '%#x', 'incompatible_features'],
                         [uint64_t, '%#x', 'compatible_features'],
                         [uint64_t, '%#x', 'autoclear_features'],
                         [uint32_t, '%d',  'refcount_order'],
                         [uint32_t, '%d',  'header_length']]
    #
    # struct format string
    qcowhead_fmt = '>' + ''.join(f[0] for f in header2_structure)
    head_size = struct.calcsize(qcowhead_fmt)

    def __init__(self, filename):
        """
        Initialisation of the qcow2 header analysis.

        Parameters
        ----------
        filename: str
            Full path of the qcow2 image file.
        """
        _logger.debug('qcow2 header size: %d bytes', self.head_size)
        super().__init__(filename)
        head_size = struct.calcsize(Qcow2Head.qcowhead_fmt)

        try:
            with open(self._fn, 'rb') as f:
                head_bin = f.read(head_size)
                _logger.debug('%s header successfully read', self._fn)
        except Exception as e:
            _logger.critical('   Failed to read header of %s: %s', self._fn, str(e))
            raise OciMigrateException('Failed to read the header of %s' % self._fn) from e

        qcow2header = struct.unpack(Qcow2Head.qcowhead_fmt, head_bin)

        self.stat = os.stat(self._fn)
        self.img_tag = os.path.splitext(os.path.split(self._fn)[1])[0]
        self.qcowhead_dict = dict((name[2], qcow2header[i]) for i, name in
                                  enumerate(Qcow2Head.header2_structure))
        self.img_header = dict()
        self.img_header['head'] = self.qcowhead_dict
        result_msg(msg='Got image %s header' % filename, result=False)

    def show_header(self):
        """
        Lists the header contents formatted.

        Returns
        -------
            No return value.
        """
        result_msg(msg='\n  %30s\n  %30s' % ('QCOW2 file header data', '-'*30), result=False)
        for f in Qcow2Head.header2_structure:
            result_msg(msg=''.join(["  %-30s" % f[2], f[1] % self.qcowhead_dict[f[2]]]), result=False)

    def image_size(self):
        """
        Get the size of the image file.

        Returns
        -------
            dict: {'physical': float,
                   'logical' : float}
                physical file size, logical file size
        """

        img_sz = {'physical': float(self.stat.st_size)/gigabyte,
                  'logical': float(self.qcowhead_dict['size'])/gigabyte}

        result_msg(msg='Image size: physical %10.2f GB, logical %10.2f GB'
                       % (img_sz['physical'], img_sz['logical']), result=True)
        return img_sz

    def image_supported(self, image_defs):
        """
        Verifies if the image file is supported for migration to the Oracle
        cloud infrastructure.

        Returns
        -------
            bool: True on success, False otherwise.
            str:  Eventual message on success or failure.
        """
        _logger.debug('__ Image support.')
        supp = True
        prerequisites = image_defs['prereq']
        msg = ''
        sizes = self.image_size()
        if sizes['logical'] > prerequisites['MAX_IMG_SIZE_GB']:
            msg += 'Size of the image %.2f GB exceeds the maximum allowed size of %.2f GB.\n' \
                   % (sizes['logical'], prerequisites['MAX_IMG_SIZE_GB'])
            supp = False
        else:
            msg += 'Image size of %.2f GB below maximum allowed size ' \
                   'of %.2f GB, OK.\n' % \
                   (sizes['logical'], prerequisites['MAX_IMG_SIZE_GB'])
        return supp, msg

    def image_data(self):
        """
        Collect data about contents of the image file.

        Returns
        -------
            bool: True on success, False otherwise;
            dict: The image data.
        """
        _logger.debug('__ Image data: %s', self._fn)
        #
        # initialise the dictionary for the image data
        self.image_info['img_name'] = self._fn
        self.image_info['img_type'] = 'qcow2'
        self.image_info['img_header'] = self.img_header
        self.image_info['img_size'] = self.image_size()
        #
        # mount the image using the nbd.
        try:
            result = self.handle_image()
        except Exception as e:
            _logger.critical('   ERROR %s', str(e))
            raise OciMigrateException('Failed:') from e
        return result, self.image_info

    def type_specific_prereq_test(self):
        """
        Verify the prerequisites specific for the image type from the header.

        Returns
        -------
            bool: True or False.
            str : Message
        """
        _logger.debug('__ Specific prerequisites.')
        prereqs = format_data['514649fb']['prereq']
        failmsg = ''
        #
        # size:
        passed_requirement = True
        if self.image_info['img_size']['logical'] > prereqs['MAX_IMG_SIZE_GB']:
            _logger.critical('   Image size %8.2f GB exceeds maximum allowed %8.2f GB',
                             prereqs['MAX_IMG_SIZE_GB'], self.image_info['img_size']['logical'])
            failmsg += '\n  Image size %8.2f GB exceeds maximum allowed %8.2f GB' \
                       % (prereqs['MAX_IMG_SIZE_GB'], self.image_info['img_size']['logical'])
            passed_requirement = False
        else:
            failmsg += '\n  Image size %8.2f GB meets maximum allowed size of %8.2f GB' \
                       % (self.image_info['img_size']['logical'], prereqs['MAX_IMG_SIZE_GB'])

        return passed_requirement, failmsg
