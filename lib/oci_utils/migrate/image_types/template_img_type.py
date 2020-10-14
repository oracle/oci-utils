# oci-utils
#
# Copyright (c) 2019, 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle template type formatted virtual disk images.
"""
import logging
import os
import struct

from oci_utils.migrate import result_msg
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.imgdevice import DeviceData

"""  
typedef struct Template_Img {
      uint32_t magic;
      uint32_t version;
      ...
  } Template_Img;
"""

format_data = {'01234567': {'name': 'templatetype',
                            'module': 'templatetype',
                            'clazz': 'TemplateTypeHead',
                            'prereq': {'MAX_IMG_SIZE_GB': 300.0}}}

_logger = logging.getLogger('oci-utils.template-img-type')


class TemplateTypeHead(DeviceData):
    """
    Class to analyse header of templatetype image file; ref whatever..

    Attributes
    ----------
        filename: str
            The full path of the template image file.
        stat: tuple
            The image file stat data.
        img_tag: str
            The bare file name.
        templatehead_dict: dict
            The SomeType file header as a dictionary.
    """
    #
    # templatetype header definition:
    uint32_t = 'I'  # 32bit unsigned int
    uint64_t = 'Q'  # 64bit unsigned long
    header2_structure = [[uint32_t, '%#x', 'magic'],
                         [uint32_t, '%d', 'version'],

                         ]
    #
    # struct format string
    templatetypehead_fmt = '>' + ''.join(f[0] for f in header2_structure)
    head_size = struct.calcsize(templatetypehead_fmt)

    def __init__(self, filename):
        """
        Initialisation of the templatetype header analysis.

        Parameters
        ----------
        filename: str
            Full path of the template_type image file.
        """
        super().__init__(filename)
        _logger.debug('templatetype header size: %d bytes', self.head_size)

        try:
            with open(self._fn, 'rb') as f:
                head_bin = f.read(self.head_size)
                _logger.debug('%s header successfully read', self._fn)
        except Exception as e:
            _logger.critical('   Failed to read header of %s: %s', self._fn, str(e))
            raise OciMigrateException('Failed to read the header of %s' % self._fn) from e

        templatetypeheader = struct.unpack(TemplateTypeHead.templatetypehead_fmt, head_bin)

        self.stat = os.stat(self._fn)
        self.img_tag = os.path.splitext(os.path.split(self._fn)[1])[0]
        self.templatehead_dict = \
            dict((name[2], templatetypeheader[i]) for i, name in enumerate(TemplateTypeHead.header2_structure))
        self.img_header = dict()
        self.img_header['head'] = self.templatehead_dict
        result_msg(msg='Got image %s header' % filename, result=False)
        #
        # mount the image using the nbd
        try:
            self.device_name = self.mount_img()
            _logger.debug('Image data %s', self.device_name)
            result_msg(msg='Mounted %s' % self.device_name, result=False)
            deviceinfo = self.handle_image()
        except Exception as e:
            _logger.critical('   Error %s', str(e))
            raise OciMigrateException('Failed') from e

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
