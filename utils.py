import array
import struct


b0 = (0).to_bytes(1, 'big')  # byte 0


def cksum(buf: bytes) -> int:
    """ 1s complement of the sum of all the 16-bit words """
    # pad to even length
    if len(buf) % 2:
        buf += b0
    # pair adjacent octets to form 16-bit integers
    # and sum these 16-bit integers
    s = 0
    for i in range(0, len(buf), 2):
        s += (ord(buf[i:i+1]) << 8) + ord(buf[i+1:i+2])
    # carry
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    # complement
    s = ~s
    return s & 0xffff


def pack_dataofst(dataofst: int = 5) -> int:
    """ right pad with 0's from reserved """
    return dataofst << 4


def unpack_dataofst(dataofst_i: int) -> int:
    """ undo right padded 0's from reserved """
    return dataofst_i >> 4


def pack_control(URG: bool, ACK: bool, PSH: bool,
                 RST: bool, SYN: bool, FIN: bool) -> int:
    """ pack control bits """
    return (URG << 5) + (ACK << 4) + (PSH << 3) + \
           (RST << 2) + (SYN << 1) +  FIN


def unpack_control(control_i: int) -> tuple:
    """ unpack control bits """
    URG = (control_i >> 5) & 1
    ACK = (control_i >> 4) & 1
    PSH = (control_i >> 3) & 1
    RST = (control_i >> 2) & 1
    SYN = (control_i >> 1) & 1
    FIN = control_i & 1
    return URG, ACK, PSH, RST, SYN, FIN


# TCP header struct
# src_port: int
# dst_port: int
# seq_no  : int
# ack_no  : int
# dataofst: int
# URG : bool, ACK : bool, PSH : bool
# RST : bool, SYN : bool, FIN : bool
# window  : int
# checksum: int
# urgt_ptr: int

# TCP header default
dataofst = 5  # 20 bytes = 5 * 32-bit words
reserved = 0  # per TCP standard
URG      = False
PSH      = False
RST      = False
SYN      = False
checksum = 0
urgt_ptr = 0


def encode_header(header_s: dict) -> bytes:
    """ encode a TCP header """
    # byte layout
    fmt = '!HHIIBBHHH'
    # ! network (big-endian)
    # I 4 bytes
    # H 2 bytes
    # B 1 bytes
    # group / pad -> int
    dataofst_i = pack_dataofst(header_s['dataofst'])
    control_i = pack_control(header_s['URG'], header_s['ACK'], header_s['PSH'],
                             header_s['RST'], header_s['SYN'], header_s['FIN'])
    # int -> byte
    header = struct.pack(
                fmt,
                header_s['src_port'],  # source port
                header_s['dst_port'],  # destination port
                header_s['seq_no'],    # sequence number
                header_s['ack_no'],    # acknowledgment number
                dataofst_i,  # data offset (right padded with 0's from reserved)
                control_i,   # control bits (left padded with 0's from reserved)
                header_s['window'],    # window
                header_s['checksum'],  # checksum
                header_s['urgt_ptr']   # urgent pointer
            )
    return header


def encode(payload: bytes, src_port: int, dst_port: int,
           seq_no: int = 0, ack_no: int = 0, window: int = 0,
           ACK: bool = False, FIN: bool = False,
           verbose=False) -> bytes:
    """ encode a TCP segment (header + payload) """
    # header with checksum 0
    header_s = {
        'src_port': src_port,
        'dst_port': dst_port,
        'seq_no'  : seq_no,
        'ack_no'  : ack_no,
        'dataofst': dataofst,
        'URG'     : URG,
        'ACK'     : ACK,
        'PSH'     : PSH,
        'RST'     : RST,
        'SYN'     : SYN,
        'FIN'     : FIN,
        'window'  : window,
        'checksum': 0,
        'urgt_ptr': urgt_ptr,
    }
    header = encode_header(header_s)
    checksum = cksum(header + payload)
    # header with computed checksum
    header_s['checksum'] = checksum
    header = encode_header(header_s)
    return header + payload


def decode_header(buf: bytes) -> dict:
    """ decode a TCP header """
    # byte layout
    fmt = '!HHIIBBHHH'
    # ! network (big-endian)
    # I 4 bytes
    # H 2 bytes
    # B 1 bytes
    # byte -> int
    (src_port,
     dst_port,
     seq_no,
     ack_no,
     dataofst_i,
     control_i,
     window,
     checksum,
     urgt_ptr) = struct.unpack(fmt, buf)
    # unpack
    dataofst = unpack_dataofst(dataofst_i)
    URG, ACK, PSH, RST, SYN, FIN = unpack_control(control_i)
    # structure
    header_s = {
        'src_port': src_port,
        'dst_port': dst_port,
        'seq_no'  : seq_no,
        'ack_no'  : ack_no,
        'dataofst': dataofst,
        'URG'     : URG,
        'ACK'     : ACK,
        'PSH'     : PSH,
        'RST'     : RST,
        'SYN'     : SYN,
        'FIN'     : FIN,
        'window'  : window,
        'checksum': checksum,
        'urgt_ptr': urgt_ptr,
    }
    return header_s


def decode(segment: bytes, verbose=False) -> tuple:
    """ decode a TCP segment (header + payload) """
    header =  segment[:20]
    payload = segment[20:]
    header_s = decode_header(header)
    return cksum(segment), header_s, payload


class TCPReceiverBuffer:
    """ data structure for buffering out-of-order packets """

    def __init__(self, buffer_size: int = 65535):
        self._buffer: list = list()
        self._max_size = buffer_size

    def __repr__(self):
        return 'TCPReceiverBuffer(seq_nos={})'.format(self.seq_nos)

    def push(self, seq_no: int, payload: bytes):
        if self.size < self.max_size and seq_no not in self.seq_nos:
            self.buffer = sorted(self.buffer + [(seq_no, payload)])

    @property
    def seq_nos(self) -> list:
        return [b[0] for b in self.buffer]

    @property
    def payloads(self) -> list:
        return [b[1] for b in self.buffer]

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def size(self) -> int:
        return sum([len(b[1]) for b in self.buffer])

    @property
    def buffer(self) -> list:
        return self._buffer

    @buffer.setter
    def buffer(self, value: list):
        assert isinstance(value, list)
        self._buffer = value

    def _popable(self, seq_no: int) -> bool:
        ''' check if seq_no matches start of the buffer '''
        if self.seq_nos and seq_no > self.seq_nos[0]:
            raise AttributeError('Error in TCPReceiverBuffer _popable.\n{}'
                                 .format(self))
        if self.seq_nos and seq_no == self.seq_nos[0]:
            return True
        else:
            return False

    def _pop(self, seq_no: int) -> bytes:
        """ concatenate continuous payloads [seq_no, ...) """
        end = 1
        expect_next = seq_no
        for i, (seq_no, payload) in enumerate(self.buffer):
            if expect_next != seq_no:
                break
            end = i + 1
            expect_next = seq_no + len(payload)
        payload = b''.join(self.payloads[:end])
        self.buffer = self.buffer[end:]
        return payload

    def pop(self, seq_no: int) -> bytes:
        """
        if seq_no matches start of the buffer,
        return a concatenated blob of continuous payloads [seq_no, ...)
        else, return empty byte
        """
        if not self._popable(seq_no):
            return b''
        else:
            payload = self._pop(seq_no)
            if not payload:
                AttributeError('Error in TCPReceiverBuffer pop.')
            return payload


class TOICalculator:
    """ data structure for calculating TimeOutInterval """

    def __init__(self, estRTT: float = 1., devRTT: float = 0.,
                 threshold: float = 10):
        self.estRTT = estRTT
        self.devRTT = devRTT
        self._threshold = threshold

    def __repr__(self):
        return ( 'TOICalculator(estRTT={:.3f}, devRTT={:.3f}, toi={:.3f})'
                 .format(self.estRTT,self.devRTT, self.toi)   )
    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def toi(self) -> float:
        return min(self.estRTT + 4 * self.devRTT, self.threshold)

    def update(self, splRTT: float):
        self.estRTT = .875 * self.estRTT + .125 * splRTT
        self.devRTT = .75  * self.devRTT + .25  * abs(splRTT - self.estRTT)

    def backoff(self, factor: float = 2.):
        if self.estRTT + 4 * self.devRTT <= self.threshold:
            self.estRTT *= factor
            self.devRTT *= factor


class RTTSampler:
    """
    data structure for sampling RTT
    {ack_no: send_time}
    """

    def __init__(self):
        self._records = dict()

    @property
    def records(self):
        return self._records

    def __repr__(self):
        return 'RTTSampler({})'.format(self.records)

    def __contains__(self, ack_no: int):
        return ack_no in self.records

    def update(self, record: dict):
        self.records.update(record)

    def pop(self, ack_no: int) -> tuple:
        ks = [k for k, _ in self.records.items() if k < ack_no]
        for k in ks:
            del self.records[k]
        skip_ct = len(ks)  # number of packets skipped by cumulative ack
        return skip_ct, self.records.pop(ack_no)



if __name__ == '__main__':

    # unit tests
    print(unpack_dataofst(pack_dataofst(dataofst=5)))
    print(unpack_control(pack_control(False, False, True, False, False, True)))
    print(cksum(encode(payload=b'', src_port=1, dst_port=2)))

    buf = TCPReceiverBuffer()
    buf.push(4, bytes(4))
    buf.push(8, bytes(4))
    buf.push(12, bytes(4))
    buf.push(20, bytes(4))
    print(buf)
    payload = buf.pop(4)
    print(len(payload))
    print(buf)

    toi = TOICalculator()
    toi.update(0.08)
    print(toi)
    toi.update(10.)
    print(toi)

    rtt = RTTSampler()
    rtt.update({5: .3})
    rtt.update({6: .4})
    rtt.update({7: .6})
    rtt.update({8: .8})
    rtt.update({9: 1.})
    rtt.pop(5)
    print(rtt)
    rtt.pop(7)
    print(6 in rtt)
    rtt.pop(8)
    print(rtt)
