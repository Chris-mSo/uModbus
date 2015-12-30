"""
.. note:: This section is based on `MODBUS Application Protocol Specification
    V1.1b3`_

The Protocol Data Unit (PDU) is the request or response message and is
indepedent of the underlying communication layer. This module only implements
requests PDU's.

A request PDU contains two parts: a function code and request data. A response
PDU contains the function code from the request and response data. The general
structure is listed in table below:

+---------------+-----------------+
| **Field**     | **Size** (bytes)|
+---------------+-----------------+
| Function code | 1               |
+---------------+-----------------+
| data          | N               |
+---------------+-----------------+

Below you see the request PDU with function code 1, requesting status of 3
coils, starting from coil 100::

    >>> req_pdu = b'\x01\x00d\x00\x03'
    >>> function_code = req_pdu[:1]
    >>> function_code
    b'\x01'
    >>> starting_address = req_pdu[1:3]
    >>> starting_address
    b'\x00d'
    >>> quantity = req_pdu[3:]
    >>> quantity
    b'\x00\x03'

A response PDU could look like this::

    >>> resp_pdu = b'\x01\x01\x06'
    >>> function_code = resp_pdu[:1]
    >>> function_code
    b'\x01'
    >>> byte_count = resp[1:2]
    >>> byte_count
    b'\x01'
    >>> coil_status = resp[2:]
    'b\x06'

.. _MODBUS Application Protocol Specification V1.1b3: http://modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf
"""
import struct

from umodbus.exceptions import error_code_to_exception_map, IllegalDataValueError

# Function related to data access.
READ_COILS = 1
READ_DISCRETE_INPUTS = 2
READ_HOLDING_REGISTERS = 3
READ_INPUT_REGISTERS = 4

WRITE_SINGLE_COIL = 5
WRITE_SINGLE_REGISTER = 6
WRITE_MULTIPLE_COILS = 15
WRITE_MULTIPLE_REGISTERS = 16

READ_FILE_RECORD = 20
WRITE_FILE_RECORD = 21

MASK_WRITE_REGISTER = 22
READ_WRITE_MULTIPLE_REGISTERS = 23
READ_FIFO_QUEUE = 24

# Diagnostic functions, only available when using serial line.
READ_EXCEPTION_STATUS = 7
DIAGNOSTICS = 8
GET_COMM_EVENT_COUNTER = 11
GET_COM_EVENT_LOG = 12
REPORT_SERVER_ID = 17


def create_function_from_response_pdu(resp_pdu, *args, **kwargs):
    """ Parse response PDU and return instance of :class:`Function` or raise
    error.

    :param pdu: PDU of response.
    :return: Number or list with response data.
    :raises ModbusError: When response contains error code.
    """
    function_code = struct.unpack('>B', resp_pdu[1:2])[0]

    if function_code not in function_code_to_function_map.keys():
        raise error_code_to_exception_map[function_code]

    return function_code_to_function_map[function_code] \
        .create_from_response_pdu(resp_pdu, *args, **kwargs)


class ModbusFunction(object):
    function_code = None


class ReadCoils(ModbusFunction):
    """ Implement Modbus function code 01.

        "This function code is used to read from 1 to 2000 contiguous status of
        coils in a remote device. The Request PDU specifies the starting
        address, i.e. the address of the first coil specified, and the number of
        coils. In the PDU Coils are addressed starting at zero. Therefore coils
        numbered 1-16 are addressed as 0-15.

        The coils in the response message are packed as one coil per bit of the
        data field. Status is indicated as 1= ON and 0= OFF. The LSB of the
        first data byte contains the output addressed in the query. The other
        coils follow toward the high order end of this byte, and from low order
        to high order in subsequent bytes.

        If the returned output quantity is not a multiple of eight, the
        remaining bits in the final data byte will be padded with zeros (toward
        the high order end of the byte). The Byte Count field specifies the
        quantity of complete bytes of data."

        -- MODBUS Application Protocol Specification V1.1b3, chapter 6.1

    The request PDU with function code 01 must be 5 bytes:

        ================ ===============
        Field            Length (bytes)
        ================ ===============
        Function code    1
        Starting address 2
        Quantity         2
        ================ ===============

    The PDU can unpacked to this::

        >>> struct.unpack('>BHH', b'\x01\x00d\x00\x03')
        (1, 100, 3)

    The reponse PDU varies in length, depending on the request. Each 8 coils
    require 1 byte. The amount of bytes needed represent status of the coils to
    can be calculated with: bytes = round(quantity / 8) + 1. This response
    contains (3 / 8 + 1) = 1 byte to describe the status of the coils. The
    structure of a compleet response PDU looks like this:

        ================ ===============
        Field            Length (bytes)
        ================ ===============
        Function code    1
        Byte count       1
        Coil status      n
        ================ ===============

    Assume the status of 102 is 0, 101 is 1 and 100 is also 1. This is binary
    011 which is decimal 3.

    The PDU can packed like this::

        >>> struct.pack('>BBB', function_code, byte_count, 3)
        b'\x01\x01\x03'

    """
    function_code = READ_COILS

    byte_count = None
    data = None
    starting_address = None
    _quantity = None

    @property
    def quantity(self):
        return self._quantity

    @quantity.setter
    def quantity(self, value):
        """ Set number of coils to read. Quantity must be between 1 and 2000.

        :param value: Quantity.
        :raises: IllegalDataValueError.
        """
        if not (1 <= value <= 2000):
            raise IllegalDataValueError('Quantify field of request must be a '
                                        'value between 0 and '
                                        '{0}.'.format(2000))

        self._quantity = value

    @property
    def request_pdu(self):
        """ Build request PDU to read coils.

        :return: Byte array of 5 bytes with PDU.
        """
        if None in [self.starting_address, self.quantity]:
            # TODO Raise proper exception.
            raise Exception

        return struct.pack('>BHH', self.function_code, self.starting_address,
                           self.quantity)

    @staticmethod
    def create_from_response_pdu(resp_pdu, quantity):
        """ Create instance from response PDU.

        Response PDU is required together with the quantity of coils read.

        :param resp_pdu: Byte array with request PDU.
        :param quantity: Number of coils read.
        :return: Instance of :class:`ReadCoils`.
        """
        read_coils = ReadCoils()
        read_coils.quantity = quantity
        read_coils.byte_count = struct.unpack('>B', resp_pdu[1:2])[0]

        fmt = '>' + ('B' * read_coils.byte_count)
        bytes_ = struct.unpack(fmt, resp_pdu[2:])

        data = list()

        for i, value in enumerate(bytes_):
            padding = 8 if (read_coils.quantity - (8 * i)) // 8 > 0 \
                else read_coils.quantity % 8

            fmt = '{{0:0{padding}b}}'.format(padding=padding)

            # Create binary representation of integer, convert it to a list
            # and reverse the list.
            data = data + [int(i) for i in fmt.format(value)][::-1]

        read_coils.data = data
        return read_coils


class ReadDiscreteInputs(ModbusFunction):
    function_code = 2

    @staticmethod
    def create_from_response_pdu(pdu):
        read_discrete_inputs = ReadDiscreteInputs()
        _, byte_count = struct.unpack('>BB', pdu[:2])

        read_discrete_inputs.byte_count = byte_count

        fmt =  '>B' * byte


class ReadHoldingRegisters(ModbusFunction):
    function_code = 3

    def create_from_response_pdu(pdu):
        read_holding_registers = ReadHoldingRegisters()
        _, byte_count = struct.unpack('>BB', pdu[:2])

        read_holding_registers.byte_count = byte_count

        fmt = '>' + ('H' * int(read_holding_registers.byte_count / 2))
        read_holding_registers.data = list(struct.unpack(fmt, pdu[2:]))

        return read_holding_registers


class ReadInputRegisters(ModbusFunction):
    function_code = 4

    def create_from_response_pdu(pdu):
        read_input_registers = ()
        _, byte_count = struct.unpack('>BB', pdu[:2])

        read_input_registers.byte_count = byte_count

        fmt = '>' + ('H' * int(read_input_registers.byte_count / 2))
        read_input_registers.data = list(struct.unpack(fmt, pdu[2:]))

        return read_input_registers


function_code_to_function_map = {
    READ_COILS: ReadCoils,
    #READ_DISCRETE_INPUTS: ReadDiscreteInputs,
    READ_HOLDING_REGISTERS: ReadHoldingRegisters,
    READ_INPUT_REGISTERS: ReadInputRegisters,
    #WRITE_SINGLE_COIL: WriteSingleCoil,
    #WRITE_SINGLE_REGISTER: WriteSingleRegister,
    #WRITE_MULTIPLE_COILS: WriteMultipleCoils,
    #WRITE_MULTIPLE_REGISTERS: WriteMultipleRegisters,
}
