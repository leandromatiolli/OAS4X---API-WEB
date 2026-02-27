(function () {
  const INTERVAL_MS = 5000;
  const pre = document.getElementById('health-json');
  const loading = document.getElementById('health-loading');
  const table = document.getElementById('health-table');
  const tbody = table.querySelector('tbody');

  function fetchHealth() {
    fetch('/health')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loading.style.display = 'none';
        pre.style.display = 'block';
        pre.textContent = JSON.stringify(data, null, 2);
        renderTable(data);
      })
      .catch(function (err) {
        loading.textContent = 'Erro: ' + err.message;
      });
  }

  function renderTable(data) {
    tbody.innerHTML = '';
    var rows = [
      ['Status', data.status],
      ['Serviço', data.service || '-'],
      ['Uptime', data.uptime_human || data.uptime_seconds + ' s'],
      ['CPU temp (°C)', data.cpu_temp_c != null ? data.cpu_temp_c.toFixed(1) : 'N/A'],
    ];
    if (data.memory) {
      rows.push(['RAM', data.memory.percent + '% (' + data.memory.available_mb + ' MB livres)']);
    }
    if (data.disk) {
      rows.push(['Disco ' + data.disk.path, data.disk.percent + '% (' + data.disk.free_gb + ' GB livres)']);
    }
    if (data.daq) {
      rows.push(['DAQ', data.daq.connected ? data.daq.product + ' (' + data.daq.unique_id + ')' : 'Desconectado: ' + (data.daq.error || '')]);
    }
    rows.forEach(function (r) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td><strong>' + r[0] + '</strong></td><td>' + r[1] + '</td>';
      tbody.appendChild(tr);
    });
    table.style.display = 'table';
  }

  fetchHealth();
  setInterval(fetchHealth, INTERVAL_MS);
})();
