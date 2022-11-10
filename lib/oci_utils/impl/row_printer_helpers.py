# Copyright (c) 2021, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
import sys
from oci_utils.impl.row_printer import get_row_printer_impl

_logger = logging.getLogger("oci-utils.row_printer_helpers")

__all__ = ['initialise_column_lengths',
           'get_length',
           'get_yesno',
           'get_value_data_list',
           'get_value_data',
           'list_to_str',
           'print_data',
           'print_vnic_data']


class IndentPrinter:
    """
    Printer used in ColumnsPrinter.
    Print rows with indentation to stdout
    """

    def __init__(self, howmany):
        """ How many spaces indentation
        """
        self.hm = howmany

    def write(self, s):
        """ Write string to stdout
        """
        sys.stdout.write('  '*self.hm + s)


def initialise_column_lengths(coldata):
    """
    Initialise the columns structure.

    Parameters
    ----------
    coldata: dict
        The column structure.

    Returns
    -------
        dict: the updated columns structure, added initial lengths of the columns, determined by the header lenght.
    """
    for key, _ in coldata.items():
        coldata[key]['collen'] = len(coldata[key]['head'])
    return coldata


def get_length(val):
    """
    Return the length of the value of a variable.

    Parameters
    ----------
    val:
        The variable.

    Returns
    -------
        int: the length
    """
    if val is None:
        return 3
    if isinstance(val, str):
        return len(val)
    if isinstance(val, int):
        return len('%8s' % val)
    if isinstance(val, float):
        return len('%15.4f' % val)
    if isinstance(val, bool):
        return 5
    return 0


def get_yesno(yesno):
    """
    Convert a yes/no id to yes/no string.

    Parameters
    ----------
    yesno: int
        The yes/no id

    Returns
    -------
        str: [yes|no]
    """
    return 'yes' if yesno == 1 else 'no'


def get_value_data_list(obj_list, func):
    """
    Get the attributes of a list of objects.

    Parameters
    ----------
    obj_list: list
        List of objects.
    func: str
        Attribute.

    Returns
    -------
        list: list of attributes.
    """
    _logger.debug('_get_value_data_list')
    result = []
    for ob in obj_list:
        result.append(getattr(ob, func)())
    return result


def get_value_data(struct, data):
    """
    Return the value and length of an attribute function of a struct.

    Parameters
    ----------
    struct: dict
        The data.
    data: dict
        The data structure.

    Returns
    -------
        tuple:value and length
    """
    _logger.debug('_get_value_data')
    func = data['func'] if 'func' in data else None
    item = data['item'] if 'item' in data else None
    lfunc = data['lfunc'] if 'lfunc' in data else None
    attrib = data['attrib'] if 'attrib' in data else None
    val = None
    value = '-'
    if func is not None:
        # struct is an object
        try:
            if isinstance(func, list):
                _logger.debug('list: %s', func)
                # recursive get attributes.
                st = struct
                for fa in func:
                    if isinstance(st, list):
                        v1 = get_value_data_list(st, fa)
                    else:
                        v1 = getattr(st, fa)()
                    st = v1
                val = st
            elif isinstance(func, tuple):
                _logger.debug('tuple: %s', func)
                # get all attributes in tuple and return as a (b c d)
                st = struct
                v = []
                for fa in func:
                    v.append(getattr(st, fa)())
                val = str(v[0]) + '(' + ' '.join(map(str, v[1:])) + ')'
            else:
                # just exec the function
                _logger.debug('function: %s', func)
                # val = getattr(struct, func)(struct)
                val = getattr(struct, func)()
        except Exception as e:
            _logger.debug('Failed to collect %s: %s', func, str(e))
            return '-', 1

    elif item is not None:
        # struct is a dict,
        try:
            val = struct[item]
        except Exception as e:
            _logger.debug('Failed to collect %s: %s', item, str(e))
            return '-', 1

    elif lfunc is not None:
        # execute a method
        # todo needs to be corrected
        try:
            val = locals()[data['lfunc']](struct)
        except Exception as e:
            _logger.debug('Failed to collect %s: %s', lfunc, str(e))
            return '-', 1

    elif attrib is not None:
        # get an attriburte
        try:
            val = getattr(struct, attrib)
        except Exception as e:
            _logger.debug('Failed to collect %s: %s', attrib, str(e))
            return '-', 1


    if bool(val):
        if data['type'] == 'str':
            value = data['convert'](val) if 'convert' in data else val
        if data['type'] == 'int':
            value = data['convert'](val) if 'convert' in data else val
        if data['type'] == 'float':
            value = data['convert'](val) if 'convert' in data else val
        if data['type'] == 'list':
            value = data['convert'](val[data['index']]) if 'convert' in data else val[data['index']]
        if data['type'] == 'yesno':
            value = get_yesno(val)
        if data['type'] == 'bool':
            value = data['convert'](val) if 'convert' in data else val
        if value is None:
            value = '-'
        _logger.debug('value: %s %d', str(value), get_length(value))
        return value, get_length(value)

    return '-', 4


def list_to_str(somelist, delimiter=' '):
    """
    Convert a list of strings to a delimeter separated string.

    Parameters
    ----------
    somelist: list
        The list of strings.
    delimiter: str
        The delimiter.

    Returns
    -------
        str: the string of list.
    """
    if somelist is not None:
        if isinstance(somelist, list):
            return delimiter.join(somelist)
        return str(somelist)
    return None


def print_data(title, structure, data, mode, printer_type=None, truncate=False):
    """
    Display the data described by structure in mode.

    Parameters
    ----------
    title: str
        The title
    structure: dict
        The structure of the data.
    data: list
        The data.
    printer_type: printerclass
        Modifier.
    mode: str
        The output mode.
    truncate: bool
        Truncate the data if True

    Returns
    -------
        No return value.
    """
    _columns = list()
    for key, value in structure.items():
        _columns.append([value['head'], value['collen']+2, key])
    #
    printerKlass = get_row_printer_impl(mode)
    printer = printerKlass(title=title, columns=_columns, text_truncate=truncate) if printer_type is None \
        else printerKlass(title=title, columns=_columns, printer=printer_type, text_truncate=truncate)
    printer.printHeader()
    #
    # print
    for _sp in data:
        printer.rowBreak()
        printer.printRow(_sp)
    printer.printFooter()
    printer.finish()


def print_vnic_data(title, structure, structure_secondary, data, mode, truncate):
    """
    Display the data described by structure in mode.

    Parameters
    ----------
    title: str
        The title
    structure: dict
        The structure of the data.
    structure_secondary: dict
        The structure of the secondary addr.
    data: list
        The data.
    mode: str
        The output mode.
    truncate: bool
        Truncate the data if set to True
    Returns
    -------
        No return value.
    """
    _columns = list()
    for key, value in structure.items():
        _columns.append([value['head'], value['collen']+2, key])
    #
    printerKlass = get_row_printer_impl(mode)
    printer = printerKlass(title=title, columns=_columns)
    printer.printHeader()
    #
    # print
    for _sp in data:
        details4 = _sp.pop('ipv4', None)
        details6 = _sp.pop('ipv6', None)
        printer.rowBreak()
        printer.printRow(_sp)
        # if bool(details4):
        #     print_data('ipv4 secondary ip', structure_secondary,
        #     details4, mode=mode, printer_type=IndentPrinter(3), truncate=truncate)
        # if bool(details6):
        #     print_data('ipv6 secondary ip', structure_secondary,
        #     details6, mode=mode, printer_type=IndentPrinter(3), truncate=truncate)
        if bool(details4):
            details = details4
        else:
            details = []
        if bool(details6):
            details.extend(details6)
        if bool(details):
            print_data('IP address details',
                       structure_secondary,
                       details,
                       mode=mode,
                       printer_type=IndentPrinter(3),
                       truncate=truncate)
    printer.printFooter()
    printer.finish()
