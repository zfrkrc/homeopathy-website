/* Homeopati Blog - Main Scripts */

function toggleNav() {
  const navLinks = document.getElementById('navLinks');
  const toggle = document.querySelector('.nav-toggle');
  if (navLinks) {
    const willOpen = !navLinks.classList.contains('open');
    navLinks.classList.toggle('open');
    if (toggle) toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }
}

function handleNewsletter(event) {
  event.preventDefault();
  const input = event.target.querySelector('input[type="email"]');
  if (input && input.value) {
    const btn = event.target.querySelector('button');
    const original = btn.textContent;
    btn.textContent = 'Abone Olundu!';
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
      input.value = '';
    }, 2000);
  }
}

// Close mobile menu on outside click
document.addEventListener('click', (e) => {
  const nav = document.querySelector('.nav');
  const navLinks = document.getElementById('navLinks');
  if (nav && navLinks && !nav.contains(e.target)) {
    navLinks.classList.remove('open');
  }
});

// Dark mode toggle
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const btn = document.querySelector('.theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

updateThemeIcon(document.documentElement.getAttribute('data-theme'));

// Scroll reveal animations
(function () {
  const items = document.querySelectorAll('.reveal');
  if (!items.length) return;
  if (!('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  items.forEach((el) => observer.observe(el));
})();
