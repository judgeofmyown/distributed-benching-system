from collections import deque
from pprint import pprint
import numpy as np

class Accumulator:
    def __init__(self, window_size: int):
        # self.data_queue = deque()
        self.data_rtt = deque()
        self.data_srvr_procc = deque()
        self.data_ntwrk_wire = deque()
        self.window_size = window_size # will determine the size of this accumulator

    def accumulate(self, metrics: list):
        rtt_data = float(metrics[0].split(':')[1].split('|')[0])
        srvr_procc = float(metrics[1].split(':')[1].split('|')[0])
        ntwrk_wire = float(metrics[2].split(':')[1].split('|')[0])

        if len(self) < self.window_size:
            self.data_rtt.append(rtt_data)
            self.data_srvr_procc.append(srvr_procc)
            self.data_ntwrk_wire.append(ntwrk_wire)
        else:
            self.data_rtt.popleft()
            self.data_srvr_procc.popleft()
            self.data_ntwrk_wire.popleft()

            self.data_rtt.append(rtt_data)
            self.data_srvr_procc.append(srvr_procc)
            self.data_ntwrk_wire.append(ntwrk_wire)        

    def __len__(self):
        return len(self.data_rtt)

    def compute_metrics(self, data: deque):
        data = np.array(data)

        n = len(data)
        if n == 0:
            return {
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "std": 0.0,
                "iqr": 0.0,
                "jitter": 0.0,
            }

        p50 = float(np.percentile(data, 50))
        p90 = float(np.percentile(data, 90))
        p95 = float(np.percentile(data, 95))
        p99 = float(np.percentile(data, 99))

        p25 = float(np.percentile(data, 25))
        p75 = float(np.percentile(data, 75))
        iqr = p75 - p25

        std = float(np.std(data, ddof=1)) if n>1 else 0.0
        if n>1:
            diffs = [
                abs(data[i] - data[i-1]) for i in range(1, n)
            ]
            jitter = float(sum(diffs) / len(diffs))
        else:
            jitter = 0.0

        return {
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
            "std": std,
            "iqr": iqr,
            "jitter": jitter,
        }

    def get_metrics(self) -> dict[str, float]:
        rtt_m = self.compute_metrics(self.data_rtt)
        srvr_proc_m = self.compute_metrics(self.data_srvr_procc)
        wire_m = self.compute_metrics(self.data_ntwrk_wire)

        return {
            "rtt_50": round(rtt_m["p50"], 4),
            "rtt_p90": round(rtt_m["p90"], 4),
            "rtt_p95": round(rtt_m["p95"], 4),
            "rtt_99": round(rtt_m["p99"], 4),
            "rtt_std": round(rtt_m["std"], 4),
            "rtt_iqr": round(rtt_m["iqr"], 4),
            "rtt_jitter": round(rtt_m["jitter"], 4),

            "srvr_proc_50": round(srvr_proc_m["p50"], 4),
            "srvr_proc_p90": round(srvr_proc_m["p90"], 4),
            "srvr_proc_p95": round(srvr_proc_m["p95"], 4),
            "srvr_proc_99": round(srvr_proc_m["p99"], 4),
            "srvr_proc_std": round(srvr_proc_m["std"], 4),
            "srvr_proc_iqr": round(srvr_proc_m["iqr"], 4),
            "srvr_proc_jitter": round(srvr_proc_m["jitter"], 4),

            "wire_flight_50": round(wire_m["p50"], 4),
            "wire_flight_p90": round(wire_m["p90"], 4),
            "wire_flight_p95": round(wire_m["p95"], 4),
            "wire_flight_99": round(wire_m["p99"], 4),
            "wire_flight_std": round(wire_m["std"], 4),
            "wire_flight_iqr": round(wire_m["iqr"], 4),
            "wire_flight_jitter": round(wire_m["jitter"], 4),
        }

    def clean(self):
        self.data_rtt.clear()
        self.data_srvr_procc.clear()
        self.data_ntwrk_wire.clear()


class Test:
    def __init__(self):
        self.test_data = [
    [
        "exchange.bot.rtt:12.431|ms\n",
        "exchange.engine.processing:4.217|ms\n",
        "exchange.network.wire:2.803|ms"
    ],
    [
        "exchange.bot.rtt:8.752|ms\n",
        "exchange.engine.processing:3.891|ms\n",
        "exchange.network.wire:1.924|ms"
    ],
    [
        "exchange.bot.rtt:15.209|ms\n",
        "exchange.engine.processing:5.103|ms\n",
        "exchange.network.wire:3.412|ms"
    ],
    [
        "exchange.bot.rtt:6.843|ms\n",
        "exchange.engine.processing:2.756|ms\n",
        "exchange.network.wire:1.637|ms"
    ],
    [
        "exchange.bot.rtt:21.576|ms\n",
        "exchange.engine.processing:6.428|ms\n",
        "exchange.network.wire:4.215|ms"
    ],
    [
        "exchange.bot.rtt:10.394|ms\n",
        "exchange.engine.processing:3.642|ms\n",
        "exchange.network.wire:2.187|ms"
    ],
    [
        "exchange.bot.rtt:4.928|ms\n",
        "exchange.engine.processing:2.103|ms\n",
        "exchange.network.wire:1.284|ms"
    ],
    [
        "exchange.bot.rtt:18.637|ms\n",
        "exchange.engine.processing:5.817|ms\n",
        "exchange.network.wire:3.926|ms"
    ],
    [
        "exchange.bot.rtt:9.115|ms\n",
        "exchange.engine.processing:3.284|ms\n",
        "exchange.network.wire:1.856|ms"
    ],
    [
        "exchange.bot.rtt:13.804|ms\n",
        "exchange.engine.processing:4.593|ms\n",
        "exchange.network.wire:2.741|ms"
    ]
]

    def run(self):
        window_size = 3
        accumulator = Accumulator(window_size=window_size)
        print(f"[.] Instantiated accumulator of size {window_size}")

        for test_metric in self.test_data:
            accumulator.accumulate(test_metric)
        print("[.] all together accumulated successfully")

        pprint(accumulator.data_rtt)
        pprint(accumulator.data_srvr_procc)
        pprint(accumulator.data_ntwrk_wire)

        accumulator.clean()

        for test_metric in self.test_data:
            accumulator.accumulate(test_metric)
            metrics = accumulator.get_metrics()
            pprint(metrics)
        print(f"Finished!")

# test1 = Test()
# test1.run()