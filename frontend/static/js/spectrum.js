(function () {
  const API = '/api';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsBase = protocol + '//' + window.location.host + API;

  const sensorSelect = document.getElementById('spectrum-sensor');
  const intervalSelect = document.getElementById('spectrum-interval');
  const btnStart = document.getElementById('btn-start-spectrum');
  const btnStop = document.getElementById('btn-stop-spectrum');
  const statusEl = document.getElementById('spectrum-status-msg');
  const infoEl = document.getElementById('spectrum-info');
  const plotContainer = document.getElementById('spectrum-plot-container');

  let ws = null;

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? '#f44336' : '#e8e8e8';
  }

  function updatePlot(frame) {
    if (!frame || frame.error || !frame.freq_hz || !frame.magnitude_db) return;
    var trace = {
      x: frame.freq_hz,
      y: frame.magnitude_db,
      type: 'scatter',
      mode: 'lines',
      name: 'Magnitude'
    };
    var layout = {
      margin: { t: 30, r: 30, b: 50, l: 60 },
      xaxis: { title: 'Frequência (Hz)', showgrid: true },
      yaxis: { title: 'Magnitude (dB)', showgrid: true },
      uirevision: 'spectrum'
    };
    if (typeof Plotly !== 'undefined') {
      if (plotContainer.data) {
        Plotly.react(plotContainer, [trace], layout, { responsive: true });
      } else {
        Plotly.newPlot(plotContainer, [trace], layout, { responsive: true });
      }
    }
  }

  function updateInfo(frame) {
    if (!frame || frame.error) {
      infoEl.textContent = '';
      return;
    }
    var df = frame.df_hz != null ? frame.df_hz.toFixed(2) : '-';
    var n = frame.n_points != null ? frame.n_points : '-';
    var interval = frame.interval_s != null ? frame.interval_s : 0.5;
    var updateHz = (1 / interval).toFixed(1);
    infoEl.textContent = 'Δf = ' + df + ' Hz | 0 - 100 kHz | N = ' + n + ' pontos | Atualização ~' + updateHz + ' Hz';
  }

  function startSpectrum() {
    var sensor = sensorSelect.value;
    var intervalS = intervalSelect.value;
    btnStart.disabled = true;
    btnStop.disabled = false;
    showStatus('Resetando DAQ e conectando ao espectro...');
    var wsUrl = wsBase + '/spectrum/stream?sensor=' + encodeURIComponent(sensor) +
      '&interval_s=' + encodeURIComponent(intervalS) + '&sample_rate=200000';
    fetch(API + '/daq/reset', { method: 'POST' })
      .then(function () {
        ws = new WebSocket(wsUrl);
        attachSpectrumWsHandlers(sensor);
      })
      .catch(function () {
        ws = new WebSocket(wsUrl);
        attachSpectrumWsHandlers(sensor);
      });
  }

  function attachSpectrumWsHandlers(sensor) {
    ws.onopen = function () {
      showStatus('Espectro ativo – sensor ' + sensor + '. Aguardando primeiro frame...');
    };
    ws.onmessage = function (event) {
      try {
        var frame = JSON.parse(event.data);
        if (frame.error) {
          showStatus('Erro: ' + frame.error, true);
          return;
        }
        updatePlot(frame);
        updateInfo(frame);
        if (statusEl.textContent.indexOf('Aguardando') !== -1) {
          showStatus('Espectro em tempo real – sensor ' + sensor);
        }
      } catch (e) {}
    };
    ws.onerror = function () {
      showStatus('Erro de conexão WebSocket.', true);
    };
    ws.onclose = function () {
      if (ws !== this) return;
      ws = null;
      btnStart.disabled = false;
      btnStop.disabled = true;
      if (statusEl.textContent.indexOf('Erro') === -1) {
        showStatus('Espectro parado.');
      }
      fetch(API + '/daq/reset', { method: 'POST' }).catch(function () {});
    };
  }

  function stopSpectrum() {
    if (ws) {
      ws.close();
    }
    fetch(API + '/spectrum/stop', { method: 'POST' })
      .then(function () { return fetch(API + '/daq/reset', { method: 'POST' }); })
      .catch(function () {});
  }

  btnStart.addEventListener('click', startSpectrum);
  btnStop.addEventListener('click', stopSpectrum);
})();
