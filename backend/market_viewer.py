import socket
import struct
import os
import sys

def parse_binary_market_packet(data: bytes) -> dict:
    if len(data) < 2:
        return None
    
    num_bids, num_asks =struct.unpack("!BB", data[0:2])

    expected_len = 2 + (num_bids * 8) + (num_asks * 8)

    if len(data) < expected_len:
        return None # incomplete data
    
    cursor = 2
    bids = []
    for _ in range(num_bids):
        price, qty = struct.unpack("!fI", data[cursor : cursor + 8])
        bids.append({"price" : round(price, 4), "qty" : qty})
        cursor += 8
    asks = []
    for _ in range(num_asks):
        price, qty = struct.unpack("!fI", data[cursor : cursor + 8])
        asks.append({"price" : round(price, 4), "qty" : qty})
        cursor += 8
    
    return {"bids" : bids, "asks": asks}