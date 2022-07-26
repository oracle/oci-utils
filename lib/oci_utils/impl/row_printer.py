# Copyright (c) 2021, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import logging
from io import StringIO
import types
import json
import sys

__all__ = ['get_row_printer_impl']

_logger = logging.getLogger("oci-utils.row_printer")


def get_row_printer_impl(mode):
    """
    Get the printer type to be called.

    Parameters
    ----------
    mode: str
        [table|parsable|json|csv|html|text|compat]

    Returns
    -------
        str: the printer name.
    """
    if mode == 'table':
        return TablePrinter
    if mode == 'parsable':
        return ParsableTextPrinter
    if mode == 'json':
        return JSONPrinter
    if mode == 'csv':
        return CSVPrinter
    if mode == 'html':
        return HtmlPrinter
    if mode in ['text', 'compat']:
        return TextPrinter
    raise Exception('Unknown mode: [%s]' % mode)


class ColumnsPrinter:
    """
    Base class for array printer
    """
    _DEFAULT_SEP = ':'
    _MISSING_ATTR = '-'
    _DEFAULT_WIDTH = 10
    _COLUMN_SEP = "|"

    def __init__(self, **kargs):
        """
        Instantiate a new columnsPrinter
        keywords:
            'column_separator' : character used to mark filed separation (default = '|')
            'printer' : file object used to output data, default sys.stdout
            'title'   : title of the spreadsheet
            'columns' : tuple of list describing how to print the columns
                        each entry must have three elements:
                            - columns title
                            - columns width
                            - attribute name to be called during printing.
                              . Or dictionary key.
                              . Or callback. callback signature is 'str _f(name,object)'
                                callback must return a string to be printed. callback will
                                be called with columns name as first argument and object as passed to printRow()
                        ex: (['name',10,'getName'])
                           This will produce a column of 10 characters width.
                           'getName' method will be called on each object passed to printRow()
                        ex:  (['foo',10, bar])
                            a call to printRow(o) produce a call to bar('foo',o)
        """

        self.title = kargs.get('title', None)
        _columns = kargs.get('columns', None)
        if not _columns:
            raise AttributeError('Columns keyword cannot be empty.')
        self.columnsNames = []
        self.columnsWidths = []
        self.columnsAttrs = []
        try:
            for _c in _columns:
                self.columnsNames.append(_c[0])
                w = int(_c[1])
                if w > 0:
                    self.columnsWidths.append(w)
                else:
                    self.columnsWidths.append(ColumnsPrinter._DEFAULT_WIDTH)
                self.columnsAttrs.append(_c[2])
        except Exception as e:
            raise AttributeError('Invalid value for columns: %s' % e.args[0]) from e

        self.tableWidth = sum(self.columnsWidths)
        self.columnsSeparator = kargs.get('column_separator', ColumnsPrinter._COLUMN_SEP)
        self.replacement = ColumnsPrinter._MISSING_ATTR
        self.printer = kargs.get('printer', sys.stdout)

    def printHeader(self):
        """ Prints the header of the array, depending upon the implementation
        """

    def printRow(self, o):
        """
        Prints a new row
        o can be an arbitrary instance on which all columns attribute will be called
        if o is a dictionary columns attribute are used as key of the dictionary
        if o is a list all elements' string representation will be printed in order
        if o is an instance, defined callback or attribute will be called
        depending upon the implementation
        """

    def rowBreak(self):
        """
        Row break, what to be display between rows
        """

    def printKeyValue(self, attrName, attrValue):
        """
        static method to print a key value pair
        depending upon the implementation
        """
        print("%s%c %s" % (attrName, ColumnsPrinter._DEFAULT_SEP, attrValue), file=self.printer)

    def printFooter(self):
        """
        prints the footer of the array
        depending upon the implementation
        """

    def finish(self):
        """
        do what it takes to finish the display of the table
        """

    def _getValueForColumn(self, columnIdx, _object):
        """
        Common helper to be used by subclass to fetch the value
        to be printed for a given column from an object pass
        :param columnIdx: current column index
        :param _object: Object as accepted by printRow
        raise LookupError is value cannot be found

        If current column attribute is a function , call it with _object
        If _object is a list or a tuple, returns the columnIdx'th element of it
        If _object is a dictionary, returns the value associated with key defined in column attribute
        If _object is an Object
           If corresponding column attribute define a callback, returns result of cb being called on that object
           If corresponding column attribute define a method name, returns result of this Object method
        """

        _columnAttr = self.columnsAttrs[columnIdx]
        if isinstance(_columnAttr, types.FunctionType):
            #
            # call the defined callback
            try:
                return _columnAttr(self.columnsNames[columnIdx], _object)
            except Exception as e:
                raise LookupError("Error calling callback [%s] in obj %s: %s"
                                  % (_columnAttr, _object, e.args[0])) from e

        # if isinstance(_object, list) or isinstance(_object, tuple):
        if isinstance(_object, (list, tuple)):
            #
            # list case : return the columnIdx'th element
            if len(_object) <= columnIdx:
                raise LookupError('List too small to match index %d' % columnIdx)
            return _object[columnIdx]

        if isinstance(_object, dict):
            #
            # dict case : return the value of key defined for that column
            _key = self.columnsAttrs[columnIdx]
            if _key in _object:
                return _object[self.columnsAttrs[columnIdx]]
            raise LookupError('Missing key [%s] in dict' % _key)

        # otherwise handle Object case.
        # if a callback is defined call and return its result
        # otherwise check if passed object has an attribute matching column
        # definition and return its result

        _o_attr = getattr(_object, _columnAttr, None)
        if not _o_attr:
            raise LookupError("Missing object attribute [%s] in obj %s" % (_columnAttr, _object))
        if isinstance(_o_attr, types.MethodType):
            try:
                return _o_attr()
            except Exception as e:
                raise LookupError("Error calling method [%s] in obj %s: %s" % (_columnAttr, _object, e.args[0])) from e
        else:
            return _o_attr


class TablePrinter(ColumnsPrinter):
    """
    Prints elements as table's rows
    """
    def __init__(self, **kargs):
        """
        see ColumnsPrinter.__init__
        keywords:
            text_truncate : yes/no (something evaluaet to True)
                            truncate if cell value greater than cell width, truncate the value
            indent: int
                indent the header.
        """
        super().__init__(**kargs)
        self.text_truncate = bool(kargs.get('text_truncate', True))
        self.header_indent = kargs.get('indent', 0) * '  '

    def printHeader(self):
        # title
        _h_title = StringIO()
        _h_title.write(self.title)
        print(_h_title.getvalue(), file=self.printer)
        _h_title.close()
        # header text
        _h_header = StringIO()
        for idx in range(len(self.columnsNames)):
            _h_header.write(self.columnsNames[idx].center(self.columnsWidths[idx]))
            _h_header.write(self.columnsSeparator)
        print(_h_header.getvalue(), file=self.printer)
        _start = _h_header.tell()
        _h_header.close()
        # subline
        _h_subline = StringIO()
        # compute needed length for subline
        _h_subline.write((_start-1)*'-')
        print(_h_subline.getvalue(), file=self.printer)
        _h_subline.close()

    def _formatCell(self, cellWidth, cellValue):
        cellValue_s = str(cellValue)
        if cellWidth > 0:
            # cellWidth - 4 : '...'
            if self.text_truncate and len(cellValue_s) > cellWidth-2:
                return ' %s... ' % cellValue_s[:cellWidth - 5]
            # enough place: we just center it
            return cellValue_s.center(cellWidth)
        return cellValue_s

    def printRow(self, o):
        # receive a list, just print elements of it
        _elements = []
        for cidx in range(len(self.columnsNames)):
            try:
                _elements.append(self._getValueForColumn(cidx, o))
            except LookupError:
                # _logger.debug('cannot get value', exc_info=True)
                _logger.debug('Cannot get value.')
                _elements.append(self.replacement)
        self._printElements(_elements)

    def _printElements(self, strlist):

        if not strlist:
            return

        _buffer = StringIO()
        it = iter(strlist)
        _w = _buffer.write
        for width in self.columnsWidths:
            try:
                _w(self._formatCell(width, next(it)))
                _w(self.columnsSeparator)
            except StopIteration:
                break
        print(_buffer.getvalue(), file=self.printer)
        _buffer.close()

    def finish(self):
        print("\n", file=self.printer)


class ParsableTextPrinter(TablePrinter):
    """Parsable text printer
    """
    _COLUMN_SEP = "#"
    _MISSING_ATTR = ''

    def __init__(self, **kargs):
        TablePrinter.__init__(self, **kargs)
        self.columnsSeparator = ParsableTextPrinter._COLUMN_SEP
        # no string centering
        self.columnsWidths = [0]*len(self.columnsNames)
        self.replacement = ParsableTextPrinter._MISSING_ATTR

    def printKeyValue(self, _, value):
        print(value, file=self.printer)

    def printHeader(self):
        pass

    def _formatCell(self, cellWidth, cellValue):
        return str(cellValue)


class CSVPrinter(ParsableTextPrinter):
    """CSV printer, not implemented
    """
    def __init__(self, **kargs):
        ParsableTextPrinter.__init__(self, **kargs)
        self.columnsSeparator = ';'


class JSONPrinter(ColumnsPrinter):
    """ JSON printer
    """
    def __init__(self, **kargs):
        ColumnsPrinter.__init__(self, **kargs)
        self.jsonArray = []
        self.encoder = json.JSONEncoder(skipkeys=False, sort_keys=False)

    def printKeyValue(self, name, value):
        print(self.encoder.encode({name: value}), file=self.printer)

    def printRow(self, o):
        _a = dict()
        cidx = 0
        for _name in self.columnsNames:
            try:
                _a[_name] = self._getValueForColumn(cidx, o)
            except LookupError:
                # _logger.debug('Cannot get value', exc_info=True)
                _logger.debug('Cannot get value.')

            cidx = cidx+1

        self.jsonArray.append(_a)

    def finish(self):
        print("%s\n" % self.encoder.encode(self.jsonArray), file=self.printer)


class HtmlPrinter(ColumnsPrinter):
    """ HTML, not implemented
    """
    def printHeader(self):
        _buffer = StringIO()
        _buffer.write('<HTML>\n')
        _buffer.write('<HEAD>\n')
        _buffer.write('<TITLE>%s</TITLE>\n' % self.title)
        _buffer.write('<BODY aLink=#ff0000 bgColor=#ffffff link=#0000ee text=#000000 vLink=#000066>\n')
        _buffer.write('<CENTER>\n')
        _buffer.write('<table border="1" align="center" width="80%">\n')
        _buffer.write('<tr>\n')
        for idx in range(len(self.columnsNames)):
            _buffer.write('<th>\n')
            _buffer.write('%s\n' % self.columnsNames[idx])
            _buffer.write('</th>\n')

        _buffer.write('</tr>\n')
        print(_buffer.getvalue(), file=self.printer)
        _buffer.close()

    def printFooter(self):
        _buffer = StringIO()
        _buffer.write('</table>\n')
        _buffer.write('</CENTER>\n')
        _buffer.write('</BODY>\n')
        _buffer.write('</HTML>\n')
        print(_buffer.getvalue(), file=self.printer)
        _buffer.close()

    def printRow(self, o):
        if isinstance(o, list):
            return self._printElements(o)

        if isinstance(o, dict):
            vals = []
            for attr in self.columnsAttrs:
                try:
                    vals.append(o[attr])
                except KeyError:
                    _logger.debug("Missing key [%s] in dict.", attr)

            return self._printElements(vals)

        vals = []
        columnNamesIte = iter(self.columnsNames)
        for attr in self.columnsAttrs:
            currentName = next(columnNamesIte)
            newCell = ColumnsPrinter._MISSING_ATTR
            if isinstance(attr, types.FunctionType):
                # call the defined callback
                try:
                    newCell = attr(currentName, o)
                except Exception as e:
                    _logger.debug("Error calling callback [%s] in obj %s: %s", attr, o, e.args[0])
            else:
                method = getattr(o, attr, None)
                if method is None:
                    if _logger.isEnabledFor(logging.DEBUG):
                        _logger.debug("Missing method [%s] in obj %s", attr, o)
                    newCell = self.replacement
                else:
                    try:
                        newCell = method()
                    except Exception as e:
                        _logger.debug("Error calling method [%s] in obj %s: %s", attr, o, e.args[0])
                        newCell = self.replacement

            vals.append(newCell)

        self._printElements(vals)
        return 1

    def _printElements(self, strlist):
        """
        Print

        Parameters
        ----------
        strlist: list
            to be printed

        Returns
        -------
            None
        """
        if not strlist:
            return

        _buffer = StringIO()
        it = iter(strlist)
        _buffer.write('<tr>\n')
        for _ in self.columnsWidths:
            try:
                o = next(it)
                _buffer.write('<td align="center" valign="middle">%s</td>\n' % str(o))
            except StopIteration:
                _logger.debug('Not enough elements to be printed.')
                break
        _buffer.write('</tr>\n')

        print(_buffer.getvalue(), file=self.printer)
        _buffer.close()


class TextPrinter(ColumnsPrinter):
    """
    Print only key/value per line
    """
    def printHeader(self):
        print(self.title, file=self.printer)

    def printRow(self, o):

        for cidx in range(len(self.columnsNames)):
            try:
                _value = self._getValueForColumn(cidx, o)
                if _value is not None:
                    _value = str(_value)
                else:
                    _value = self.replacement
            except LookupError:
                # _logger.debug('cannot get value', exc_info=True)
                _logger.debug('Cannot get value.')
                _value = self.replacement

            print('%s: %s' % (self.columnsNames[cidx], _value), file=self.printer)

    def rowBreak(self):
        # print some space between rows (block of information)
        print('', file=self.printer)
