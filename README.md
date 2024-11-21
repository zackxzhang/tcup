# TCUP

[![Language](https://img.shields.io/github/languages/top/zackxzhang/tcup)](https://github.com/zackxzhang/tcup)
[![License](https://img.shields.io/github/license/zackxzhang/tcup)](https://opensource.org/licenses/BSD-3-Clause)
[![Last Commit](https://img.shields.io/github/last-commit/zackxzhang/tcup)](https://github.com/zackxzhang/tcup)

*Implement TCP using UDP*


This is a toy project that exemplifies transport protocols through socket programming.
It implements `TCP` with `UDP` so that client can **reliably** transfer data to server
over an **unreliable** network that may **drop**, **corrupt**, **reorder**, or **delay** packets.

To be exact, `server` receives data from `client`, ACKs them, and save them to file.
Meanwhile, `client` sends data to `server`, re-transmits the oldest unACKed packet on timeout, and pauses when end of window is reached.
To reduce timeouts, `client` also fast re-transmits on triple duplicate `ACK`s.
After all payloads are sent and ACKed, `client` sends `FIN`, closes socket and file handles, and calls it a day.
On receiving `FIN`, `server` releases resources and takes a bow.


### Usage
```python
python server.py -f copy.pdf
python client.py -f original.pdf
```


### Example
![alt text](./example.png)


### Feature
- implement `TCP` header (20 bytes) including checksum and encoding/decoding
- set sequence number and `ACK` number by counting bytes
- trigger fast re-transmission on triple duplicate `ACK`s
- log valid RTT samples and compute timeout interval for timer
- make `client` non-blocking, sending data and receiving `ACK`s simultaneously
- handle the corner case where `FIN` gets corrupted or lost by a long timeout
- curate a buffer of payloads for `TCP` receiver
- keep track of multiple pointers for windowing

| window                                  | semantic                    |
|-----------------------------------------|-----------------------------|
| `[         0, send_base              )` | sent and ACKed              |
| `[ send_base, send_next              )` | sent but not yet ACKed      |
| `[ send_next, send_base + window_size)` | can be sent if available    |
| `[         0, recv_base              )` | received                    |


### Roadmap
- make `server` non-blocking, receiving data and sending `ACK`s simultaneously
- implement delayed `ACK`s, ACK two at a time, immediate duplicate `ACK`s, etc
- handle the corner case where all data are ACKed but `FIN` is not sent
- set the checksum field precisely instead of re-packing a whole new header
- refactor buffer management to reduce copies and writes
