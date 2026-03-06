(function () {
  const API = '/api';
  const calibToggle = document.getElementById('calib-toggle');
  const calibRate = document.getElementById('calib-rate');
  const calibChunk = document.getElementById('calib-chunk');
  const calibInterval = document.getElementById('calib-interval');
  const calibFitPoints = document.getElementById('calib-fit-points');
  const calibStatusMsg = document.getElementById('calib-status-msg');
  const plotSensorSelect = document.getElementById('plot-sensor');
  const plotXy = document.getElementById('plot-xy');
  const fitRunSelect = document.getElementById('fit-run-select');
  const fitSensorSelect = document.getElementById('fit-sensor');
  const btnFitFromRun = document.getElementById('btn-fit-from-run');
  const fitFromRunMsg = document.getElementById('fit-from-run-msg');
  const paramsBySensor = document.getElementById('params-by-sensor');
  const paramsPlaceholder = document.getElementById('params-placeholder');
  const calibPhaseMsg = document.getElementById('calib-phase-msg');
  const calibResetBtn = document.getElementById('calib-reset-btn');

  let pollIntervalId = null;
  const POLL_MS = 2000;

  function getSelectedSensors() {
    const nodes = document.querySelectorAll('input[name="calib-sensors"]:checked');
    return Array.from(nodes).map(function (n) { return n.value; });
  }

  function setSelectedSensors(sensors) {
    document.querySelectorAll('input[name="calib-sensors"]').forEach(function (cb) {
      cb.checked = sensors && sensors.indexOf(cb.value) !== -1;
    });
  }

  function refreshStatus() {
    fetch(API + '/calibration/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        calibToggle.checked = (data.user_wants_on !== undefined ? data.user_wants_on : !!data.running);
        if (data.params) {
          calibRate.value = data.params.rate_hz || 1000;
          calibChunk.value = data.params.chunk_duration_s || 1;
          calibInterval.value = data.params.interval_s || 5;
          calibFitPoints.value = data.params.fit_points || 50000;
          setSelectedSensors(data.params.sensors);
        }
        if (data.phase === 'initial') {
          calibPhaseMsg.style.display = 'block';
          calibPhaseMsg.textContent = 'Coletando 10 s iniciais (1000 Hz) por sensor...';
          calibPhaseMsg.style.color = '#1976d2';
        } else {
          calibPhaseMsg.style.display = 'none';
        }
        if (data.running) {
          calibStatusMsg.textContent = data.phase === 'initial' ? 'Calibração iniciando (10 s iniciais)...' : 'Calibração ativa.';
          calibStatusMsg.style.color = '';
        } else {
          calibStatusMsg.textContent = 'Calibração parada.';
          calibStatusMsg.style.color = '#666';
        }
        if (pollIntervalId == null && data.running) {
          startPolling();
        } else if (!data.running && pollIntervalId != null) {
          stopPolling();
        }
      })
      .catch(function () {
        calibStatusMsg.textContent = 'Erro ao obter status.';
        calibStatusMsg.style.color = '#f44336';
      });
  }

  function startPolling() {
    if (pollIntervalId != null) return;
    pollIntervalId = setInterval(function () {
      refreshStatus();
      updatePlot(plotSensorSelect.value);
      refreshParamsDisplay();
    }, POLL_MS);
  }

  function stopPolling() {
    if (pollIntervalId != null) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
  }

  function updatePlot(sensor) {
    if (!sensor) sensor = plotSensorSelect.value;
    fetch(API + '/calibration/fit/' + encodeURIComponent(sensor))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const R = data.R || [];
        const G = data.G || [];
        const curve = data.ellipse_curve || { x: [], y: [] };
        const traces = [];
        if (R.length && G.length) {
          traces.push({
            x: R,
            y: G,
            type: 'scatter',
            mode: 'markers',
            name: 'R, G',
            marker: { size: 3 }
          });
        }
        if (curve.x && curve.x.length) {
          traces.push({
            x: curve.x,
            y: curve.y,
            type: 'scatter',
            mode: 'lines',
            name: 'Elipse'
          });
        }
        const layout = {
          margin: { t: 30, r: 30, b: 40, l: 50 },
          xaxis: { title: 'R (canal 0)' },
          yaxis: { title: 'G (canal 1)' },
          showLegend: true
        };
        if (traces.length) {
          Plotly.newPlot(plotXy, traces, layout, { responsive: true });
        } else {
          Plotly.newPlot(plotXy, [{ x: [], y: [], type: 'scatter', mode: 'markers' }], layout, { responsive: true });
        }
      })
      .catch(function () {
        Plotly.newPlot(plotXy, [{ x: [], y: [], type: 'scatter', mode: 'markers' }], {
          margin: { t: 30, r: 30, b: 40, l: 50 },
          xaxis: { title: 'R (canal 0)' },
          yaxis: { title: 'G (canal 1)' }
        }, { responsive: true });
      });
  }

  function refreshParamsDisplay() {
    const sensors = ['S1', 'S2', 'S3', 'S4'];
    const promises = sensors.map(function (s) {
      return fetch(API + '/calibration/params/' + s).then(function (r) { return r.json(); });
    });
    Promise.all(promises).then(function (results) {
      let html = '';
      results.forEach(function (data, i) {
        const s = sensors[i];
        if (data.params && Array.isArray(data.params) && data.params.length === 5) {
          const p = data.params;
          html += '<div class="params-sensor"><strong>' + s + '</strong>: p=' + p[0].toFixed(4) + ', q=' + p[1].toFixed(4) +
            ', r=' + p[2].toFixed(4) + ', s=' + p[3].toFixed(4) + ', alpha=' + p[4].toFixed(4) +
            (data.updated_utc ? ' — ' + data.updated_utc : '') + '</div>';
        } else {
          html += '<div class="params-sensor"><strong>' + s + '</strong>: sem calibração</div>';
        }
      });
      if (html) {
        paramsPlaceholder.style.display = 'none';
        paramsBySensor.innerHTML = html;
      }
    }).catch(function () {
      paramsPlaceholder.style.display = 'block';
    });
  }

  function loadRunsForFit() {
    fetch(API + '/files')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const runs = data.runs || [];
        fitRunSelect.innerHTML = '<option value="">-- Selecione uma run --</option>' +
          runs.map(function (r) {
            return '<option value="' + (r.run_id || r.run_id) + '">' + (r.run_id || '') + '</option>';
          }).join('');
      })
      .catch(function () {});
  }

  calibToggle.addEventListener('change', function () {
    if (calibToggle.checked) {
      const sensors = getSelectedSensors();
      if (!sensors.length) {
        calibToggle.checked = false;
        calibStatusMsg.textContent = 'Selecione ao menos um sensor.';
        calibStatusMsg.style.color = '#f44336';
        return;
      }
      fetch(API + '/calibration/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rate_hz: parseFloat(calibRate.value) || 1000,
          chunk_duration_s: parseFloat(calibChunk.value) || 1,
          interval_s: parseFloat(calibInterval.value) || 5,
          fit_points: parseInt(calibFitPoints.value, 10) || 50000,
          sensors: sensors
        })
      })
        .then(function (r) { return r.json(); })
        .then(function () {
          refreshStatus();
          startPolling();
        })
        .catch(function () {
          calibToggle.checked = false;
          calibStatusMsg.textContent = 'Erro ao iniciar calibração.';
          calibStatusMsg.style.color = '#f44336';
        });
    } else {
      fetch(API + '/calibration/stop', { method: 'POST' })
        .then(function () { refreshStatus(); stopPolling(); })
        .catch(function () { refreshStatus(); });
    }
  });

  plotSensorSelect.addEventListener('change', function () {
    updatePlot(plotSensorSelect.value);
  });

  calibResetBtn.addEventListener('click', function () {
    const sensors = getSelectedSensors();
    if (!sensors.length) {
      calibStatusMsg.textContent = 'Selecione ao menos um sensor para reiniciar com 10 s iniciais.';
      calibStatusMsg.style.color = '#f44336';
      return;
    }
    calibResetBtn.disabled = true;
    calibStatusMsg.textContent = 'Resetando e recolhendo 10 s iniciais...';
    calibStatusMsg.style.color = '#666';
    fetch(API + '/calibration/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        restart: true,
        rate_hz: parseFloat(calibRate.value) || 1000,
        chunk_duration_s: parseFloat(calibChunk.value) || 1,
        interval_s: parseFloat(calibInterval.value) || 5,
        fit_points: parseInt(calibFitPoints.value, 10) || 50000,
        sensors: sensors
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        calibToggle.checked = !!data.restarted;
        if (data.restarted) {
          startPolling();
          calibStatusMsg.textContent = 'Coletando 10 s iniciais (1000 Hz) por sensor...';
        } else {
          calibStatusMsg.textContent = 'Buffer e último fit zerados.';
        }
        calibStatusMsg.style.color = '#666';
        updatePlot(plotSensorSelect.value);
        refreshParamsDisplay();
      })
      .catch(function () {
        calibStatusMsg.textContent = 'Erro ao resetar.';
        calibStatusMsg.style.color = '#f44336';
      })
      .finally(function () { calibResetBtn.disabled = false; });
  });

  btnFitFromRun.addEventListener('click', function () {
    const runId = (fitRunSelect.value || '').trim();
    const sensor = fitSensorSelect.value;
    if (!runId) {
      fitFromRunMsg.textContent = 'Selecione uma run.';
      fitFromRunMsg.style.color = '#f44336';
      return;
    }
    btnFitFromRun.disabled = true;
    fitFromRunMsg.textContent = 'Aplicando fit...';
    fitFromRunMsg.style.color = '#666';
    fetch(API + '/calibration/fit-from-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, sensor: sensor })
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || r.statusText); });
        return r.json();
      })
      .then(function (data) {
        fitFromRunMsg.textContent = 'Fit gravado. Sensor ' + sensor + ' — ' + (data.updated_utc || '');
        fitFromRunMsg.style.color = '';
        updatePlot(sensor);
        refreshParamsDisplay();
      })
      .catch(function (err) {
        fitFromRunMsg.textContent = 'Erro: ' + err.message;
        fitFromRunMsg.style.color = '#f44336';
      })
      .finally(function () { btnFitFromRun.disabled = false; });
  });

  refreshStatus();
  loadRunsForFit();
  refreshParamsDisplay();
  updatePlot(plotSensorSelect.value);
})();
