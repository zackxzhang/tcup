import argparse
import socket
from utils import encode, decode, TCPReceiverBuffer


#################
# configuration #
#################

parser = argparse.ArgumentParser(description='TCP server',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-f', '--file',         default='recv.txt',     type=str, help='file to receive')
parser.add_argument('-a', '--host',         default='localhost',    type=str, help='server host')
parser.add_argument('-i', '--recv-port',    default=41194,          type=int, help='server recv port')
parser.add_argument('-o', '--send-port',    default=41195,          type=int, help='server send port')
parser.add_argument('-S', '--client-host',  default='localhost',    type=str, help='client host')
parser.add_argument('-s', '--client-port',  default=41190,          type=int, help='client port')
parser.add_argument('-b', '--obuffer-size', default=2048,           type=int, help='send buffer size')
parser.add_argument('-B', '--ibuffer-size', default=2048,           type=int, help='recv buffer size')
parser.add_argument('-w', '--window-size',  default=65535,          type=int, help='recv window size')


#############
# main loop #
#############

if __name__ == '__main__':

    args = parser.parse_args()
    buf = TCPReceiverBuffer(buffer_size=args.window_size)

    with open(args.file, 'wb') as f, \
         socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as si, \
         socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
        # set sockets
        si.settimeout(60)  # in case FIN gets lost or corrupted
        si.bind((args.host, args.recv_port))
        so.bind((args.host, args.send_port))
        recv_base = 0
        send_base = 0
        while True:
            print(f"waiting for {recv_base}")
            segment, _ = si.recvfrom(args.ibuffer_size)
            checksum, header_s, payload = decode(segment, verbose=True)
            if checksum:
                print(f"error detected at {header_s['seq_no']}")
                pass  # discard corrupted packets
            elif header_s['seq_no'] < recv_base:
                pass  # discard duplicate packets
            elif header_s['seq_no'] > recv_base:
                # push out-of-order packets to buffer
                buf.push(header_s['seq_no'], payload)
            else: # accept intact, in-order packets
                # pop from buffer, and append to payload
                payload += buf.pop(recv_base+len(payload))
                f.write(payload)
                f.flush()
                recv_base += len(payload)
            if header_s['FIN']:
                break
            # assemble ack packet
            ack = encode(
                payload=b'',
                src_port=args.send_port,
                dst_port=args.client_port,
                seq_no=send_base,
                ack_no=recv_base,
                ACK=True,
                verbose=True
            )
            so.sendto(ack, (args.client_host, args.client_port))

    print("server shutdown.")
