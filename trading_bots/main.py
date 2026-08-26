from bot_01 import Bot
from config import ASSET_INITIAL_PRICE, NUM_BOTS, TELEMETRY_HOST, TELEMETRY_PORT
import asyncio
import os
import socket

METRICS_QUEUE = asyncio.Queue(maxsize = 100000)
PROCESS_TIMEOUT_SECONDS = 200

async def telemetry_reporter_worker(telemetry_host, telemetry_port):
    """ Drains the single shared container queue and streams metrics over UDP """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[+] Container telemetry worker active. Streaming to {telemetry_host}:{telemetry_port}")
    
    while True:
        try:
            total_rtt, server_proc, wire_time = await METRICS_QUEUE.get()
            
            # Format using standard StatsD metrics format
            payload = (
                f"exchange.bot.rtt:{total_rtt:.3f}|ms\n"
                f"exchange.engine.processing:{server_proc:.3f}|ms\n"
                f"exchange.network.wire:{wire_time:.3f}|ms"
            ).encode('utf-8')
            
            sock.sendto(payload, (telemetry_host, telemetry_port))
            METRICS_QUEUE.task_done()
        except asyncio.CancelledError:
            break
        except Exception:
            # Prevent telemetry glitches from crashing the container
            await asyncio.sleep(0.5) 
    sock.close()

async def main_async():
    
    print(f"[+] Bootstrapping swarm container with {NUM_BOTS} bots ...")

    telemetry_host = os.getenv("TELEMETRY_HOST", TELEMETRY_HOST)
    telemetry_port = int(os.getenv("TELEMETRY_PORT", TELEMETRY_PORT))

    reporter_task = asyncio.create_task(telemetry_reporter_worker(telemetry_host, telemetry_port))

    swarm = [Bot(ASSET_INITIAL_PRICE, METRICS_QUEUE) for _ in range(NUM_BOTS)]

    bot_tasks = [asyncio.create_task(bot.start()) for bot in swarm]

    bots_group = asyncio.gather(*bot_tasks)

    try:
        await asyncio.wait_for(bots_group, timeout=PROCESS_TIMEOUT_SECONDS)
        print("[-] All bots disconnected naturally.")
    except asyncio.TimeoutError:
        print(f"[!] Timeout of {PROCESS_TIMEOUT_SECONDS}s reaached. Initiating graceful shutdown...")

        for bot in swarm:
            await bot.stop()

        print("[*] Waiting for network drain...")
        await asyncio.gather(*bot_tasks, return_exceptions=True)
    finally:
        print("[-] Stopping telemetry worker...")
        reporter_task.cancel()
        await asyncio.gather(reporter_task, return_exceptions=True)
        # await asyncio.gather(*bot_tasks, return_exceptions=True)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
