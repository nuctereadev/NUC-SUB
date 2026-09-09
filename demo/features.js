/* nuc-features: per-config QR + VPN apps launcher (self-contained) */
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

  var APPS = [
    { n: 'v2rayN',      p: 'Windows',     c: '#2F7BF6', h: 'https://github.com/2dust/v2rayN/releases' },
    { n: 'Nekoray',     p: 'Windows',     c: '#7C5CFF', h: 'https://github.com/MatsuriDayo/nekoray/releases' },
    { n: 'Hiddify',     p: 'All',         c: '#22C55E', h: 'https://github.com/hiddify/hiddify-app/releases' },
    { n: 'v2rayNG',     p: 'Android',     c: '#10B981', h: 'https://github.com/2dust/v2rayNG/releases' },
    { n: 'NekoBox',     p: 'Android',     c: '#F97316', h: 'https://github.com/MatsuriDayo/NekoBoxForAndroid/releases' },
    { n: 'Streisand',   p: 'Android',     c: '#E11D48', h: 'https://github.com/StreisandEffect/streisand/releases' },
    { n: 'Shadowrocket',p: 'iPhone',      c: '#38BDF8', h: 'https://apps.apple.com/app/shadowrocket/id932747118' },
    { n: 'V2Box',       p: 'iPhone/Android', c: '#8B5CF6', h: 'https://apps.apple.com/app/v2box-v2ray-client/id6446814696' },
    { n: 'sing-box',    p: 'iPhone',      c: '#0EA5E9', h: 'https://apps.apple.com/app/sing-box/id6451272673' },
    { n: 'Qv2ray',      p: 'Linux',       c: '#6366F1', h: 'https://github.com/Qv2ray/Qv2ray/releases' }
  ];

  var ov = el('div', { id: 'nucOverlay', class: '', 'data-mode': 'qr' });
  ov.innerHTML =
    '<div class="nuc-modal">' +
      '<button class="nuc-close" aria-label="Close">&times;</button>' +
      '<h3 id="nucTitle">QR</h3>' +
      '<div id="nucQrView">' +
        '<img id="nucQrImg" width="240" height="240" alt="QR" style="display:none">' +
        '<span class="nuc-link" id="nucQrLink"></span>' +
      '</div>' +
      '<div id="nucAppsView">' +
        '<div class="nuc-apps"></div>' +
        '<div class="nuc-apps-note">برنامه را نصب کنید و سرویس / کانفیگ را داخل آن اضافه کنید.&#10;Install the app and import your subscription / config.</div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(ov);

  var overlayEl = document.getElementById('nucOverlay');
  var qrView = document.getElementById('nucQrView');
  var appsView = document.getElementById('nucAppsView');
  var titleEl = document.getElementById('nucTitle');
  var appsGrid = appsView.querySelector('.nuc-apps');

  APPS.forEach(function (a) {
    var icon = el('span', { class: 'nuc-app-icon', style: 'background:linear-gradient(135deg,' + a.c + ',rgba(15,30,70,.85))' }, a.n.charAt(0).toUpperCase());
    var b = document.createElement('b'); b.textContent = a.n;
    var s = document.createElement('small'); s.textContent = a.p;
    var link = el('a', { href: a.h, target: '_blank', rel: 'noopener', class: 'nuc-app' });
    link.appendChild(icon); link.appendChild(b); link.appendChild(s);
    appsGrid.appendChild(link);
  });

  function openMode(mode) {
    overlayEl.setAttribute('data-mode', mode);
    qrView.style.display = mode === 'qr' ? '' : 'none';
    appsView.style.display = mode === 'apps' ? '' : 'none';
    overlayEl.classList.add('open');
  }
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
    if (!QR) { openMode('qr'); return; }
    try {
      var q = QR(0, 'M');
      q.addData(text);
      q.make();
      img.src = q.createDataURL(5, 6);
      img.style.display = 'block';
      openMode('qr');
    } catch (err) {
      img.style.display = 'none';
      if (linkEl) linkEl.textContent = text + ' -- ' + (err && err.message ? err.message : 'QR failed');
      openMode('qr');
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

  var fab = el('button', { class: 'nuc-fab', type: 'button' },
    '<svg viewBox="0 0 24 24"><path d="M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm1 14h-2v-2h2v2zm0-4h-2V7h2v4z"/></svg><span>VPN Apps</span>');
  fab.addEventListener('click', function () {
    titleEl.textContent = 'برنامه‌های اتصال / VPN Apps';
    openMode('apps');
  });
  document.body.appendChild(fab);
})();