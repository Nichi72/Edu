/* 챕터 공통 동작 — 체크리스트 / 퀴즈 / 우측 레일 현재 위치 */
(function(){
  "use strict";

  document.querySelectorAll('[data-check]').forEach(function(el){
    el.setAttribute('role','checkbox');
    el.setAttribute('tabindex','0');
    el.setAttribute('aria-checked','false');
    function toggle(){
      var on = el.classList.toggle('is-done');
      el.setAttribute('aria-checked', on ? 'true' : 'false');
      el.querySelector('.check__box').textContent = on ? '✓' : '';
    }
    el.addEventListener('click', toggle);
    el.addEventListener('keydown', function(e){
      if(e.key === ' ' || e.key === 'Enter'){ e.preventDefault(); toggle(); }
    });
  });

  document.querySelectorAll('[data-quiz]').forEach(function(g){
    g.addEventListener('click', function(e){
      var c = e.target.closest('.choice');
      if(!c || g.dataset.locked) return;
      g.dataset.locked = '1';
      g.querySelectorAll('.choice').forEach(function(o){
        var ok = o.dataset.ok === '1';
        if(ok) o.classList.add('choice--right');
        else if(o === c) o.classList.add('choice--wrong');
        if(o === c || ok){
          var s = document.createElement('span');
          s.style.cssText = 'margin-left:auto;font-size:12.5px;font-weight:700';
          s.textContent = ok ? '정답' : '오답';
          o.appendChild(s);
        }
      });
      var ex = document.querySelector('[data-explain="' + c.dataset.q + '"]');
      if(ex) ex.hidden = false;
    });
  });

  /* 모바일 목차 접기 — 항목이 많으면 안 접을 때 첫 화면이 목차로 다 찬다.
     한 파일로 묶은 교재에는 페이지마다 목차가 있어서 전부 건다 */
  document.querySelectorAll('.navblock').forEach(function (nb) {
    var tg = nb.querySelector('.navtoggle');
    if (!tg) return;
    tg.addEventListener('click', function () {
      var on = nb.classList.toggle('is-open');
      tg.setAttribute('aria-expanded', on ? 'true' : 'false');
    });
    // 항목을 고르면 바로 닫는다. 안 닫으면 이동해도 목차가 화면을 덮는다.
    nb.addEventListener('click', function (e) {
      if (e.target.closest('.toc__sub, .toc__item')) {
        nb.classList.remove('is-open');
        tg.setAttribute('aria-expanded', 'false');
      }
    });
  });

  var rail = [].slice.call(document.querySelectorAll('.railitem'));
  var secs = rail.map(function(a){ return document.querySelector(a.getAttribute('href')); });
  if('IntersectionObserver' in window && rail.length){
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if(!e.isIntersecting) return;
        var i = secs.indexOf(e.target);
        if(i < 0) return;
        rail.forEach(function(a, j){ a.classList.toggle('is-here', i === j); });
      });
    }, {rootMargin:'-64px 0px -70% 0px'});
    secs.forEach(function(s){ if(s) io.observe(s); });
  }
})();
