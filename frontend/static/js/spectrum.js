(function () {
  const API = '/api';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsBase = protocol + '//' + window.location.host + API;
  const SAMPLE_RATE_HZ = 200000;

  const sensorSelect = document.getElementById('spectrum-sensor');
  const windowSelect = document.getElementById('spectrum-window');
  const scaleSelect = document.getElementById('spectrum-scale');
  const channelSelect = document.getElementById('spectrum-channel');
  const fftPointsSelect = document.getElementById('spectrum-fft-points');
  const fftCustomInput = document.getElementById('spectrum-fft-custom');
  const fftCustomGroup = document.getElementById('spectrum-fft-custom-group');
  const updateRateSelect = document.getElementById('spectrum-update-rate');
  const bufferDurationEl = document.getElementById('spectrum-buffer-duration');
  const dfEl = document.getElementById('spectrum-df');
  const btnStart = document.getElementById('btn-start-spectrum');
  const btnStop = document.getElementById('btn-stop-spectrum');
  const statusEl = document.getElementById('spectrum-status-msg');
  const infoEl = document.getElementById('spectrum-info');
  const plotContainer = document.getElementById('spectrum-plot-container');

  let ws = null;

  function getFftPoints() {
    var val = fftPointsSelect ? fftPointsSelect.value : '262144';
    if (val === 'custom' && fftCustomInput && fftCustomInput.value) {
      var n = parseInt(fftCustomInput.value, 10);
      return isNaN(n) || n < 8192 ? 262144 : Math.min(1048576, n);
    }
    var n = parseInt(val, 10);
    return isNaN(n) ? 262144 : n;
  }

  function updateBufferInfo() {
    var n = getFftPoints();
    var duration = (n / SAMPLE_RATE_HZ).toFixed(2);
    var df = n > 0 ? (SAMPLE_RATE_HZ / n).toFixed(2) : '-';
    if (bufferDurationEl) bufferDurationEl.textContent = duration;
    if (dfEl) dfEl.textContent = df + ' Hz';
  }

  if (fftPointsSelect) {
    fftPointsSelect.addEventListener('change', function () {
      if (fftCustomGroup) fftCustomGroup.style.display = (this.value === 'custom') ? 'block' : 'none';
      updateBufferInfo();
    });
  }
  if (fftCustomInput) {
    fftCustomInput.addEventListener('input', updateBufferInfo);
  }
  updateBufferInfo();

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? '#f44336' : '#e8e8e8';
  }

  function updatePlot(frame) {
    // #region agent log
    if (!frame || frame.error || !frame.freq_hz) {
      fetch('http://127.0.0.1:7597/ingest/2eba02d0-2656-4543-949f-b2edf34af300',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6cbc7e'},body:JSON.stringify({sessionId:'6cbc7e',location:'spectrum.js:updatePlot',message:'early_return',data:{noFrame:!frame,error:!!(frame&&frame.error),noFreqHz:!(frame&&frame.freq_hz)},timestamp:Date.now(),hypothesisId:'D'})}).catch(function(){});
      return;
    }
    var y = frame.magnitude_db != null ? frame.magnitude_db : frame.magnitude_linear;
    if (y == null) {
      fetch('http://127.0.0.1:7597/ingest/2eba02d0-2656-4543-949f-b2edf34af300',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6cbc7e'},body:JSON.stringify({sessionId:'6cbc7e',location:'spectrum.js:updatePlot',message:'no_y',data:{},timestamp:Date.now(),hypothesisId:'D'})}).catch(function(){});
      return;
    }
    // #endregion
    var isDb = frame.magnitude_db != null;
    var trace = {
      x: frame.freq_hz,
      y: y,
      type: 'scatter',
      mode: 'lines',
      name: 'Magnitude'
    };
    var yTitle = isDb ? 'Magnitude (dB)' : 'Magnitude (linear)';
    var layout = {
      margin: { t: 30, r: 30, b: 50, l: 60 },
      xaxis: { title: 'Frequência (Hz)', showgrid: true },
      yaxis: { title: yTitle, showgrid: true },
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
    var nFft = frame.fft_points != null ? frame.fft_points : '-';
    var updateInterval = frame.update_interval_s != null ? frame.update_interval_s : 0.1;
    var updateHz = (1 / updateInterval).toFixed(1);
    var ch = frame.channel != null ? 'CH' + frame.channel : '';
    var win = frame.window_type || '';
    var extra = (ch || win) ? ' | ' + (ch ? ch + ' ' : '') + (win ? win : '') : '';
    infoEl.textContent = 'Δf = ' + df + ' Hz | N_FFT = ' + nFft + ' | 0 - 100 kHz | pontos no gráfico = ' + n + ' | Atualização ~' + updateHz + ' Hz' + extra;
  }

  function startSpectrum() {
    var sensor = sensorSelect.value;
    var fftPoints = getFftPoints();
    var updateIntervalS = updateRateSelect ? parseFloat(updateRateSelect.value) : 0.1;
    if (isNaN(updateIntervalS) || updateIntervalS <= 0) updateIntervalS = 0.1;
    var windowType = (windowSelect && windowSelect.value) ? windowSelect.value : 'hamming';
    var scale = (scaleSelect && scaleSelect.value) ? scaleSelect.value : 'db';
    var useDb = scale === 'db';
    var channel = (channelSelect && channelSelect.value) ? channelSelect.value : '0';
    btnStart.disabled = true;
    btnStop.disabled = false;
    showStatus('Resetando DAQ e conectando ao espectro...');
    var wsUrl = wsBase + '/spectrum/stream?sensor=' + encodeURIComponent(sensor) +
      '&fft_points=' + encodeURIComponent(fftPoints) +
      '&update_interval_s=' + encodeURIComponent(updateIntervalS) +
      '&sample_rate=' + encodeURIComponent(SAMPLE_RATE_HZ) +
      '&window_type=' + encodeURIComponent(windowType) +
      '&db=' + (useDb ? 'true' : 'false') +
      '&channel=' + encodeURIComponent(channel);
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
      showStatus('Espectro ativo – sensor ' + sensor + '. Aguardando buffer e primeiro frame...');
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
