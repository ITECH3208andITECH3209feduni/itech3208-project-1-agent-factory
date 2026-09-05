// site/js/site.js — Interactive features for Agent Factory Showcase Website
// PROJ-403, PROJ-448, PROJ-449, PROJ-451

document.addEventListener('DOMContentLoaded', () => {
  initThemeToggle();
  initMobileNav();
  initFaqSearch();
  initCounterAnimations();
});

/* ── Theme Toggle ── */
function initThemeToggle() {
  const toggleBtn = document.getElementById('theme-toggle-btn');
  const savedTheme = localStorage.getItem('site_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('site_theme', next);
      updateThemeIcon(next);
    });
  }
}

function updateThemeIcon(theme) {
  const icon = document.getElementById('theme-icon');
  if (icon) {
    icon.textContent = theme === 'dark' ? '☀️' : '🌙';
  }
}

/* ── Mobile Navigation ── */
function initMobileNav() {
  const toggle = document.getElementById('mobile-nav-toggle');
  const links = document.getElementById('nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', () => {
      links.classList.toggle('open');
      toggle.textContent = links.classList.contains('open') ? '✕' : '☰';
    });
  }
}

/* ── FAQ Search & Filter (PROJ-451) ── */
function initFaqSearch() {
  const searchInput = document.getElementById('faq-search-input');
  const items = document.querySelectorAll('.faq-item');
  const categoryChips = document.querySelectorAll('.category-chip');

  let activeCategory = 'all';

  function filterItems() {
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();

    items.forEach(item => {
      const category = item.getAttribute('data-category') || 'general';
      const question = item.querySelector('.faq-question')?.textContent.toLowerCase() || '';
      const answer = item.querySelector('.faq-answer')?.textContent.toLowerCase() || '';

      const matchesCat = activeCategory === 'all' || category === activeCategory;
      const matchesSearch = !query || question.includes(query) || answer.includes(query);

      if (matchesCat && matchesSearch) {
        item.style.display = 'block';
      } else {
        item.style.display = 'none';
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', filterItems);
  }

  categoryChips.forEach(chip => {
    chip.addEventListener('click', () => {
      categoryChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeCategory = chip.getAttribute('data-category') || 'all';
      filterItems();
    });
  });

  // Accordion Expand/Collapse
  items.forEach(item => {
    const questionBtn = item.querySelector('.faq-question');
    if (questionBtn) {
      questionBtn.addEventListener('click', () => {
        const isOpen = item.classList.contains('open');
        // Close others in accordion
        items.forEach(other => other.classList.remove('open'));
        if (!isOpen) {
          item.classList.add('open');
        }
      });
    }
  });
}

/* ── Counter Animations ── */
function initCounterAnimations() {
  const counters = document.querySelectorAll('.stat-number');
  if (!counters.length) return;

  const observer = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const targetVal = parseFloat(el.getAttribute('data-target') || '0');
        const suffix = el.getAttribute('data-suffix') || '';
        animateValue(el, 0, targetVal, 1200, suffix);
        obs.unobserve(el);
      }
    });
  }, { threshold: 0.5 });

  counters.forEach(c => observer.observe(c));
}

function animateValue(obj, start, end, duration, suffix = '') {
  let startTimestamp = null;
  const isFloat = end % 1 !== 0;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    const easeOut = 1 - Math.pow(1 - progress, 3);
    const current = start + easeOut * (end - start);
    obj.innerHTML = (isFloat ? current.toFixed(1) : Math.floor(current)) + suffix;
    if (progress < 1) {
      window.requestAnimationFrame(step);
    } else {
      obj.innerHTML = (isFloat ? end.toFixed(1) : end) + suffix;
    }
  };
  window.requestAnimationFrame(step);
}
