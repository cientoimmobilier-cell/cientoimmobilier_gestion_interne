(function () {
  'use strict';

  // Confirmation dialog for all forms with data-confirm attribute
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var msg = form.getAttribute('data-confirm');
    if (msg && !confirm(msg)) {
      e.preventDefault();
    }
  });

  // Auto-dismiss flash messages after 5 seconds
  var alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.5s ease';
      alert.style.opacity = '0';
      setTimeout(function () {
        alert.remove();
      }, 500);
    }, 5000);
  });
})();
