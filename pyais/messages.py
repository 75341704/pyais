import json
from typing import Any, Dict, Optional, Sequence

from bitarray import bitarray  # type: ignore

from pyais.ais_types import AISType
from pyais.decode import decode
from pyais.exceptions import InvalidNMEAMessageException, InvalidChecksumException
from pyais.util import decode_into_bit_array, get_int, compute_checksum


class NMEAMessage(object):
    __slots__ = (
        'ais_id',
        'raw',
        'talker',
        'msg_type',
        'count',
        'index',
        'seq_id',
        'channel',
        'data',
        'checksum',
        'bit_array'
    )

    def __init__(self, raw: bytes) -> None:
        # Initial values
        self.checksum: int = -1

        # Store raw data
        self.raw: bytes = raw

        # An AIS NMEA message consists of seven, comma separated parts
        values = raw.split(b",")

        # Only encapsulated messages are currently supported
        if values[0][0] != 0x21:
            return

        if len(values) != 7:
            raise InvalidNMEAMessageException("A NMEA message needs to have exactly 7 comma separated entries.")

        # Unpack NMEA message parts
        (
            head,
            count,
            index,
            seq_id,
            channel,
            data,
            checksum
        ) = values

        # The talker is identified by the next 2 characters
        self.talker: str = head[1:3].decode('ascii')

        # The type of message is then identified by the next 3 characters
        self.msg_type: str = head[3:].decode('ascii')

        # Store other important parts
        self.count: int = int(count)
        self.index: int = int(index)
        self.seq_id: bytes = seq_id
        self.channel: bytes = channel
        self.data: bytes = data
        self.checksum = int(checksum[2:], 16)

        # Verify if the checksum is correct
        if not self.is_valid:
            raise InvalidChecksumException(
                f"Invalid Checksum. Expected {self.checksum}, got {compute_checksum(self.data)}.")

        # Finally decode bytes into bits
        self.bit_array: bitarray = decode_into_bit_array(self.data)
        self.ais_id: int = get_int(self.bit_array, 0, 6)

    def __str__(self) -> str:
        return str(self.raw)

    def asdict(self) -> Dict[str, Any]:
        def serializable(o: object) -> Any:
            if isinstance(o, bytes):
                return o.decode('utf-8')
            elif isinstance(o, bitarray):
                return o.to01()

            return o

        return dict(
            [
                (slot, serializable(getattr(self, slot)))
                for slot in self.__slots__
            ]
        )

    def __eq__(self, other: object) -> bool:
        return all([getattr(self, attr) == getattr(other, attr) for attr in self.__slots__])

    @classmethod
    def from_string(cls, nmea_str: str) -> "NMEAMessage":
        return cls(str.encode(nmea_str))

    @classmethod
    def from_bytes(cls, nmea_byte_str: bytes) -> "NMEAMessage":
        return cls(nmea_byte_str)

    @classmethod
    def assemble_from_iterable(cls, messages: Sequence["NMEAMessage"]) -> "NMEAMessage":
        """
        Assemble a multiline message from a sequence of NMEA messages.
        :param messages: Sequence of NMEA messages
        :return: Single message
        """
        raw = b''
        data = b''
        bit_array = bitarray()

        for msg in messages:
            raw += msg.raw
            data += msg.data
            bit_array += msg.bit_array

        messages[0].raw = raw
        messages[0].data = data
        messages[0].bit_array = bit_array
        return messages[0]

    @property
    def is_valid(self) -> bool:
        return self.checksum == compute_checksum(self.raw)

    @property
    def is_single(self) -> bool:
        return not self.seq_id and self.index == self.count == 1

    @property
    def is_multi(self) -> bool:
        return not self.is_single

    @property
    def fragment_count(self) -> int:
        return self.count

    def decode(self, silent: bool = True) -> Optional["AISMessage"]:
        """
        Decode the message content.

        @param silent: Boolean. If set to true errors are ignored and None is returned instead
        """
        try:
            return AISMessage(self)
        except Exception as e:
            if silent:
                return None

            raise e


class AISMessage(object):
    """
    Initializes a generic AIS message.
    """

    def __init__(self, nmea_message: NMEAMessage) -> None:
        self.nmea: NMEAMessage = nmea_message
        self.msg_type: AISType = AISType(nmea_message.ais_id)
        self.content = decode(self.nmea)

    def __getitem__(self, item: str) -> Any:
        return self.content[item]

    def __str__(self) -> str:
        return str(self.content)

    def asdict(self) -> Dict[str, Any]:
        return {
            'nmea': self.nmea.asdict(),
            'decoded': self.content
        }

    def to_json(self) -> str:
        return json.dumps(
            self.asdict(),
            indent=4
        )
