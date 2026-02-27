(function () {
  const API = '/api';
  const loadingEl = document.getElementById('files-loading');
  const tableEl = document.getElementById('files-table');
  const tableBody = tableEl.querySelector('tbody');

  function loadFiles() {
    loadingEl.style.display = 'block';
    tableEl.style.display = 'none';
    fetch(API + '/files')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loadingEl.style.display = 'none';
        tableBody.innerHTML = '';
        if (!data.runs || data.runs.length === 0) {
          tableBody.innerHTML = '<tr><td colspan="6">Nenhuma run encontrada.</td></tr>';
          tableEl.style.display = 'table';
          return;
        }
        data.runs.forEach(function (run) {
          const runId = run.run_id || run.timestamp || '';
          const testName = run.test_name || '-';
          const channels = (run.channels && run.channels.length) ? run.channels.join(',') : '-';
          const fs = run.sample_rate_hz != null ? run.sample_rate_hz : '-';
          const dur = run.duration_s != null ? run.duration_s : '-';
          const binUrl = API + '/files/' + encodeURIComponent(runId) + '/download/bin';
          const jsonUrl = API + '/files/' + encodeURIComponent(runId) + '/download/json';
          const tr = document.createElement('tr');
          tr.innerHTML =
            '<td>' + (run.timestamp || runId) + '</td>' +
            '<td>' + testName + '</td>' +
            '<td>' + channels + '</td>' +
            '<td>' + fs + '</td>' +
            '<td>' + dur + '</td>' +
            '<td><a href="' + binUrl + '" download>BIN</a> <a href="' + jsonUrl + '" download>JSON</a></td>';
          tableBody.appendChild(tr);
        });
        tableEl.style.display = 'table';
      })
      .catch(function (err) {
        loadingEl.textContent = 'Erro ao carregar: ' + err.message;
        loadingEl.style.display = 'block';
      });
  }

  loadFiles();
})();
