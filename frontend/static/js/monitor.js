(function () {
  const API = '/api';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsBase = protocol + '//' + window.location.host + API;

  const sensorSelect = document.getElementById('sensor-select');
  const btnStart = document.getElementById('btn-start-monitor');
  const btnStop = document.getElementById('btn-stop-monitor');
  const statusEl = document.getElementById('monitor-status-msg');
  const plotContainer = document.getElementById('monitor-plot-container');

  let ws = null;

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? '#f44336' : '#e8e8e8';
  }

  function updatePlot(frame) {
    if (!frame || frame.error || !frame.t || !frame.ch0) return;
    const t = frame.t;
    const traces = [
      { x: t, y: frame.ch0, name: 'CH0 (V)', type: 'scatter', mode: 'lines' },
      { x: t, y: frame.ch1, name: 'CH1 (V)', type: 'scatter', mode: 'lines' },
      { x: t, y: frame.diff, name: 'Diferencial (V)', type: 'scatter', mode: 'lines' }
    ];
    var layout = {
      margin: { t: 30, r: 30, b: 40, l: 50 },
      xaxis: { title: 'Tempo (s)' },
      yaxis: { title: 'Tensão (V)', range: [0, 5], fixedrange: true },
      showLegend: true
    };
    if (typeof Plotly !== 'undefined') {
      if (plotContainer.data) {
        Plotly.react(plotContainer, traces, layout, { responsive: true });
      } else {
        Plotly.newPlot(plotContainer, traces, layout, { responsive: true });
      }
    }
  }

  function startMonitor() {
    const sensor = sensorSelect.value;
    btnStart.disabled = true;
    btnStop.disabled = false;
    showStatus('Conectando ao sensor ' + sensor + '...');
    const wsUrl = wsBase + '/monitor/stream?sensor=' + encodeURIComponent(sensor);
    ws = new WebSocket(wsUrl);
    ws.onopen = function () {
      showStatus('Monitor ativo – sensor ' + sensor + '. Atualização em tempo real.');
    };
    ws.onmessage = function (event) {
      try {
        const frame = JSON.parse(event.data);
        if (frame.error) {
          showStatus('Erro: ' + frame.error, true);
          return;
        }
        updatePlot(frame);
      } catch (e) {}
    };
    ws.onerror = function () {
      showStatus('Erro de conexão WebSocket.', true);
    };
    ws.onclose = function () {
      btnStart.disabled = false;
      btnStop.disabled = true;
      if (statusEl.textContent.indexOf('Erro') === -1) {
        showStatus('Monitor parado.');
      }
      ws = null;
    };
  }

  function stopMonitor() {
    if (ws) {
      ws.close();
      ws = null;
    }
    fetch(API + '/monitor/stop', { method: 'POST' }).catch(function () {});
  }

  btnStart.addEventListener('click', startMonitor);
  btnStop.addEventListener('click', stopMonitor);
})();
