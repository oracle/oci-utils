# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle sometype formatted virtual disk images, intended as a template.
"""
import logging
import os
import struct

from oci_utils.migrate import migrate_tools
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

_logger = logging.getLogger('oci-utils.some-img-type')


class SomeTypeHead(DeviceData):
    """
    Class to analyse header of sometype image file; ref whatever..

    Attributes
    ----------
        filename: str
            The full path of the vmdk image file.
        stat: tuple
            The image file stat data.
        img_tag: str
            The bare file name.
        somehead_dict: dict
            The SomeType file header as a dictionary.
    """
    # sometype header definition:
    uint32_t = 'I'  # 32bit unsigned int
    uint64_t = 'Q'  # 64bit unsigned long
    header2_structure = [[uint32_t, '%#x', 'magic'],
                         [uint32_t, '%d', 'version'],

                         ]

    # struct format string
    sometypehead_fmt = '>' + ''.join(f[0] for f in header2_structure)
    head_size = struct.calcsize(sometypehead_fmt)

    def __init__(self, filename):
        """
        Initialisation of the sometype header analysis.

        Parameters
        ----------
        filename: str
            Full path of the qcow2 image file.
        """
        super(SomeTypeHead, self).__init__(filename)
        _logger.debug('sometype header size: %d bytes' % self.head_size)

        try:
            with open(self._fn, 'rb') as f:
                head_bin = f.read(self.head_size)
                _logger.debug('%s header successfully read' % self._fn)
        except Exception as e:
            _logger.critical('Failed to read header of %s: %s'
                             % (self._fn, str(e)))
            raise OciMigrateException('Failed to read the header of %s: %s'
                                      % (self._fn, str(e)))

        sometypeheader = struct.unpack(SomeTypeHead.sometypehead_fmt, head_bin)

        self.stat = os.stat(self._fn)
        self.img_tag = os.path.splitext(os.path.split(self._fn)[1])[0]
        self.somehead_dict = dict((name[2], sometypeheader[i])
                                  for i, name
                                  in enumerate(SomeTypeHead.header2_structure))
        self.img_header = dict()
        self.img_header['head'] = self.somehead_dict
        migrate_tools.result_msg(msg='Got image %s header' % filename, result=True)
        #
        # mount the image using the nbd
        try:
            self.devicename = self.mount_img()
            _logger.debug('Image data %s' % self.devicename)
            migrate_tools.result_msg(msg='Mounted %s' % self.devicename,
                                     result=True)
            deviceinfo = self.handle_image()
        except Exception as e:
            _logger.critical('error %s' % str(e))
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
