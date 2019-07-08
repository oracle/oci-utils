#!/usr/bin/env python2.7

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle sometype formatted virtual disk images, intended as a template.
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
typedef struct SometypeHeader {
      uint32_t magic;
      uint32_t version;
      ...
  } SometypeHeader;
"""

format_data = {'01234567': {'name': 'sometype',
                            'module': 'sometype',
                            'clazz': 'SomeTypeHead',
                            'prereq': {'MAX_IMG_SIZE_GB': 300.0}}}


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    gen_tools.prog_msg(__name__)


class SomeTypeHead(DeviceData):
    """
    Class to analyse header of sometype image file; ref whatever..

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
    # sometype header definition:
    uint32_t = 'I'  # 32bit unsigned int
    uint64_t = 'Q'  # 64bit unsigned long
    header2_structure = [[uint32_t, '%#x', 'magic'],
                         [uint32_t, '%d', 'version'],

                         ]

    # struct format string
    sometypehead_fmt = '>' + ''.join(f[0] for f in header2_structure)
    _logger = logging.getLogger('oci-image-migrate.Qcow2Head')

    def __init__(self, filename, logger=None):
        """
        Initialisation of the sometype header analysis.

        Parameters
        ----------
        filename: str
            Full path of the qcow2 image file.
        logger: loggername
            The logging specification.
        """
        super(SomeTypeHead, self).__init__(filename, logger)
        head_size = struct.calcsize(SomeTypeHead.qcowhead_fmt)

        self._logger.info('sometype header size: %d bytes' % head_size)

        try:
            with open(self.fn, 'rb') as f:
                head_bin = f.read(head_size)
                self._logger.debug('%s header successfully read' % self.fn)
        except Exception, e:
            self._logger.critical(
                'Failed to read header of %s: %s' % (self.fn, str(e)))
            raise OciMigrateException('Failed to read the header of %s: %s' % (self.fn, str(e)))

        sometypeheader = struct.unpack(SomeTypeHead.sometypehead_fmt, head_bin)

        self.stat = os.stat(self.fn)
        self.img_tag = os.path.splitext(os.path.split(self.fn)[1])[0]
        self.somehead_dict = dict((name[2], sometypeheader[i]) for i, name in
                               enumerate(SomeTypeHead.header2_structure))
        self.img_header = dict()
        self.img_header['head'] = self.somehead_dict
        gen_tools.result_msg('Got image %s header' % filename)
        #
        # mount the image using the nbd
        try:
            self.devicename = self.mount_img()
            self._logger.debug('Image data %s' % self.devicename)
            gen_tools.result_msg('Mounted %s' % self.devicename)
            deviceinfo = self.handle_image()
        except Exception as e:
            self._logger.critical('error %s' % str(e))
            raise OciMigrateException(str(e))


    def show_header(self):
        """
        Lists the header contents formatted.

        Returns
        -------
            No return value.
        """
        pass

    def image_size(self):
        """
        Get the size of the image file.

        Returns
        -------
            tuple: (float, float)
                physical file size, logical file size
        """
        pass

    def image_supported(self, image_defs):
        """
        Verifies if the image file is supported for migration to the Oracle
        cloud infrastructure.

        Returns
        -------
            bool: True on success, False otherwise.
            str:  Eventual message on success or failure.
        """
        pass

    def image_data(self):
        """
        Collect data about contents of the image file.

        Returns
        -------
            bool: True on success, False otherwise;
            dict: The image data.
        """
        pass

    def type_specific_prereq_test(self):
        """
        Verify the prerequisites specific for the image type.

        Returns
        -------
            bool: True or False.
            str : Message
        """
        pass