## Benching System for Simulated Exchanges.
Benchmarking is based upon the metrics collected from the swarm bot attacks. Metrics such as percentiles of round trip time, server processing time, network wire time. Other metrics to be considered are resource usage of the simulated Exchange like cpu utilization, response time, etc.

### Current developments
- A fully working test Exchange server in `.cpp`, exposing all necessary UDP and TCP ports for communication.
- First phase Trading Bot, listens to the exchange, strategises and puts orders (BUY, SELL, CANCEL) on the exchange server. It also exposes necessary ports for communication and telemetry
- Backend, a functional backend in FastAPI binding all together, exposing websockets for sending data to UI. Handles UDP connections, collects the telemetry stream using an implemented `Accumulator` which stores and processes the instream data for summary metrics, which are then used for performance evaluation.
- frontend, a simple designed UI in HTML/CSS & JavScript to collect the data using websockets.

### How to run in dev mode
The system consists of four components:

- Client — dashboard frontend
- Backend — WebSocket/telemetry server
- Exchange Engine — simulated exchange
- Bots — automated trading clients

### Startup

Start the components in separate terminals.

#### 1. Start the frontend
```
cd client_ui
npx serve
```
#### 2. Start the backed
```
cd backend
python3 main.py
```

#### 3. Start the engine (compile first and change name as per changes)
```
cd tests
./engine_main.exe
```

#### 4. Start the Swarm Bots
```
cd trading_bots
python3 main.py
```

### System performance
Tested currently with only `10` Bots with timeout `0.01 seconds`(time a bot takes before its another order) reaching `OPS` (Orders Per Second) 900~.
The benching system showed quite ease on these testing with `event loop lag` not exceeding `1.5ms`
also `Accumulator performance` in processing was in range `1 ~ 2ms`. 
/*These are visual estimates*/ even then it proves that their is a room for much large scale testing. 

Performance of the test exchange was average, on average the system score was around `55` when the `OPS` was low (10~20). But when cranked up the `OPS` the average score increased `80`. /*These are visual estimates*/. I cant figure what might cause this increase.

/*Visual estimates were made since the test ran for 2 minutes and accumulation was not done, once done accurate metrics will be computed they will be mentioned here, also since the values didnt fluctuate randomly and the system performed in a stable manner.*/

### Technologies used 
Python, FastAPI, Asyncio, cpp, 

### Further work on
Deployement using any distributed tool for large scale testing of the system and large scale bot swarm attacks for more stress testing. Collecting more data/telemetry for more better performance evaluation.
Experimenting with different trading bots design/algorithms.
