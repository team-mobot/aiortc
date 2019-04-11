import binascii
from unittest import TestCase

from aioquic import packet
from aioquic.packet import (PACKET_TYPE_INITIAL, QuicHeader,
                            QuicProtocolVersion, QuicTransportParameters,
                            pull_quic_header, pull_quic_transport_parameters,
                            pull_uint_var, push_quic_header,
                            push_quic_transport_parameters, push_uint_var)
from aioquic.tls import Buffer, BufferReadError

from .utils import load


class UintTest(TestCase):
    def roundtrip(self, data, value):
        buf = Buffer(data=data)
        self.assertEqual(pull_uint_var(buf), value)
        self.assertEqual(buf.tell(), len(data))

        buf = Buffer(capacity=8)
        push_uint_var(buf, value)
        self.assertEqual(buf.data, data)

    def test_uint_var(self):
        # 1 byte
        self.roundtrip(b'\x00', 0)
        self.roundtrip(b'\x01', 1)
        self.roundtrip(b'\x25', 37)
        self.roundtrip(b'\x3f', 63)

        # 2 bytes
        self.roundtrip(b'\x7b\xbd', 15293)
        self.roundtrip(b'\x7f\xff', 16383)

        # 4 bytes
        self.roundtrip(b'\x9d\x7f\x3e\x7d', 494878333)
        self.roundtrip(b'\xbf\xff\xff\xff', 1073741823)

        # 8 bytes
        self.roundtrip(b'\xc2\x19\x7c\x5e\xff\x14\xe8\x8c', 151288809941952652)
        self.roundtrip(b'\xff\xff\xff\xff\xff\xff\xff\xff', 4611686018427387903)

    def test_pull_uint_var_truncated(self):
        buf = Buffer(capacity=0)
        with self.assertRaises(BufferReadError):
            pull_uint_var(buf)

    def test_push_uint_var_too_big(self):
        buf = Buffer(capacity=8)
        with self.assertRaises(ValueError) as cm:
            push_uint_var(buf, 4611686018427387904)
        self.assertEqual(str(cm.exception), 'Integer is too big for a variable-length integer')


class PacketTest(TestCase):
    def test_pull_empty(self):
        buf = Buffer(data=b'')
        with self.assertRaises(BufferReadError):
            pull_quic_header(buf, host_cid_length=8)

    def test_pull_initial_client(self):
        buf = Buffer(data=load('initial_client.bin'))
        header = pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(header.version, QuicProtocolVersion.DRAFT_17)
        self.assertEqual(header.packet_type, PACKET_TYPE_INITIAL)
        self.assertEqual(header.destination_cid, binascii.unhexlify('90ed1e1c7b04b5d3'))
        self.assertEqual(header.source_cid, b'')
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 1263)
        self.assertEqual(buf.tell(), 17)

    def test_pull_initial_server(self):
        buf = Buffer(data=load('initial_server.bin'))
        header = pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(header.version, QuicProtocolVersion.DRAFT_17)
        self.assertEqual(header.packet_type, PACKET_TYPE_INITIAL)
        self.assertEqual(header.destination_cid, b'')
        self.assertEqual(header.source_cid, binascii.unhexlify('0fcee9852fde8780'))
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 182)
        self.assertEqual(buf.tell(), 17)

    def test_pull_version_negotiation(self):
        buf = Buffer(data=load('version_negotiation.bin'))
        header = pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(header.version, QuicProtocolVersion.NEGOTIATION)
        self.assertEqual(header.packet_type, None)
        self.assertEqual(header.destination_cid, binascii.unhexlify('dae1889b81a91c26'))
        self.assertEqual(header.source_cid, binascii.unhexlify('f49243784f9bf3be'))
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 8)
        self.assertEqual(buf.tell(), 22)

    def test_pull_long_header_no_fixed_bit(self):
        buf = Buffer(data=b'\x80\xff\x00\x00\x11\x00')
        with self.assertRaises(ValueError) as cm:
            pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(str(cm.exception), 'Packet fixed bit is zero')

    def test_pull_long_header_too_short(self):
        buf = Buffer(data=b'\xc0\x00')
        with self.assertRaises(BufferReadError):
            pull_quic_header(buf, host_cid_length=8)

    def test_pull_short_header(self):
        buf = Buffer(data=load('short_header.bin'))
        header = pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(header.version, 0)
        self.assertEqual(header.packet_type, 0x50)
        self.assertEqual(header.destination_cid, binascii.unhexlify('f45aa7b59c0e1ad6'))
        self.assertEqual(header.source_cid, b'')
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 12)
        self.assertEqual(buf.tell(), 9)

    def test_pull_short_header_no_fixed_bit(self):
        buf = Buffer(data=b'\x00')
        with self.assertRaises(ValueError) as cm:
            pull_quic_header(buf, host_cid_length=8)
        self.assertEqual(str(cm.exception), 'Packet fixed bit is zero')

    def test_push_initial(self):
        buf = Buffer(capacity=32)
        header = QuicHeader(
            version=QuicProtocolVersion.DRAFT_17,
            packet_type=PACKET_TYPE_INITIAL,
            destination_cid=binascii.unhexlify('90ed1e1c7b04b5d3'),
            source_cid=b'')
        push_quic_header(buf, header)
        self.assertEqual(buf.data, binascii.unhexlify('c0ff0000115090ed1e1c7b04b5d30000000000'))


class ParamsTest(TestCase):
    maxDiff = None

    def test_client_params(self):
        buf = Buffer(data=binascii.unhexlify(
            'ff0000110031000500048010000000060004801000000007000480100000000'
            '4000481000000000100024258000800024064000a00010a'))
        params = pull_quic_transport_parameters(buf, is_client=True)
        self.assertEqual(params, QuicTransportParameters(
            initial_version=QuicProtocolVersion.DRAFT_17,
            idle_timeout=600,
            initial_max_data=16777216,
            initial_max_stream_data_bidi_local=1048576,
            initial_max_stream_data_bidi_remote=1048576,
            initial_max_stream_data_uni=1048576,
            initial_max_streams_bidi=100,
            ack_delay_exponent=10,
        ))

        buf = Buffer(capacity=512)
        push_quic_transport_parameters(buf, params, is_client=True)

    def test_server_params(self):
        buf = Buffer(data=binascii.unhexlify(
            'ff00001104ff000011004500050004801000000006000480100000000700048'
            '010000000040004810000000001000242580002001000000000000000000000'
            '000000000000000800024064000a00010a'))
        params = pull_quic_transport_parameters(buf, is_client=False)
        self.assertEqual(params, QuicTransportParameters(
            negotiated_version=QuicProtocolVersion.DRAFT_17,
            supported_versions=[QuicProtocolVersion.DRAFT_17],
            idle_timeout=600,
            stateless_reset_token=bytes(16),
            initial_max_data=16777216,
            initial_max_stream_data_bidi_local=1048576,
            initial_max_stream_data_bidi_remote=1048576,
            initial_max_stream_data_uni=1048576,
            initial_max_streams_bidi=100,
            ack_delay_exponent=10,
        ))

        buf = Buffer(capacity=512)
        push_quic_transport_parameters(buf, params, is_client=False)


class FrameTest(TestCase):
    def test_ack_frame(self):
        data = b'\x00\x02\x00\x00'

        # parse
        buf = Buffer(data=data)
        rangeset, delay = packet.pull_ack_frame(buf)
        self.assertEqual(list(rangeset), [
            range(0, 1)
        ])
        self.assertEqual(delay, 2)

        # serialize
        buf = Buffer(capacity=len(data))
        packet.push_ack_frame(buf, rangeset, delay)
        self.assertEqual(buf.data, data)

    def test_ack_frame_with_ranges(self):
        data = b'\x05\x02\x01\x00\x02\x03'

        # parse
        buf = Buffer(data=data)
        rangeset, delay = packet.pull_ack_frame(buf)
        self.assertEqual(list(rangeset), [
            range(0, 4),
            range(5, 6)
        ])
        self.assertEqual(delay, 2)

        # serialize
        buf = Buffer(capacity=len(data))
        packet.push_ack_frame(buf, rangeset, delay)
        self.assertEqual(buf.data, data)

    def test_new_token(self):
        data = binascii.unhexlify('080102030405060708')

        # parse
        buf = Buffer(data=data)
        token = packet.pull_new_token_frame(buf)
        self.assertEqual(token, binascii.unhexlify('0102030405060708'))

        # serialize
        buf = Buffer(capacity=len(data))
        packet.push_new_token_frame(buf, token)
        self.assertEqual(buf.data, data)

    def test_new_connection_id(self):
        data = binascii.unhexlify(
            '02117813f3d9e45e0cacbb491b4b66b039f20406f68fede38ec4c31aba8ab1245244e8')

        # parse
        buf = Buffer(data=data)
        frame = packet.pull_new_connection_id_frame(buf)
        self.assertEqual(frame, (
            2,
            binascii.unhexlify('7813f3d9e45e0cacbb491b4b66b039f204'),
            binascii.unhexlify('06f68fede38ec4c31aba8ab1245244e8')))

        # serialize
        buf = Buffer(capacity=len(data))
        packet.push_new_connection_id_frame(buf, *frame)
        self.assertEqual(buf.data, data)