#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle QCOW2 formatted virtual disk images.
"""
import logging
import os
import struct
import sys

# for the sake of testing
sys.path.append('/omv/data/git_pycharm/oci-utils/lib')
from oci_utils.migrate import gen_tools
from oci_utils.migrate.migrate_utils import gigabyte as gigabyte
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate.imgdevice import DeviceData
from oci_utils.migrate.migrate_utils import OciMigrateException

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
                            'prereq': {'MAX_IMG_SIZE_GB': 300.0}}}


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    gen_tools.result_msg(__name__)


class Qcow2Head(DeviceData):
    """
    Class to analyse header of qcow2 image file

    Attributes
    ----------
        filename: str
            The full path of the vmdk image file.
        logger: logger
            The logger.
        stat: tuple
            The image file stat data.
        img_tag: str
            The bare file name.
        qcowhead_dict: dict
            The VMDK file header as a dictionary.
    """
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

    # struct format string
    qcowhead_fmt = '>' + ''.join(f[0] for f in header2_structure)
    _logger = logging.getLogger('oci-image-migrate.Qcow2Head')

    def __init__(self, filename, logger=None):
        """
        Initialisation of the qcow2 header analysis.

        Parameters
        ----------
        filename: str
            Full path of the qcow2 image file.
        logger: loggername
            The logging specification.
        """
        super(Qcow2Head, self).__init__(filename, logger)
        head_size = struct.calcsize(Qcow2Head.qcowhead_fmt)

        self._logger.info('qcow2 header size: %d bytes' % head_size)

        try:
            with open(self.fn, 'rb') as f:
                head_bin = f.read(head_size)
                self._logger.debug('%s header successfully read' % self.fn)
        except Exception as e:
            self._logger.critical(
                'Failed to read header of %s: %s' % (self.fn, str(e)))
            raise OciMigrateException(
                'Failed to read the header of %s: %s' % (self.fn, str(e)))

        qcow2header = struct.unpack(Qcow2Head.qcowhead_fmt, head_bin)

        self.stat = os.stat(self.fn)
        self.img_tag = os.path.splitext(os.path.split(self.fn)[1])[0]
        self.qcowhead_dict = dict((name[2], qcow2header[i]) for i, name in
                                  enumerate(Qcow2Head.header2_structure))
        self.img_header = dict()
        self.img_header['head'] = self.qcowhead_dict
        gen_tools.result_msg('Got image %s header' % filename)

    def show_header(self):
        """
        Lists the header contents formatted.

        Returns
        -------
            No return value.
        """
        gen_tools.result_msg('\n  %30s\n  %30s'
                             % ('QCOW2 file header data', '-'*30),
                             prog=False)
        for f in Qcow2Head.header2_structure:
            gen_tools.result_msg(''.join(["  %-30s" % f[2], f[1]
                                          % self.qcowhead_dict[f[2]]]),
                                 prog=False)

    def image_size(self):
        """
        Get the size of the image file.

        Returns
        -------
            tuple: (float, float)
                physical file size, logical file size
        """

        img_sz = {'physical': float(self.stat.st_size)/gigabyte,
                  'logical': float(self.qcowhead_dict['size'])/gigabyte}

        gen_tools.result_msg(
            'Image size: physical %10.2f GB, logical %10.2f GB' %
            (img_sz['physical'], img_sz['logical']))
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
        supp = True
        prerequisites = image_defs['prereq']
        msg = ''
        sizes = self.image_size()
        if sizes['logical'] > prerequisites['MAX_IMG_SIZE_GB']:
            msg += 'Size of the image %.2f GB exceeds the maximum allowed ' \
                   'size of %.2f GB.\n' % \
                   (sizes['logical'], prerequisites['MAX_IMG_SIZE_GB'])
            supp = False
        else:
            msg += 'Image size of %.2f GB below maximum allowed size ' \
                   'of %.2f GB, OK.\n' % \
                   (sizes['logical'],
                    prerequisites['MAX_IMG_SIZE_GB'])
        return supp, msg

    def image_data(self):
        """
        Collect data about contents of the image file.

        Returns
        -------
            bool: True on success, False otherwise;
            dict: The image data.
        """
        self._logger.debug('image data: %s' % self.fn)
        # self.devicename = None
        #
        # initialise the dictionary for the image data
        self.img_info['img_name'] = self.fn
        self.img_info['img_type'] = 'qcow2'
        self.img_info['img_header'] = self.img_header
        self.img_info['img_size'] = self.image_size()
        #
        # mount the image using the nbd.
        try:
            result = self.handle_image()
        except Exception as e:
            self._logger.critical('error %s' % str(e))
            raise OciMigrateException(str(e))
        return result, self.img_info

    def type_specific_prereq_test(self):
        """
        Verify the prerequisites specific for the image type from the header.

        Returns
        -------
            bool: True or False.
            str : Message
        """
        prereqs = format_data['514649fb']['prereq']
        failmsg = ''
        #
        # size:
        thispass = True
        if self.img_info['img_size']['logical'] > prereqs['MAX_IMG_SIZE_GB']:
            self._logger.critical(
                'Image size %8.2f GB exceeds maximum allowed %8.2f GB'
                % (prereqs['MAX_IMG_SIZE_GB'],
                   self.img_info['img_size']['logical']))
            failmsg += '\n  Image size %8.2f GB exceeds maximum allowed ' \
                       '%8.2f GB' % (prereqs['MAX_IMG_SIZE_GB'],
                                     self.img_info['img_size']['logical'])
            thispass = False
        else:
            failmsg += '\n  Image size %8.2f GB meets maximum allowed size ' \
                       'of %8.2f GB' % (self.img_info['img_size']['logical'],
                                        prereqs['MAX_IMG_SIZE_GB'])

        return thispass, failmsg