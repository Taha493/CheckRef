// Polls the job status, animates the ring and the steps, and opens the report when it is ready.
(function () {
  var box = document.getElementById('job');
  if (!box) return;
  var id = box.dataset.id;
  var total = +box.dataset.steps;
  var ring = document.getElementById('ring');
  var CIRCLE = 515.2;
  var $ = function (x) { return document.getElementById(x); };

  function setRing(fraction) {
    ring.style.strokeDashoffset = String(CIRCLE * (1 - fraction));
  }

  function setSteps(current) {
    document.querySelectorAll('#stepper li').forEach(function (li, i) {
      li.classList.toggle('done', i < current);
      li.classList.toggle('active', i === current);
    });
  }

  function show(s) {
    if (s.state === 'done') {
      box.classList.remove('queued'); box.classList.add('done');
      setSteps(total); setRing(1);
      $('big').textContent = '100%'; $('small').textContent = 'ready';
      $('state').innerHTML = 'Report ready, opening it…';
      setTimeout(function () { location.replace('/jobs/' + id + '/report'); }, 900);
      return false;
    }
    if (s.state === 'failed' || s.state === 'deleted' || s.state === 'missing') {
      location.replace('/jobs/' + id); return false;
    }
    if (s.state === 'queued') {
      box.classList.add('queued');
      setSteps(-1); setRing(0);
      $('big').textContent = '#' + s.position;
      $('small').textContent = 'in the queue';
      $('state').innerHTML = '<span class="dots">' + (s.position === 1
        ? 'Next in line' : 'Waiting for the checks ahead of yours') + '</span>';
      $('elapsed-text').textContent = 'Starting soon';
      return true;
    }
    box.classList.remove('queued');
    var current = Math.max(s.step - 1, 0);
    var pct = Math.round(100 * current / s.steps);
    setSteps(current); setRing(current / s.steps);
    $('big').textContent = pct + '%';
    $('small').textContent = 'done';
    $('state').innerHTML = '<span class="dots"></span>';
    $('state').firstChild.textContent = s.stage_label;
    var m = Math.floor(s.seconds / 60), sec = s.seconds % 60;
    $('elapsed-text').textContent = 'Running for ' + (m ? m + ' min ' : '') + sec + ' s';
    return true;
  }

  function poll() {
    fetch('/api/jobs/' + id, { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (s) { if (show(s)) setTimeout(poll, 1500); })
      .catch(function () { setTimeout(poll, 4000); });
  }
  poll();
})();
