import os

SERVER_HOST         = os.getenv("SERVER_HOST", "localhost")
SERVER_PORT         = int(os.getenv("SERVER_PORT", "8888"))
PROB_BUY            = int(os.getenv("PROB_BUY", "45"))
PROB_SELL           = int(os.getenv("PROB_SELL", "45"))
PROB_CANCEL         = int(os.getenv("PROB_CANCEL", "10"))
ASSET_INITIAL_PRICE = int(os.getenv("ASSET_INITIAL_PRICE", "150"))
STD_DEV             = float(os.getenv("std_dev", "0.5"))
SLEEP_TIMEOUT       = int(os.getenv("SLEEP_TIMEOUT", "2"))
NUM_BOTS            = int(os.getenv("NUM_BOTS", "10"))
