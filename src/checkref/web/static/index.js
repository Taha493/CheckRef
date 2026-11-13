// Home page: drag and drop, the chosen file and the busy button.
(function () {
  var form = document.getElementById('upload');
  var drop = document.getElementById('drop');
  var input = document.getElementById('file');
  var picked = document.getElementById('picked');
  var maxBytes = parseFloat(form.dataset.maxMb) * 1024 * 1024;

  function size(n) {
    return n < 1024 * 1024 ? Math.max(1, Math.round(n / 1024)) + ' KB' : (n / 1024 / 1024).toFixed(1) + ' MB';
  }

  function show() {
    var f = input.files && input.files[0];
    if (!f) { picked.classList.remove('show'); return; }
    var ext = (f.name.split('.').pop() || '').toLowerCase();
    var problem = ext !== 'pdf' && ext !== 'docx' ? 'Only PDF and Word (.docx) files can be checked.'
      : f.size > maxBytes ? 'This file is larger than ' + form.dataset.maxMb + ' MB.' : '';
    document.getElementById('ficon').textContent = ext === 'docx' ? 'DOCX' : ext.toUpperCase().slice(0, 4);
    document.getElementById('fname').textContent = f.name;
    document.getElementById('fmeta').textContent = problem || size(f.size) + ' · ready to check';
    picked.classList.toggle('bad', !!problem);
    picked.classList.remove('show'); void picked.offsetWidth; picked.classList.add('show');
    input.setCustomValidity(problem);
  }

  input.addEventListener('change', show);
  ['dragenter', 'dragover'].forEach(function (e) {
    drop.addEventListener(e, function (ev) { ev.preventDefault(); drop.classList.add('over'); });
  });
  ['dragleave', 'drop'].forEach(function (e) {
    drop.addEventListener(e, function () { drop.classList.remove('over'); });
  });
  drop.addEventListener('drop', function (ev) {
    ev.preventDefault();
    if (ev.dataTransfer && ev.dataTransfer.files.length) { input.files = ev.dataTransfer.files; show(); }
  });

  form.addEventListener('submit', function () {
    var go = document.getElementById('go');
    go.classList.add('busy');
    go.querySelector('.txt').textContent = 'Uploading';
    setTimeout(function () { go.disabled = true; }, 0); // after the form data is taken
  });

  // Coming back to the page (browser back button) must not leave the button busy.
  window.addEventListener('pageshow', function () {
    var go = document.getElementById('go');
    go.classList.remove('busy'); go.disabled = false;
    go.querySelector('.txt').textContent = 'Check references';
  });
})();
