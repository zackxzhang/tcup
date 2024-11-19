import argparse
import select
import socket
import sys
import time
from utils import encode, decode, RTTSampler, TOICalculator


#################
# configuration #
#################

parser = argparse.ArgumentParser(description='TCP client',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-f', '--file',         default='send.txt',     type=str, help='file to send')
parser.add_argument('-a', '--host',         default='localhost',    type=str, help='client host')
parser.add_argument('-i', '--recv-port',    default=41190,          type=int, help='client recv port')
parser.add_argument('-o', '--send-port',    default=41191,          type=int, help='client send port')
parser.add_argument('-S', '--server-host',  default='localhost',    type=str, help='server host')
parser.add_argument('-s', '--server-port',  default=41192,          type=int, help='server port')
parser.add_argument('-b', '--obuffer-size', default=64,             type=int, help='send buffer size')
parser.add_argument('-B', '--ibuffer-size', default=2048,           type=int, help='recv buffer size')
parser.add_argument('-w', '--window-size',  default=2048,           type=int, help='send window size')


#############
# main loop #
#############

if __name__ == '__main__':

    args = parser.parse_args()

    with open(args.file, 'rb') as f, \
         socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so, \
         socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as si:
        # set sockets
        so.setblocking(False)
        si.setblocking(False)
        so.bind((args.host, args.send_port))
        si.bind((args.host, args.recv_port))
        # set top level states for looping and polling
        TERM = False    # if true, terminate main loop
        DONE = False    # whether all data have been sent or not
                        # if true, do not poll on sending socket
        DUP_ACK_CT = 0  # counter for duplicate ack
                        # if >= 2, fast retransmit
        # set pointers for windowing
        # [         0, send_base)                 sent and acknowledged
        # [ send_base, send_next)                 sent but not yet acknowledged
        # [ send_next, send_base + window_size)   can be sent if available
        # [         0, recv_base)                 received
        send_base = 0
        send_next = 0
        recv_base = 0
        # set rtt and toi
        rtt = RTTSampler()
        toi = TOICalculator()
        MIN_RTT = 10.
        # enter main loop
        while not TERM:
            # poll on sockets
            # ... data to be fast retransmitted
            if DUP_ACK_CT >= 2:
                il, ol, xl = select.select([], [so], [si, so], toi.toi)
            # ... data within the window to be sent
            elif not DONE and send_next + args.obuffer_size <= send_base + args.window_size:
                il, ol, xl = select.select([si], [so], [si, so], toi.toi)
            # ... NO data to be sent or fast retransmitted
            else:
                il, ol, xl = select.select([si], [], [si, so], toi.toi)
            # receive ack
            for s in il:
                if s is si:
                    ack, _ = si.recvfrom(args.ibuffer_size)
                    _, header_s, _ = decode(ack, verbose=True)
                    # move send_base on cumulative ack
                    if send_base < header_s['ack_no']:
                        send_base = header_s['ack_no']
                        DUP_ACK_CT = 0
                    else:
                        DUP_ACK_CT += 1
                    # terminate if all data are sent and acked
                    if DONE and send_base == send_next:
                        segment = encode(
                            b'',
                            src_port=args.send_port,
                            dst_port=args.server_port,
                            seq_no=send_next,
                            FIN=True
                        )
                        so.sendto(segment, (args.server_host, args.server_port))
                        TERM = True  # set terminate flag
                        break
                    # update toi with sample rtt
                    if header_s['ack_no'] in rtt:
                        skip_ct, send_time = rtt.pop(header_s['ack_no'])
                        sample_rtt = time.time() - send_time
                        MIN_RTT = min(MIN_RTT, sample_rtt)
                        sample_rtts = [sample_rtt] + [MIN_RTT] * skip_ct
                        for sample_rtt in sample_rtts:
                            toi.update(sample_rtt)
            # send data
            for s in ol:
                if s is so:
                    # ... fast retransmit
                    if DUP_ACK_CT >= 2:
                        print(f"fast retransmit {send_base}")
                        f.seek(send_base)
                        payload = f.read(args.obuffer_size)
                        segment = encode(
                            payload,
                            src_port=args.send_port,
                            dst_port=args.server_port,
                            seq_no=send_base
                        )
                        so.sendto(segment, (args.server_host, args.server_port))
                        DUP_ACK_CT = 0
                    # ... normal transmit
                    else:
                        print(f"sending packet {send_next}")
                        f.seek(send_next)
                        payload = f.read(args.obuffer_size)
                        if not payload:     # end of file
                            DONE = True     # all data have been sent
                        else:               # some data to be sent
                            segment = encode(
                                payload,
                                src_port=args.send_port,
                                dst_port=args.server_port,
                                seq_no=send_next
                            )
                            so.sendto(segment, (args.server_host, args.server_port))
                        send_next += len(payload)               # advance send_next
                        rtt.update({send_next: time.time()})    # update rtt records
            # timeout, retransmit
            if not (il + ol + xl):
                toi.backoff(1.1) # exponential backoff
                # re-sending ...
                print(
                    f"timeout packet {send_base}. "
                    f"{toi}. "
                    "re-sending..."
                )
                f.seek(send_base)
                payload = f.read(args.obuffer_size)
                # assemble data packet
                segment = encode(
                    payload,
                    src_port=args.send_port,
                    dst_port=args.server_port,
                    seq_no=send_base
                )
                so.sendto(segment, (args.server_host, args.server_port))
                # update rtt record, avoid measuring retransmitted packets
                if send_base+len(payload) in rtt:
                    rtt.pop(send_base+len(payload))

    print("client shutdown.")
