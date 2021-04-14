# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
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
    if mode == 'text':
        return TextPrinter
    raise Exception('unknown mode [%s]' % mode)


class ColumnsPrinter:
    """
    base class fo array printer
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
                            - attribute name to be called during printing. Or dictionary key.
                              Or callback. callback signature is 'str _f(name,object)'
                              callback must return a string to be printed. callback will
                              be called with columns name as first argument and object as passed to printRow()
                        ex: (['name',10,'getName'])
                           This will produce a columns of 10 characters width.
                           'getName' method will be called on each objects passed to printRow()
                        ex:  (['foo',10, bar])
                            a call to printRow(o) produce a call to bar('foo',o)
        """

        self.title = kargs.get('title', None)
        _columns = kargs.get('columns', None)
        if not _columns:
            raise AttributeError('columns keyword cannot be empty')
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
        """
        prints the header of the array
        depend of the implementation
        """

    def printRow(self, o):
        """
        prints a new row
        o can be an arbitrary instance on which all columns attribute will be called
        if o is an dictionnary columns attribute are used as key of the dictionnary
        if o is a list all elements' string representation will be printed in order
        if o is an instance, defined callback or attribute will be called
        depend of the implementation
        """

    def rowBreak(self):
        """
        Row break, what to be display between rows
        """

    def printKeyValue(self, attrName, attrValue):
        """
        static method to print a key value pair
        depend of the implementation
        """
        print("%s %c %s" % (attrName, ColumnsPrinter._DEFAULT_SEP, attrValue), file=self.printer)

    def printFooter(self):
        """
        prints the footer of the array
        depend of the implementation
        """

    def finish(self):
        """
        do what it takes to finish the display of the table
        """

    def _getValueForColumn(self, columnIdx, _object):
        """
        Common helper to be used by subclass to fetch the value
        to be printed for a given column from a object pass
        :param columnIdx: current column index
        :param _object: Object as accepted by printRow
        raise LookupError is value cannot be found

        If current column attribut is a function , call it with _object
        If _object is a list or a tuple, returns the columnIdx'th element of it
        If _object is a dictionary, returns the value associated with key defined in column attribute
        If _object is a Object
           If corresponding column attribute define a callback, returns result of cb being called on that object
           If corresponding column attribute define a method name, returns result of this Object method
        """

        _columnAttr = self.columnsAttrs[columnIdx]
        if isinstance(_columnAttr, types.FunctionType):
            # call the defined callback
            try:
                return _columnAttr(self.columnsNames[columnIdx], _object)
            except Exception as e:
                raise LookupError("error calling callback [%s] in obj %s: %s"
                                  % (_columnAttr, _object, e.args[0])) from e

        if isinstance(_object, list) or isinstance(_object, tuple):
            """
            list case : return the columnIdx'th element
            """
            if len(_object) <= columnIdx:
                raise LookupError('list too small to match index %d' % columnIdx)
            return _object[columnIdx]

        if isinstance(_object, dict):
            """
            dict case : return the value of key defined for that column
            """
            _key = self.columnsAttrs[columnIdx]
            if _key in _object:
                return _object[self.columnsAttrs[columnIdx]]
            raise LookupError('missing key [%s] in dict' % _key)

        # otherwise handle Object case.
        # if a callback is defined call and return its result
        # otherwise check if passed object has an attribute matching column
        # definition and return its result

        _o_attr = getattr(_object, _columnAttr, None)
        if not _o_attr:
            raise LookupError("missing object attribute [%s] in obj %s" % (_columnAttr, _object))
        if isinstance(_o_attr, types.MethodType):
            try:
                return _o_attr()
            except Exception as e:
                raise LookupError("error calling method [%s] in obj %s: %s" % (_columnAttr, _object, e.args[0])) from e
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

        """
        super().__init__(**kargs)
        self.text_truncate = bool(kargs.get('text_truncate', True))

    def printHeader(self):
        _buffer = StringIO()
        _buffer.write(self.title)
        _buffer.write(':\n')
        # keep track of position before printing columns names
        # in order to draw the line
        _start = _buffer.tell()
        for idx in range(len(self.columnsNames)):
            _buffer.write(self.columnsNames[idx].center(self.columnsWidths[idx]))
            _buffer.write(self.columnsSeparator)
        _buffer.write('\n')
        # compute needed length for subline
        _buffer.write((_buffer.tell()-_start-1)*'-')

        print(_buffer.getvalue(), file=self.printer)
        _buffer.close()

    def _formatCell(self, cellWidth, cellValue):
        cellValue_s = str(cellValue)
        if cellWidth > 0:
            # cellWidth - 4 : '...'
            if self.text_truncate and len(cellValue_s) > cellWidth:
                return '%s...' % cellValue_s[:cellWidth - 3]
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
                _logger.debug('cannot get value')
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


class ParsableTextPrinter(TablePrinter):
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
    def __init__(self, **kargs):
        ParsableTextPrinter.__init__(self, **kargs)
        self.columnsSeparator = ';'


class JSONPrinter(ColumnsPrinter):
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
                _logger.debug('Cannot get value')

            cidx = cidx+1

        self.jsonArray.append(_a)

    def finish(self):
        print("%s\n" % self.encoder.encode(self.jsonArray), file=self.printer)


class HtmlPrinter(ColumnsPrinter):

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
                    _logger.debug("missing key [%s] in dict", attr)

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
                    _logger.debug("error calling callback [%s] in obj %s: %s", attr, o, e.args[0])
            else:
                method = getattr(o, attr, None)
                if method is None:
                    if _logger.isEnabledFor(logging.DEBUG):
                        _logger.debug("missing method [%s] in obj %s", attr, o)
                    newCell = self.replacement
                else:
                    try:
                        newCell = method()
                    except Exception as e:
                        _logger.debug("error calling method [%s] in obj %s: %s", attr, o, e.args[0])
                        newCell = self.replacement

            vals.append(newCell)

        self._printElements(vals)

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
                _logger.debug('not enough elem to be printed')
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
                _logger.debug('cannot get value')
                _value = self.replacement

            print('%s: %s' % (self.columnsNames[cidx], _value), file=self.printer)

    def rowBreak(self):
        # print some space between rows (block of information)
        print('', file=self.printer)
