from bot_01 import Bot
from config import ASSET_INITIAL_PRICE, NUM_BOTS

async def main_async():
    
    print(f"[+] Bootstrapping swarm container with {NUM_BOTS} bots ...")

    swarm = [Bot(ASSET_INITIAL_PRICE) for _ in range(NUM_BOTS)]

    for bot in swarm:
        await Bot.start()
    
    # keeps the main process alive untill all bots disconnect from the sever.
    while any(bot.is_connected for bot in swarm):
        await asyncio.sleep(1)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
