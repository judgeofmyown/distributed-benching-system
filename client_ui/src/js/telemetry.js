const ws_url = "ws://localhost:8000/ws/telemetry"
const metric_container = document.getElementById("metric")
const score_container = document.getElementById("system-score");

const bench_metric_container = document.getElementById("bench-metric");
const bench_score_container = document.getElementById("bench-score");

function connectWebSocketTelemetry(){
    const socket = new WebSocket(ws_url);

    socket.onopen = () => {
        console.log("Telemetry UDP connected successfully...")
    };

    socket.onmessage = (event) => {
        const metric_message = JSON.parse(event.data);
        console.log("metric message got!!")
        if (metric_message.type == "BOT_TELE_BATCH"){
            const metric_dict = metric_message.metrics;
            const health_dict = metric_message.system_health;
            console.log(health_dict)

            requestAnimationFrame(() => {
                if (metric_dict) {
                    renderMetrics(metric_dict, metric_container);
                    if (metric_dict.system_score !== undefined){
                        score_container.textContent = metric_dict.system_score.toFixed(1);
                    }
                }

                if (health_dict) {
                    renderMetrics(health_dict, bench_metric_container);
                    if (health_dict.bot_emission_rate !== undefined){
                        bench_score_container.textContent = health_dict.bot_emission_rate.toFixed(0) + " OPS";
                    }
                }

            });
        }else{
            console.error("Invalid message type")
        }
    }

    socket.onerror = (err) => {
        console.error("ES:Error ", err);
        socket.close();
    };
}

function renderMetrics(metric_dict, container) {
    container.innerHTML = Object.entries(metric_dict)
        .filter(([name, _]) => name !== "system_score" && name !== "bot_emission_rate")
        .map(([name, value]) => `
            <div class="metric-item">
                <span class="metric-name">${name.replace(/_/g, ' ')}</span>
                <span class="metric-value">${typeof value === 'number' ? value.toFixed(3) : value}</span>
            </div>
        `).join("")
}

connectWebSocketTelemetry();