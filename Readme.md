## Benching System for Simulated Exchanges.
Benchmarking is based upon the metrics collected from the swarm bot attacks. Metrics such as percentiles of round trip time, server processing time, network wire time. Other metrics to be considered are resource usage of the simulated Exchange like cpu utilization, response time, etc.

### Current developments
- A fully working test Exchange server in `.cpp`, exposing all necessary UDP and TCP ports for communication.
- First phase Trading Bot, listens to the exchange, strategises and puts orders (BUY, SELL, CANCEL) on the exchange server. It also exposes necessary ports for communication and telemetry
- Backend, a functional backend in FastAPI binding all together, exposing websockets for sending data to UI. Handles UDP connections, collects the telemetry stream using an implemented `Accumulator` which stores and processes the instream data for summary metrics, which are then used for performance evaluation.
- frontend, a simple designed UI in HTML/CSS & JavScript to collect the data using websockets.

### How to run in dev mode
instructions dedo :pray

### Technologies used 
Python, FastAPI, Asyncio, cpp, 

### Further work on
Deployement using any distributed tool for large scale testing of the system and large scale bot swarm attacks for more stress testing. Collecting more data/telemetry for more better performance evaluation.
Experimenting with different trading bots design/algorithms.
