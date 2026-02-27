(function () {
  const API = '/api';
  const statusEl = document.getElementById('status-msg');
  const plotContainer = document.getElementById('plot-container');
  const valuesTableBody = document.getElementById('values-table').querySelector('tbody');
  const metricsTableBody = document.getElementById('metrics-table').querySelector('tbody');
  const btnStart = document.getElementById('btn-start');
  const btnStop = document.getElementById('btn-stop');

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? '#f44336' : '#e8e8e8';
  }

  function buildChannelCheckboxes() {
    const div = document.getElementById('channel-checkboxes');
    div.innerHTML = '';
    for (let i = 0; i < 8; i++) {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = i;
      cb.name = 'ch';
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' CH' + i + ' '));
      div.appendChild(label);
    }
  }

  function buildSensorCheckboxes() {
    const div = document.getElementById('sensor-checkboxes');
    div.innerHTML = '';
    ['S1', 'S2', 'S3', 'S4'].forEach(function (s) {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = s;
      cb.name = 'sensor';
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + s + ' '));
      div.appendChild(label);
    });
  }

  function getSelectedChannels() {
    const ch = [];
    document.querySelectorAll('input[name="ch"]:checked').forEach(function (cb) {
      ch.push(parseInt(cb.value, 10));
    });
    return ch;
  }

  function getSelectedSensors() {
    const s = [];
    document.querySelectorAll('input[name="sensor"]:checked').forEach(function (cb) {
      s.push(cb.value);
    });
    return s;
  }

  function startAcquisition() {
    const channels = getSelectedChannels();
    const sensors = getSelectedSensors();
    if (channels.length === 0 && sensors.length === 0) {
      showStatus('Selecione ao menos um canal ou sensor.', true);
      return;
    }
    const sampleRate = parseInt(document.getElementById('sample-rate').value, 10);
    const duration = parseInt(document.getElementById('duration').value, 10);
    const testName = document.getElementById('test-name').value.trim();

    btnStart.disabled = true;
    btnStop.disabled = false;
    showStatus('Iniciando aquisição...');

    fetch(API + '/acquisition/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channels: channels.length ? channels : undefined,
        sensors: sensors.length ? sensors : undefined,
        sample_rate_hz: sampleRate,
        duration_s: duration,
        test_name: testName
      })
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || r.statusText); });
        return r.json();
      })
      .then(function (data) {
        showStatus('Aquisição iniciada. Run ID: ' + data.run_id + ' — aguardando conclusão...');
        startStatusPolling();
      })
      .catch(function (err) {
        showStatus('Erro: ' + err.message, true);
        btnStart.disabled = false;
        btnStop.disabled = true;
      });
  }

  function stopAcquisition() {
    fetch(API + '/acquisition/stop', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function () {
        showStatus('Parada solicitada (scan finito pode terminar em breve).');
      });
  }

  let pollInterval = null;

  function startStatusPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollStatus, 800);
  }

  function stopStatusPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  function pollStatus() {
    fetch(API + '/acquisition/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status === 'running') {
          showStatus('Aquisição em andamento...');
          return;
        }
        if (data.status === 'done') {
          stopStatusPolling();
          btnStart.disabled = false;
          btnStop.disabled = true;
          showStatus('Aquisição concluída. Run ID: ' + data.run_id);
          renderPreview(data.preview);
          renderValues(data.preview);
          renderMetrics(data.metrics);
          return;
        }
        if (data.status === 'error') {
          stopStatusPolling();
          btnStart.disabled = false;
          btnStop.disabled = true;
          showStatus('Erro: ' + (data.error_message || 'desconhecido'), true);
        }
      })
      .catch(function () {});
  }

  function renderPreview(preview) {
    if (!preview || !preview.t || !preview.channels) {
      plotContainer.innerHTML = '<p>Sem dados de preview.</p>';
      return;
    }
    const t = preview.t;
    const channels = preview.channels;
    const traces = Object.keys(channels).map(function (ch) {
      return { x: t, y: channels[ch], name: 'CH' + ch, type: 'scatter', mode: 'lines' };
    });
    if (typeof Plotly !== 'undefined') {
      Plotly.newPlot(plotContainer, traces, {
        margin: { t: 30, r: 30, b: 40, l: 50 },
        xaxis: { title: 'Tempo (s)' },
        yaxis: { title: 'Tensão (V)' },
        showLegend: true
      }, { responsive: true });
    } else {
      plotContainer.innerHTML = '<p>Plotly não carregado. Dados disponíveis em Métricas.</p>';
    }
  }

  function renderValues(preview) {
    valuesTableBody.innerHTML = '';
    if (!preview || !preview.channels) return;
    Object.keys(preview.channels).forEach(function (ch) {
      const ys = preview.channels[ch];
      const last = ys && ys.length ? ys[ys.length - 1] : '-';
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>CH' + ch + '</td><td>' + (typeof last === 'number' ? last.toFixed(4) : last) + '</td>';
      valuesTableBody.appendChild(tr);
    });
  }

  function renderMetrics(metrics) {
    metricsTableBody.innerHTML = '';
    if (!metrics || !metrics.length) return;
    metrics.forEach(function (m) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + m.channel + '</td>' +
        '<td>' + (m.rms != null ? m.rms.toFixed(4) : '-') + '</td>' +
        '<td>' + (m.dc != null ? m.dc.toFixed(4) : '-') + '</td>' +
        '<td>' + (m.peak != null ? m.peak.toFixed(4) : '-') + '</td>' +
        '<td>' + (m.clipping_pct != null ? m.clipping_pct : '-') + '%</td>';
      metricsTableBody.appendChild(tr);
    });
  }

  btnStart.addEventListener('click', startAcquisition);
  btnStop.addEventListener('click', stopAcquisition);

  buildChannelCheckboxes();
  buildSensorCheckboxes();
})();
