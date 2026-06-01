import socket
import json
import time
import random
import threading

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8888

def listen_to_exchange(sock):
    while True:
        try:
            data = sock.recv(4096).decode('utf-8')
            if not data:
                print("\n[!] Disconnected from the exchange server.")
                break
            
            # Line buffering parsing layer
            for line in data.split("\n"):
                cleaned = line.strip()
                if not cleaned:
                    continue
                
                try:
                    msg = json.loads(cleaned)
                    if msg.get("type") == "FILL":
                        print(f"\n[ALERT] ** EXECUTION FILL ** -> Traded {msg['size']} units @ ${msg['price']:.2f}")
                        continue # Move to the next line immediately
                        
                    # 2. Check for order entry confirmations independently
                    if msg.get("status") == "ACK":
                        print(f"\n[ACK] -> Order Accepted. Assigned ID: {msg['order_id']}")
                        continue
                        
                    # 3. Check for cancellation confirmations independently
                    if msg.get("status") == "CANCELED":
                        print(f"\n[ACK] -> Order {msg['order_id']} Canceled.")
                        continue
                except json.JSONDecodeError:
                    pass
        except (ConnectionResetError, BrokenPipeError):
            break

def run_client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
        # Find out what unique local network port the OS gave this specific process
        local_port = sock.getsockname()[1]
        print(f"[+] Connected to Exchange! Your temporary Client ID is: CLIENT_{local_port}")
    except ConnectionRefusedError:
        print("[-] Exchange server is offline.")
        return

    # Start the network listener on a background thread so it doesn't block keyboard input
    threading.Thread(target=listen_to_exchange, args=(sock,), daemon=True).start()

    print("\nCommands format: \n  > BUY size price\n  > SELL size price\n  > CANCEL id\n")
    
    while True:
        try:
            user_input = input("Order Entry > ").strip().upper().split()
            if not user_input: 
                continue
            
            command = user_input[0]
            if command == "EXIT":
                break
                
            payload = {}
            if command in ("BUY", "SELL") and len(user_input) == 3:
                payload = {"action": command, "size": int(user_input[1]), "price": int(user_input[2])}
            elif command == "CANCEL" and len(user_input) == 2:
                payload = {"action": command, "order_id": int(user_input[1])}
            else:
                print("[-] Invalid format. Ex: BUY 100 5 or CANCEL 1")
                continue

            sock.sendall((json.dumps(payload) + "\n").encode('utf-8'))
            
        except (KeyboardInterrupt, EOFError):
            break

    sock.close()
    print("[-] Logged off safely.")

if __name__ == "__main__":
    run_client()



