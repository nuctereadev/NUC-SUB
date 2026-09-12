/* nuc-features: per-config QR codes, self-contained */
(function () {
  'use strict';

  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (attrs[k] == null) continue;
        e.setAttribute(k, attrs[k]);
      }
    }
    if (html) e.innerHTML = html;
    return e;
  }
  function raw(s) { return String(s || '').replace(/&amp;/g, '&'); }

  var ov = el('div', { id: 'nucOverlay' });
  ov.innerHTML =
    '<div class="nuc-modal">' +
      '<button class="nuc-close" aria-label="Close">&times;</button>' +
      '<h3 id="nucTitle">QR</h3>' +
      '<img id="nucQrImg" width="240" height="240" alt="QR" style="display:none">' +
      '<span class="nuc-link" id="nucQrLink"></span>' +
    '</div>';
  document.body.appendChild(ov);

  var overlayEl = document.getElementById('nucOverlay');
  var titleEl = document.getElementById('nucTitle');

  function openOv() { overlayEl.classList.add('open'); }
  function closeOv() { overlayEl.classList.remove('open'); }

  overlayEl.addEventListener('click', function (e) {
    if (e.target === overlayEl || e.target.classList.contains('nuc-close')) closeOv();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeOv(); });

  function showQr(link) {
    var QR = window.NucQR;
    var img = document.getElementById('nucQrImg');
    var linkEl = document.getElementById('nucQrLink');
    var text = raw(link);
    titleEl.textContent = 'کد QR کانفیگ / Config QR';
    if (linkEl) linkEl.textContent = text;
    if (!img) return;
    if (!QR) { openOv(); return; }
    try {
      var q = QR(0, 'M');
      q.addData(text);
      q.make();
      img.src = q.createDataURL(5, 6);
      img.style.display = 'block';
      openOv();
    } catch (err) {
      img.style.display = 'none';
      if (linkEl) linkEl.textContent = text + ' -- ' + (err && err.message ? err.message : 'QR failed');
      openOv();
    }
  }

  document.querySelectorAll('[data-link]').forEach(function (card) {
    if (card.querySelector('.nucqr-btn')) return;
    var isA = card.tagName === 'A' || card.tagName === 'BUTTON';
    var btn = el(
      isA ? 'span' : 'button',
      { class: 'nucqr-btn', type: isA ? null : 'button', 'aria-label': 'QR' },
      '<svg viewBox="0 0 24 24"><path d="M3 11h8V3H3v8zm2-6h4v4H5V5zM13 3v2h2V3h-2zm6 6v8h2v-8h-2zm-2-6h4v4h-4V3zm-8 8h2v2H9v-2zm4 0h2v4h-2v-4zm-4 4h4v-2h-2v-2H9v4zm4 2h2v4h-2v-4zm-6 4h6v-2H7v2zm12-2h-2v2h-2v2h4v-4zM5 17h2v-2H5v2zm12-8v2h2v-2h-2z"/></svg>'
    );
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      showQr(card.getAttribute('data-link'));
    });
    card.appendChild(btn);
  });
})();