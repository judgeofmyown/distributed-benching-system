import socket
import random
import asyncio
import uuid
import threading
import time
import struct
from enum import IntEnum
import os
from config import SERVER_HOST, SERVER_PORT, PROB_BUY, PROB_SELL, PROB_CANCEL, SLEEP_TIMEOUT, STD_DEV
class Action(IntEnum):
    BUY = 1
    SELL = 2
    CANCEL = 3
    MRKET_BUY = 4
    MARKET_SELL = 5

class ServerMsg(IntEnum):
    ACK = 10
    FILL = 15
    REJECT = 30

class ErrorCodes(IntEnum):
    pass

class RequestIdGenerator:
    def __init__(self):
        self._next = 1

    def get(self):
        rid = self._next
        self._next += 1

        # Wrap around after 2^32 - 1
        if self._next > 0xFFFFFFFF:
            self._next = 1

        return rid

class Bot:
    def __init__(self, asset_initial_price: int, metrics_queue: asyncio.Queue):
        self.server_host = SERVER_HOST
        self.server_port = SERVER_PORT
        self.b_id = str(uuid.uuid4())
        self.client_id = None
        self.is_connected = False
        self.sleep_timeout = SLEEP_TIMEOUT
        self.buys = 0
        self.sells = 0
        self.canceled = 0
        self.max_orders = 10000
        self.orders_sent = 0
        self.p_buy = PROB_BUY 
        self.p_sell = PROB_SELL
        self.p_cancel = PROB_CANCEL
        self.asset_price = asset_initial_price
        self.std = STD_DEV 
        self.order_ids = []
        self.metrics_queue = metrics_queue
        self.network_latency = {}
        self.req_id_gen = RequestIdGenerator()

    async def listen_to_exchange(self, reader, writer):
        """
        listen to exchange server continusly until exited.
        Order acknowledgement (ACK) (25 Bytes)
            1 Byte (Msg Type) + 4 byte (Int: ClientReq Id) + 4 bytes (Int: Order ID) + time_recv + time_send
            '!Biiqq'
        Order Execution (FILL) (33 Bytes)
            1 Byte (Msg Type) + 4 byte (Int: ClientReq Id) + 4 bytes (Int: Order ID) + 4 bytes (Int: Filled Quantity) + 4 bytes (Float: Executed Price)+ time_recv + time_send

            '!Biiifqq'
        Order Rejected/Error (REJ) (6 Bytes)
            1 Byte (Msg Type) + 4 bytes (Int: Order ID) + 1 bytes (Byte: Error Code)
            '!BiB'
        Each message is prefixed with a length byte.
        ex: [9]0x0A6734432300000231, which is encoding for, ACK[1 byte], Client request ID[4 byte], Order ID[4 byte]
        """
        print(f"[+] Bot {self.b_id} started listening loop.")
        while True:
            try:
                # Listening Binary encoded messages
                length = (await reader.readexactly(1))[0]
                msg_packet = await reader.readexactly(length)

                time_arrival_ns = time.time_ns()

                if length == 25:
                    # ACK message
                    msg_type, client_req_id, order_id, t_recv, t_send = struct.unpack("!Biiqq", msg_packet)

                    t_start_ns = self.network_latency.pop(client_req_id, None)
                    if t_start_ns is not None:
                        total_rtt_ms = (time_arrival_ns - t_start_ns) / 1_000_000.0
                        server_processing_ms = (t_send - t_recv)  / 1_000_000.0
                        wire_flight_ms = total_rtt_ms - server_processing_ms

                        try:
                            self.metrics_queue.put_nowait((total_rtt_ms, server_processing_ms, wire_flight_ms))
                        except asyncio.QueueFull:
                            pass

                    self.order_ids.append(order_id)


                elif length == 33:
                    # Trade Execution message
                    msg_type, client_req_id, order_id, fill_qty, exec_price, t_recv, t_send = struct.unpack("!Biiifqq", msg_packet)

                elif length == 10:
                    msg_type, client_req_id, order_id, error_code = struct.unpack("!BiiB", msg_packet)


            except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
                print(f"[-] Bot {self.b_id}: Error listening to Exchange server!") 
                break
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    def encode_order(self, action: Action, client_req_id: int, order_id: int|None, size: int|None, price: float|None) -> bytes:
        """fixed length binary encoding"""

        if action in (Action.BUY, Action.SELL):
            # Limit Orders
            return struct.pack('!Biif', action.value, client_req_id, size, price)
        elif action in (Action.MARKET_BUY, Action.MARKET_SELL):
            # Market Orders
            # Send 0.0 as price placeholder
            return struct.pack('!Biif', action.value, client_req_id, size, 0.0)
        elif action == Action.CANCEL:
            return struct.pack('!Bii', action.value, client_req_id, order_id)


    def order_action(self):
        """" Decides its action"""

        if self.order_ids:
            # You can balance these probabilities from your Nomad env files later
            action = random.choices(
                    ["BUY", "SELL", "MARKET_BUY", "MARKET_SELL", "CANCEL"],
                    weights=[self.p_buy, self.p_sell, self.p_market_buy, self.p_market_sell, self.p_cancel], 
                    k=1
                    )[0]
        else:
            action = random.choices( 
                                    ["BUY", "SELL", "MARKET_BUY", "MARKET_SELL"],
                                    weights=[self.p_buy, self.p_sell, self.p_market_buy, self.p_market_sell],
                                    k=1
                                    )[0]

        # Limit Execution Pipeline
        if action in ["BUY", "SELL"]:        
            size = max(1, round(random.gauss(50, 20)))
            price = max(0.01, round(random.gauss(self.asset_price, self.std), 2))
            return action, size, price
        # Market Execution Pipeline
        elif action in ["MARKET_BUY", "MARKET_SELL"]:
            size = max(1, round(random.gauss(30, 10))) # Typically slightly different sizes
            return action, size
        # Cancel Execution Pipeline
        else:
            order_id_to_cancel = random.randint(0, len(self.order_ids)-1)
            order_id = self.order_ids[order_id_to_cancel]
            self.order_ids.remove(order_id)
            return action, order_id

    async def strategy_coroutine(self, writer):

        """
        Wait for some time, take action, order blast. 
        Sends order packets:
            BUY/SELL (13 Bytes)
                1 Byte + 4 byte (Int: ClientReq Id) + 4 byte (Int: Size) + 4 byte (float: Price)
                '!Biif'
            CANCEL (9 Bytes)
                1 Byte + 4 byte (Int: ClientReq Id) + 4 byte (Int: Order Id)
                'Bii'
        """
        while self.is_connected:
            # wait for some time before taking order action
            await asyncio.sleep(self.sleep_timeout)

            command = self.order_action() 
            client_req_id = self.req_id_gen.get()    

            if len(command) == 3:
                # BUY/SELL
                action, size, price = command
                act_enum = Action.BUY if action == "BUY" else Action.SELL
                if act_enum == Action.BUY: self.buys += 1
                else: self.sells += 1
                order_bin_packet = self.encode_order(act_enum, client_req_id=client_req_id, size=size, price=price)
            elif len(command) == 2 and isinstance(command[0], str) and command[0].startswith("MARKET"):
                action, order_id = command
                act_enum = Action.MARKET_BUY if action == "MARKET_BUY" else Action.MARKET_SELL
                if act_enum == Action.MARKET_BUY: self.buys += 1
                else: self.sells += 1
                order_bin_packet = self.encode_order(act_enum, client_req_id=client_req_id, order_id=None, size=size, price=None)
            else:
                action, order_id = command
                self.canceled += 1
                order_bin_packet = self.encode_order(Action.CANCEL, client_req_id=client_req_id, order_id=order_id, size=None, price=None)

            # write to the server commands
            writer.write(order_bin_packet)
            # record the time msg sent
            self.network_latency[client_req_id] = time.time_ns()
            await writer.drain()

    async def start(self):
        """connects to exchange server"""
        reader, writer = await asyncio.open_connection(
                self.server_host,
                self.server_port
                )

        self.is_connected = True
        local_port = writer.get_extra_info('peername')[1]
        self.client_id = f"CLIENT_{local_port}"
        print(f"[+] Connected to Exchange! Assigned Identifier: {self.client_id}")

        self.listen_task = asyncio.create_task(self.listen_to_exchange(reader, writer))
        self.strategy_task = asyncio.create_task(self.strategy_coroutine(writer))
