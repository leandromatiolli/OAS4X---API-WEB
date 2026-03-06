(function () {
  const API = '/api';
  const runIdInput = document.getElementById('run-id-input');
  const btnLoad = document.getElementById('btn-load');
  const errorEl = document.getElementById('analysis-error');
  const contentEl = document.getElementById('analysis-content');
  const plotTimeEl = document.getElementById('plot-time');
  const plotFftEl = document.getElementById('plot-fft');
  const fftChannelSelect = document.getElementById('fft-channel');
  const statsTableBody = document.getElementById('stats-table').querySelector('tbody');
  const csvDecimate = document.getElementById('csv-decimate');
  const csvDownload = document.getElementById('csv-download');
  const demodSection = document.getElementById('demod-section');
  const demodSectionTitle = document.getElementById('demod-section-title');
  const plotDemodEl = document.getElementById('plot-demod');
  const btnDownloadDemodCsv = document.getElementById('btn-download-demod-csv');
  var lastDemodData = null;

  function getRunId() {
    var params = new URLSearchParams(window.location.search);
    return params.get('run_id') || runIdInput.value.trim();
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = 'block';
    contentEl.style.display = 'none';
  }

  function clearError() {
    errorEl.style.display = 'none';
  }

  function loadPreview() {
    var runId = getRunId();
    if (!runId) {
      showError('Informe o run_id.');
      return;
    }
    clearError();
    btnLoad.disabled = true;
    fetch(API + '/files/' + encodeURIComponent(runId) + '/preview')
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || r.statusText); });
        return r.json();
      })
      .then(function (data) {
        runIdInput.value = runId;
        contentEl.style.display = 'block';
        renderTimePlot(data);
        populateFftChannels(data);
        loadFft(runId, 0);
        loadStats(runId);
        updateCsvLink(runId);
        loadDemod(runId);
      })
      .catch(function (err) {
        showError('Erro: ' + err.message);
      })
      .finally(function () { btnLoad.disabled = false; });
  }

  function renderTimePlot(data) {
    var t = data.t;
    var channels = data.channels;
    var traces = Object.keys(channels).map(function (ch) {
      return { x: t, y: channels[ch], name: 'CH' + ch, type: 'scatter', mode: 'lines' };
    });
    Plotly.newPlot(plotTimeEl, traces, {
      margin: { t: 30, r: 30, b: 40, l: 50 },
      xaxis: { title: 'Tempo (s)' },
      yaxis: { title: 'Tensão (V)' },
      showLegend: true
    }, { responsive: true });
  }

  function populateFftChannels(data) {
    var chs = Object.keys(data.channels || {});
    fftChannelSelect.innerHTML = chs.map(function (c) {
      return '<option value="' + c + '">Canal ' + c + '</option>';
    }).join('');
    fftChannelSelect.addEventListener('change', function () {
      loadFft(getRunId(), parseInt(fftChannelSelect.value, 10));
    });
  }

  function loadFft(runId, channel) {
    fetch(API + '/files/' + encodeURIComponent(runId) + '/fft?channel=' + channel)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var trace = {
          x: data.freq_hz,
          y: data.magnitude_db,
          type: 'scatter',
          mode: 'lines',
          name: 'CH' + channel
        };
        Plotly.newPlot(plotFftEl, [trace], {
          margin: { t: 30, r: 30, b: 40, l: 50 },
          xaxis: { title: 'Frequência (Hz)' },
          yaxis: { title: 'Magnitude (dB)' }
        }, { responsive: true });
      });
  }

  function loadStats(runId) {
    fetch(API + '/files/' + encodeURIComponent(runId) + '/stats')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        statsTableBody.innerHTML = '';
        (data.stats || []).forEach(function (s) {
          var tr = document.createElement('tr');
          tr.innerHTML =
            '<td>' + s.channel + '</td>' +
            '<td>' + (s.rms != null ? s.rms.toFixed(4) : '-') + '</td>' +
            '<td>' + (s.rms_window_mean != null ? s.rms_window_mean.toFixed(4) : '-') + '</td>' +
            '<td>' + (s.p95 != null ? s.p95.toFixed(4) : '-') + '</td>' +
            '<td>' + (s.p99 != null ? s.p99.toFixed(4) : '-') + '</td>';
          statsTableBody.appendChild(tr);
        });
      });
  }

  function loadDemod(runId) {
    lastDemodData = null;
    if (!demodSection || !plotDemodEl) return;
    fetch(API + '/files/' + encodeURIComponent(runId) + '/demod')
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.demod || Object.keys(data.demod).length === 0) {
          demodSectionTitle.style.display = 'none';
          demodSection.style.display = 'none';
          return;
        }
        lastDemodData = data;
        demodSectionTitle.style.display = 'block';
        demodSection.style.display = 'block';
        var traces = [];
        Object.keys(data.demod).forEach(function (sensor) {
          var d = data.demod[sensor];
          var t = d.time_s || (d.phase && d.phase.length ? d.phase.map(function (_, i) { return i; }) : []);
          traces.push({
            x: t,
            y: d.phase || [],
            type: 'scatter',
            mode: 'lines',
            name: sensor
          });
        });
        Plotly.newPlot(plotDemodEl, traces, {
          margin: { t: 30, r: 30, b: 40, l: 50 },
          xaxis: { title: 'Tempo (s)' },
          yaxis: { title: 'Fase (rad)' },
          showLegend: true
        }, { responsive: true });
      })
      .catch(function () {
        demodSectionTitle.style.display = 'none';
        demodSection.style.display = 'none';
      });
  }

  function updateCsvLink(runId) {
    var dec = parseInt(csvDecimate.value, 10) || 1;
    csvDownload.href = API + '/files/' + encodeURIComponent(runId) + '/export/csv?decimate=' + dec;
    csvDownload.download = runId + '.csv';
  }

  csvDecimate.addEventListener('change', function () {
    var runId = getRunId();
    if (runId) updateCsvLink(runId);
  });

  btnDownloadDemodCsv.addEventListener('click', function () {
    if (!lastDemodData || !lastDemodData.demod) return;
    var runId = lastDemodData.run_id || 'demod';
    var rows = [];
    var sensors = Object.keys(lastDemodData.demod);
    if (sensors.length === 0) return;
    var first = lastDemodData.demod[sensors[0]];
    var t = first.time_s || [];
    if (!t.length && first.phase) {
      for (var i = 0; i < first.phase.length; i++) t.push(i);
    }
    rows.push('time_s,' + sensors.join(','));
    for (var i = 0; i < t.length; i++) {
      var row = String(t[i]);
      sensors.forEach(function (s) {
        var ph = lastDemodData.demod[s].phase;
        row += ',' + (ph && ph[i] != null ? ph[i] : '');
      });
      rows.push(row);
    }
    var csv = rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = runId + '_demod.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  });

  btnLoad.addEventListener('click', loadPreview);

  if (getRunId()) {
    loadPreview();
  }
})();
