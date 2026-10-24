/**
 * ProVision Infra – Karriere (/karriere)
 * Repliziert die Funktionen der Hauptseite (Elementor):
 *  - Scroll-Animationen (fadeInUp/Down/Left/Right, mobile Varianten)
 *  - Zähler-Animation (Counter)
 *  - Burger-Menü (Dropdown)
 *  - Testimonial-Karussell (Autoplay, Pfeile, Dots, Swipe, aktiver Slide mit gelbem Rahmen)
 *  - FAQ-Akkordeon
 *  - Stellen-Filter & Stellen-Akkordeon
 *  - Smooth Scroll für Anker mit Header-Offset
 */
(function () {
  'use strict';

  var MOBILE = 767;
  function isMobile() { return window.innerWidth <= MOBILE; }
  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Scroll-Animationen (Elementor: Waypoint-Offset 90 %, einmalig) ---------- */
  function animName(el) {
    return (isMobile() && el.getAttribute('data-anim-mobile')) || el.getAttribute('data-anim') || 'fadeInUp';
  }
  function initAnimations() {
    var items = Array.prototype.slice.call(document.querySelectorAll('.anim'));
    if (!items.length) return;
    if (prefersReduced || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('animated'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        el.classList.add('animated', animName(el));
        io.unobserve(el);
      });
    }, { threshold: 0, rootMargin: '0px 0px -10% 0px' });
    items.forEach(function (el) { io.observe(el); });
    // Sicherheitsnetz: Elemente, die nach dem Laden bereits sichtbar sind
    window.addEventListener('load', function () {
      items.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (!el.classList.contains('animated') && r.top < window.innerHeight * 0.9 && r.bottom > 0) {
          el.classList.add('animated', animName(el)); io.unobserve(el);
        }
      });
    });
  }

  /* ---------- Counter (wie jquery-numerator: data-duration, swing) ---------- */
  function swing(p) { return 0.5 - Math.cos(p * Math.PI) / 2; }
  function initCounters() {
    var nums = document.querySelectorAll('.counter-num');
    if (!nums.length) return;
    function fmt(v, decimals) { return v.toFixed(decimals).replace('.', ','); }
    function run(el) {
      var target = parseFloat(el.getAttribute('data-count')) || 0;
      var decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
      var duration = parseInt(el.getAttribute('data-duration') || '2000', 10);
      if (prefersReduced) { el.textContent = fmt(target, decimals); return; }
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min((ts - start) / duration, 1);
        el.textContent = fmt(target * swing(p), decimals);
        if (p < 1) requestAnimationFrame(step); else el.textContent = fmt(target, decimals);
      }
      requestAnimationFrame(step);
    }
    if (!('IntersectionObserver' in window)) { nums.forEach(run); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { run(e.target); io.unobserve(e.target); } });
    }, { threshold: 0, rootMargin: '0px 0px -10% 0px' });
    nums.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Burger-Menü ---------- */
  function initMenu() {
    var toggle = document.querySelector('.menu-toggle');
    var dropdown = document.getElementById('nav-dropdown');
    if (!toggle || !dropdown) return;
    function close() { toggle.setAttribute('aria-expanded', 'false'); dropdown.classList.remove('is-open'); }
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
      dropdown.classList.toggle('is-open', !open);
    });
    dropdown.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', close); });
    document.addEventListener('click', function (e) {
      if (!dropdown.classList.contains('is-open')) return;
      if (!e.target.closest('.pk-header')) close();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    window.addEventListener('resize', function () { if (!isMobile()) close(); });
  }

  /* ---------- Anker-Scroll (Elementor: 500 ms, swing) ---------- */
  function scrollToY(targetY) {
    if (prefersReduced) { window.scrollTo(0, targetY); return; }
    var startY = window.pageYOffset, dist = targetY - startY, start = null, duration = 500;
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      window.scrollTo(0, startY + dist * swing(p));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = a.getAttribute('href');
        if (id.length < 2) return;
        var target = document.querySelector(id);
        if (!target) return;
        e.preventDefault();
        var top = target.getBoundingClientRect().top + window.pageYOffset;
        scrollToY(top);
        if (history.pushState) history.pushState(null, '', id);
      });
    });
  }

  /* ---------- Aktiven Menüpunkt markieren ---------- */
  function initActiveNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll('.nav-menu a[href^="#"], .nav-dropdown a[href^="#"]'));
    var sections = [];
    links.forEach(function (l) {
      var s = document.querySelector(l.getAttribute('href'));
      if (s && sections.indexOf(s) === -1) sections.push(s);
    });
    if (!sections.length) return;
    var ticking = false;
    function update() {
      ticking = false;
      var line = window.pageYOffset + window.innerHeight * 0.35;
      var current = null;
      sections.forEach(function (s) { if (s.offsetTop <= line) current = s; });
      var atBottom = window.innerHeight + window.pageYOffset >= document.body.scrollHeight - 2;
      if (atBottom) current = sections[sections.length - 1];
      links.forEach(function (l) { l.classList.toggle('is-active', !!current && l.getAttribute('href') === '#' + current.id); });
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    window.addEventListener('resize', update);
    update();
  }

  /* ---------- Karussell ---------- */
  function initCarousel(root) {
    var track = root.querySelector('.carousel__track');
    var slides = Array.prototype.slice.call(root.querySelectorAll('.carousel__slide'));
    var prev = root.querySelector('.carousel__arrow--prev');
    var next = root.querySelector('.carousel__arrow--next');
    var dots = root.querySelector('.carousel__dots');
    if (!track || slides.length < 2) return;

    var index = 0, timer = null, perView = 3, autoplay = 5000, interacted = false;

    function getPerView() { return window.innerWidth <= MOBILE ? 1 : 3; }
    function buildDots() {
      if (!dots) return;
      while (dots.firstChild) dots.removeChild(dots.firstChild);
      slides.forEach(function (_, i) {
        var b = document.createElement('button');
        b.type = 'button';
        b.setAttribute('aria-label', 'Slide ' + (i + 1));
        b.addEventListener('click', userAction(function () { go(i); }));
        dots.appendChild(b);
      });
    }
    function update() {
      perView = getPerView();
      var slideW = 100 / perView;
      // Aktiver Slide mittig (bei 3 pro Ansicht), sonst am Anfang
      var offsetSlides = perView === 3 ? 1 : 0;
      var shift = (index - offsetSlides) * slideW;
      track.style.transform = 'translateX(' + (-shift) + '%)';
      slides.forEach(function (s, i) {
        s.classList.toggle('is-active', i === index);
        s.setAttribute('aria-hidden', (i < index - offsetSlides || i >= index - offsetSlides + perView) ? 'true' : 'false');
      });
      if (dots) Array.prototype.forEach.call(dots.children, function (d, i) { d.classList.toggle('is-active', i === index); });
      // Bei 3 Slides pro Ansicht: Slides links/rechts auffüllen (Loop-Optik via Clones vermeiden -> wir begrenzen den Bereich)
    }
    function go(i) {
      var n = slides.length;
      index = ((i % n) + n) % n;
      update();
    }
    function restart() {
      if (timer) clearInterval(timer);
      if (prefersReduced || interacted) return;   // pause_on_interaction
      timer = setInterval(function () { go(index + 1); }, autoplay);
    }
    function userAction(fn) { return function () { interacted = true; if (timer) clearInterval(timer); fn(); }; }

    /* Für den "mittig aktiv"-Look mit 3 Slides pro Ansicht klonen wir die Slides vorne/hinten */
    if (slides.length >= 3) {
      var firstClone = slides[slides.length - 1].cloneNode(true);
      var lastClone = slides[0].cloneNode(true);
      firstClone.classList.add('is-clone'); lastClone.classList.add('is-clone');
      firstClone.setAttribute('aria-hidden', 'true'); lastClone.setAttribute('aria-hidden', 'true');
      track.insertBefore(firstClone, slides[0]);
      track.appendChild(lastClone);
      var all = Array.prototype.slice.call(track.children);
      // Index-Mapping: echter Slide i befindet sich an Position i+1
      update = function () {
        perView = getPerView();
        var slideW = 100 / perView;
        var pos = index + 1; // Position im Track
        var offsetSlides = perView === 3 ? 1 : 0;
        var shift = (pos - offsetSlides) * slideW;
        track.style.transition = 'transform .5s ease';
        track.style.transform = 'translateX(' + (-shift) + '%)';
        all.forEach(function (s, p) { s.classList.toggle('is-active', p === pos); });
        if (dots) Array.prototype.forEach.call(dots.children, function (d, i) { d.classList.toggle('is-active', i === index); });
      };
      go = function (i) {
        var n = slides.length;
        var target = i;
        // Nahtloser Übergang über die Klone
        if (target < 0 || target >= n) {
          var pos = target + 1;
          perView = getPerView();
          var slideW = 100 / perView;
          var offsetSlides = perView === 3 ? 1 : 0;
          track.style.transition = 'transform .5s ease';
          track.style.transform = 'translateX(' + (-(pos - offsetSlides) * slideW) + '%)';
          all.forEach(function (s, p) { s.classList.toggle('is-active', p === pos); });
          index = ((target % n) + n) % n;
          if (dots) Array.prototype.forEach.call(dots.children, function (d, k) { d.classList.toggle('is-active', k === index); });
          setTimeout(function () {
            track.style.transition = 'none';
            update();
            // Reflow erzwingen, damit der Sprung ohne Animation passiert
            void track.offsetWidth;
            track.style.transition = 'transform .5s ease';
          }, 520);
          return;
        }
        index = target;
        update();
      };
    }

    if (prev) prev.addEventListener('click', userAction(function () { go(index - 1); }));
    if (next) next.addEventListener('click', userAction(function () { go(index + 1); }));

    // Swipe
    var startX = null;
    root.addEventListener('touchstart', function (e) { startX = e.touches[0].clientX; }, { passive: true });
    root.addEventListener('touchend', function (e) {
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 40) { interacted = true; if (timer) clearInterval(timer); go(dx < 0 ? index + 1 : index - 1); }
      startX = null;
    });
    root.addEventListener('mouseenter', function () { if (timer) clearInterval(timer); });
    root.addEventListener('mouseleave', restart);
    window.addEventListener('resize', function () { track.style.transition = 'none'; update(); void track.offsetWidth; track.style.transition = 'transform .5s ease'; });

    buildDots();
    update();
    restart();
  }

  /* ---------- FAQ ---------- */
  function initFaq() {
    document.querySelectorAll('.faq__item').forEach(function (item) {
      var btn = item.querySelector('.faq__header');
      if (!btn) return;
      btn.addEventListener('click', function () {
        var open = item.classList.contains('is-open');
        // Nur ein Element gleichzeitig offen (wie EAEL Accordion)
        item.parentElement.querySelectorAll('.faq__item.is-open').forEach(function (o) {
          o.classList.remove('is-open');
          o.querySelector('.faq__header').setAttribute('aria-expanded', 'false');
        });
        if (!open) { item.classList.add('is-open'); btn.setAttribute('aria-expanded', 'true'); }
      });
    });
  }

  /* ---------- Stellen: Filter + Akkordeon ---------- */
  function initJobs() {
    var jobs = document.querySelectorAll('.job');
    function setJob(job, open) {
      job.classList.toggle('is-open', open);
      var btn = job.querySelector('.job__btn');
      if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    jobs.forEach(function (job) {
      var head = job.querySelector('.job__head');
      if (!head) return;
      head.addEventListener('click', function (e) {
        if (e.target.closest('a')) return;
        setJob(job, !job.classList.contains('is-open'));
      });
    });
    var filterBtns = document.querySelectorAll('.filter [data-filter]');
    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        filterBtns.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
        var f = btn.getAttribute('data-filter');
        jobs.forEach(function (job) {
          var show = f === 'all' || job.getAttribute('data-category') === f;
          job.classList.toggle('is-hidden', !show);
          if (show && !job.classList.contains('animated')) job.classList.add('animated', 'fadeInUp');
        });
      });
    });
    // Deep-Link: /karriere/#job-… öffnet die Stelle direkt (auch bei Hash-Wechsel)
    function openFromHash() {
      if (!location.hash || location.hash.indexOf('#job-') !== 0) return;
      var target = document.getElementById(location.hash.slice(1));
      if (target && target.classList.contains('job')) {
        target.classList.add('animated', 'fadeInUp');
        setJob(target, true);
      }
    }
    openFromHash();
    window.addEventListener('hashchange', openFromHash);
  }

  /* ---------- Init ---------- */
  function init() {
    var y = document.getElementById('year');
    if (y) y.textContent = String(new Date().getFullYear());
    initMenu();
    initSmoothScroll();
    initActiveNav();
    initAnimations();
    initCounters();
    document.querySelectorAll('.carousel').forEach(initCarousel);
    initFaq();
    initJobs();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
