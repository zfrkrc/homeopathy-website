/* Homeopati Blog - Main Scripts */

function toggleNav() {
  const navLinks = document.getElementById('navLinks');
  if (navLinks) navLinks.classList.toggle('open');
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
