/**
 * ASSOCIATIONHUB — CORE INTERACTIVE JAVASCRIPT
 * NK Orchid College of Engineering & Technology
 * Frontend Interactive System (2026)
 */


/* --------------------------------------------------------------------------
   GLOBAL UNIVERSAL API CLIENT & PROTOCOL ROUTER (NKOCET 2026)
   -------------------------------------------------------------------------- */
window.createVerificationSessionId = function() {
  const bytes = new Uint8Array(24);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
};

// Background Offline Sync Engine for Passes Created Offline
window.processOfflineMembershipQueue = async function() {
  try {
    const qStr = localStorage.getItem('orchid_offline_pass_queue');
    if (!qStr) return;
    const queue = JSON.parse(qStr);
    if (!Array.isArray(queue) || queue.length === 0) return;

    const remaining = [];
    for (const item of queue) {
      try {
        const res = await apiFetch('/api/memberships', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...item
          })
        });
        if (!res.ok) {
          remaining.push(item);
        }
      } catch (e) {
        remaining.push(item);
      }
    }
    if (remaining.length === 0) {
      localStorage.removeItem('orchid_offline_pass_queue');
    } else {
      localStorage.setItem('orchid_offline_pass_queue', JSON.stringify(remaining));
    }
  } catch (e) {}
};
setInterval(window.processOfflineMembershipQueue, 10000);


document.addEventListener('DOMContentLoaded', () => {
  initHeader();
  initMobileMenu();
  initNavDropdown();
  initAssociationFilters();
  initEventFilters();
  initGalleryLightbox();
  initBackToTop();
  initInteractiveModals();
  initAssociationQuiz();
  initMembershipModal();
  initCampusPulse();
  initAnnouncementBanner();
  initZeroGMode();
  initCalendarEvents();
  init3DTilt();
  initFaqAccordion();
  initLiveTelemetry();
  initAdminConsole();
  initSpotlightSearch();

  // Check URL params for direct action triggers
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('open') === 'admin' && typeof openAdminModal === 'function') {
    setTimeout(() => openAdminModal(), 250);
  }
  if (urlParams.get('open') === 'join' && typeof openMembershipModal === 'function') {
    setTimeout(() => openMembershipModal(urlParams.get('dept')), 250);
  }
});

/* --------------------------------------------------------------------------
   0. TOAST NOTIFICATION, AUDIO SYNTHESIS & WHATSAPP SHARE UTILITIES
   -------------------------------------------------------------------------- */
let _audioCtx = null;
window.playAudioTone = function(freq, duration = 0.08, type = 'sine') {
  try {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (_audioCtx.state === 'suspended') _audioCtx.resume();
    const osc = _audioCtx.createOscillator();
    const gain = _audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, _audioCtx.currentTime);
    gain.gain.setValueAtTime(0.04, _audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, _audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(_audioCtx.destination);
    osc.start();
    osc.stop(_audioCtx.currentTime + duration);
  } catch(e) {}
};

window.showToast = function(message, type = 'gold') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  let icon = '⚡';
  if (type === 'success') {
    icon = '✓';
    playAudioTone(880, 0.1, 'sine');
  } else if (type === 'error') {
    icon = '⚠️';
    playAudioTone(280, 0.15, 'triangle');
  } else {
    playAudioTone(660, 0.08, 'sine');
  }
  toast.innerHTML = `<span>${icon}</span> <div>${message}</div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(50px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
};

window.sharePassWhatsApp = function(name, assoc, verifyUrl, passId) {
  const msg = `Hey! I just registered as an official member of ${assoc} at NK Orchid College of Engineering & Technology (NKOCET, Solapur)! 🚀\n\nCheck out my verified digital pass here: ${verifyUrl}\nPass ID: ${passId}`;
  window.open(`https://api.whatsapp.com/send?text=${encodeURIComponent(msg)}`, '_blank');
};

/* --------------------------------------------------------------------------
   1. HEADER SCROLL STATE
   -------------------------------------------------------------------------- */
function initHeader() {
  const header = document.querySelector('.site-header');
  if (!header) return;

  const onScroll = () => {
    if (window.scrollY > 30) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* --------------------------------------------------------------------------
   2. MOBILE NAVIGATION DRAWER
   -------------------------------------------------------------------------- */
function initMobileMenu() {
  const toggleBtn = document.querySelector('.mobile-toggle');
  const drawer = document.querySelector('.mobile-drawer');
  const overlay = document.querySelector('.mobile-overlay');
  const mobileLinks = document.querySelectorAll('.mobile-nav-link');

  if (!toggleBtn || !drawer || !overlay) return;

  function openMenu() {
    toggleBtn.classList.add('active');
    toggleBtn.setAttribute('aria-expanded', 'true');
    drawer.classList.add('open');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeMenu() {
    toggleBtn.classList.remove('active');
    toggleBtn.setAttribute('aria-expanded', 'false');
    drawer.classList.remove('open');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  toggleBtn.addEventListener('click', () => {
    if (drawer.classList.contains('open')) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  overlay.addEventListener('click', closeMenu);

  mobileLinks.forEach(link => {
    link.addEventListener('click', closeMenu);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      closeMenu();
    }
  });
}

/* --------------------------------------------------------------------------
   3. ASSOCIATION SEARCH & FILTER SYSTEM
   -------------------------------------------------------------------------- */
function initAssociationFilters() {
  const searchInput = document.getElementById('association-search');
  const filterPills = document.querySelectorAll('.filter-pill');
  const cards = document.querySelectorAll('.association-card');
  const resultsCount = document.getElementById('results-count');
  const clearBtn = document.getElementById('clear-filters-btn');
  const emptyState = document.getElementById('association-empty-state');

  if (!cards.length) return;

  let activeCategory = 'all';
  let searchTerm = '';

  function filterCards() {
    let visibleCount = 0;

    cards.forEach(card => {
      const category = card.getAttribute('data-dept-category') || '';
      const text = card.textContent.toLowerCase();

      const matchesCategory = (activeCategory === 'all' || category === activeCategory);
      const matchesSearch = !searchTerm || text.includes(searchTerm);

      if (matchesCategory && matchesSearch) {
        card.style.display = 'flex';
        visibleCount++;
      } else {
        card.style.display = 'none';
      }
    });

    if (resultsCount) {
      resultsCount.textContent = `Showing ${visibleCount} of ${cards.length} associations`;
    }

    if (emptyState) {
      emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchTerm = e.target.value.trim().toLowerCase();
      filterCards();
    });
  }

  filterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      filterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeCategory = pill.getAttribute('data-filter') || 'all';
      filterCards();
    });
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      searchTerm = '';
      activeCategory = 'all';
      filterPills.forEach(p => p.classList.remove('active'));
      const allPill = document.querySelector('.filter-pill[data-filter="all"]');
      if (allPill) allPill.classList.add('active');
      filterCards();
    });
  }
}

/* --------------------------------------------------------------------------
   4. EVENT FILTER SYSTEM (ALL / UPCOMING / PAST)
   -------------------------------------------------------------------------- */
function initEventFilters() {
  const tabs = document.querySelectorAll('.events-tab');
  const eventCards = document.querySelectorAll('.event-card');

  if (!tabs.length || !eventCards.length) return;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.getAttribute('data-event-filter') || 'all';

      eventCards.forEach(card => {
        const type = card.getAttribute('data-event-type') || 'all';
        if (target === 'all' || type === target) {
          card.style.display = 'flex';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });
}

/* --------------------------------------------------------------------------
   5. GALLERY & TEAM PHOTO LIGHTBOX (3D / 4D INTERACTIVE ENGINE)
   -------------------------------------------------------------------------- */
function initGalleryLightbox() {
  const galleryItems = document.querySelectorAll('.gallery-item, .team-avatar');
  const teamCards = document.querySelectorAll('.team-card');
  const lightbox = document.getElementById('lightbox-modal');
  if (!galleryItems.length || !lightbox) return;

  const lightboxImg = lightbox.querySelector('.lightbox-img');
  const lightboxCaption = lightbox.querySelector('.lightbox-caption-text');
  const closeBtn = lightbox.querySelector('.lightbox-close');
  const prevBtn = lightbox.querySelector('.lightbox-prev');
  const nextBtn = lightbox.querySelector('.lightbox-next');
  const card3D = document.getElementById('lightbox-3d-card');
  const glare3D = document.getElementById('lightbox-glare');
  const orbitToggle = document.getElementById('lightbox-orbit-toggle');
  const zoomToggle = document.getElementById('lightbox-zoom-toggle');

  let currentIndex = 0;
  const items = Array.from(galleryItems);

  // 3D Engine State
  let autoOrbit = true;
  let orbitAngle = 0;
  let orbitAnimId = null;
  let isFullZoom = false;

  function runAutoOrbit() {
    if (!autoOrbit || !lightbox.classList.contains('active') || !card3D) return;
    orbitAngle += 0.025;
    const tiltX = Math.sin(orbitAngle) * 8.5;
    const tiltY = Math.cos(orbitAngle * 0.8) * 12;

    card3D.style.transition = 'transform 0.08s linear, box-shadow 0.08s linear';
    card3D.style.transform = `perspective(1200px) rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg) translateZ(35px) scale3d(1.02, 1.02, 1.02)`;
    card3D.style.boxShadow = `${(-tiltY * 2.2).toFixed(1)}px ${(tiltX * 2.2 + 20).toFixed(1)}px 55px rgba(0,0,0,0.88), 0 0 35px rgba(218, 165, 32, 0.28)`;

    if (glare3D) {
      const glareX = (50 + Math.cos(orbitAngle) * 38).toFixed(1);
      const glareY = (50 + Math.sin(orbitAngle * 0.7) * 38).toFixed(1);
      glare3D.style.opacity = '0.9';
      glare3D.style.background = `radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255,255,255,0.7) 0%, rgba(218,165,32,0.35) 24%, rgba(0,217,232,0.22) 46%, transparent 70%), linear-gradient(${(tiltY * 5).toFixed(1)}deg, rgba(255,0,128,0.1) 0%, rgba(0,255,255,0.15) 50%, rgba(255,215,0,0.1) 100%)`;
    }

    orbitAnimId = requestAnimationFrame(runAutoOrbit);
  }

  function startAutoOrbit() {
    if (orbitAnimId) cancelAnimationFrame(orbitAnimId);
    autoOrbit = true;
    if (orbitToggle) {
      orbitToggle.classList.add('active');
      const textSpan = orbitToggle.querySelector('.tool-text');
      if (textSpan) textSpan.textContent = 'Auto 3D Float: ON';
    }
    runAutoOrbit();
  }

  function pauseAutoOrbit() {
    autoOrbit = false;
    if (orbitAnimId) cancelAnimationFrame(orbitAnimId);
    if (orbitToggle) {
      orbitToggle.classList.remove('active');
      const textSpan = orbitToggle.querySelector('.tool-text');
      if (textSpan) textSpan.textContent = 'Auto 3D Float: OFF';
    }
  }

  function reset3DCard() {
    if (orbitAnimId) cancelAnimationFrame(orbitAnimId);
    if (card3D) {
      card3D.style.transition = 'transform 0.4s ease-out, box-shadow 0.4s ease-out';
      card3D.style.transform = 'perspective(1200px) rotateX(0deg) rotateY(0deg) translateZ(0px) scale3d(1, 1, 1)';
      card3D.style.boxShadow = '0 25px 60px rgba(0,0,0,0.85), 0 0 25px rgba(218,165,32,0.15)';
    }
    if (glare3D) glare3D.style.opacity = '0';
  }

  function showImage(index) {
    if (index < 0) index = items.length - 1;
    if (index >= items.length) index = 0;
    currentIndex = index;

    const item = items[currentIndex];
    const fullPhoto = item.getAttribute('data-full-photo');
    const img = item.querySelector('img');
    const photoSrc = fullPhoto || (img ? img.src : '');
    if (!photoSrc) return;

    const caption = item.getAttribute('data-caption') || (img ? img.alt : '');

    reset3DCard();
    lightboxImg.src = photoSrc;
    lightboxImg.alt = img ? img.alt : 'Full Team Photo';
    if (lightboxCaption) lightboxCaption.innerHTML = caption;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Start auto 3D float
    setTimeout(() => {
      startAutoOrbit();
    }, 150);
  }

  function closeLightbox() {
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
    pauseAutoOrbit();
    reset3DCard();
    if (lightboxImg && isFullZoom) {
      lightboxImg.classList.remove('full-scale');
      isFullZoom = false;
    }
  }

  // Click on items to open
  galleryItems.forEach((item, index) => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      showImage(index);
    });
  });

  // Also allow clicking anywhere on .team-card to open that member's photo
  teamCards.forEach((card) => {
    const avatar = card.querySelector('.team-avatar');
    if (avatar) {
      card.addEventListener('click', () => {
        const idx = items.indexOf(avatar);
        if (idx !== -1) showImage(idx);
      });
    }
  });

  if (closeBtn) closeBtn.addEventListener('click', closeLightbox);
  if (prevBtn) prevBtn.addEventListener('click', () => showImage(currentIndex - 1));
  if (nextBtn) nextBtn.addEventListener('click', () => showImage(currentIndex + 1));

  // Toggle orbit button
  if (orbitToggle) {
    orbitToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      if (autoOrbit) {
        pauseAutoOrbit();
        reset3DCard();
      } else {
        startAutoOrbit();
      }
    });
  }

  // Toggle zoom button
  if (zoomToggle) {
    zoomToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      isFullZoom = !isFullZoom;
      if (lightboxImg) {
        lightboxImg.classList.toggle('full-scale', isFullZoom);
      }
      const textSpan = zoomToggle.querySelector('.tool-text');
      if (textSpan) textSpan.textContent = isFullZoom ? 'Fit View' : 'Full Scale';
    });
  }

  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox || e.target.classList.contains('lightbox-content') || e.target.classList.contains('lightbox-3d-stage')) {
      closeLightbox();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (!lightbox.classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') showImage(currentIndex - 1);
    if (e.key === 'ArrowRight') showImage(currentIndex + 1);
  });

  // 3D & 4D Interactive Depth Mouse Tracker
  if (card3D) {
    let mouseResumeTimer = null;

    lightbox.addEventListener('mousemove', (e) => {
      if (!lightbox.classList.contains('active') || !card3D) return;

      // Pause auto orbit while mouse is actively moving
      if (autoOrbit) {
        if (orbitAnimId) cancelAnimationFrame(orbitAnimId);
      }

      const rect = card3D.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      // Normalized coordinates relative to viewport & card
      const deltaX = (e.clientX - centerX) / (window.innerWidth / 2);
      const deltaY = (e.clientY - centerY) / (window.innerHeight / 2);

      const rotateY = Math.max(-26, Math.min(26, deltaX * 24));
      const rotateX = Math.max(-26, Math.min(26, -deltaY * 24));

      card3D.style.transition = 'none'; // Zero lag 1:1 real-time cursor tracking
      card3D.style.transform = `perspective(1200px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(40px) scale3d(1.04, 1.04, 1.04)`;
      card3D.style.boxShadow = `${(-rotateY * 2.5).toFixed(1)}px ${(rotateX * 2.5 + 20).toFixed(1)}px 60px rgba(0,0,0,0.92), 0 0 40px rgba(218, 165, 32, 0.35), 0 0 15px rgba(255,255,255,0.15)`;

      if (glare3D) {
        const cardX = e.clientX - rect.left;
        const cardY = e.clientY - rect.top;
        const glareX = Math.max(0, Math.min(100, (cardX / rect.width) * 100)).toFixed(1);
        const glareY = Math.max(0, Math.min(100, (cardY / rect.height) * 100)).toFixed(1);

        glare3D.style.opacity = '0.95';
        glare3D.style.background = `radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255,255,255,0.75) 0%, rgba(218,165,32,0.35) 25%, rgba(0,217,232,0.25) 45%, transparent 70%), linear-gradient(${(rotateY * 5).toFixed(1)}deg, rgba(255,0,128,0.12) 0%, rgba(0,255,255,0.18) 50%, rgba(255,215,0,0.12) 100%)`;
      }

      // Resume smooth auto float after 2.5 seconds of stillness
      clearTimeout(mouseResumeTimer);
      mouseResumeTimer = setTimeout(() => {
        if (autoOrbit && lightbox.classList.contains('active')) {
          card3D.style.transition = 'transform 0.6s ease-out, box-shadow 0.6s ease-out';
          runAutoOrbit();
        }
      }, 2500);
    });

    // Mobile gyroscope orientation tilt
    if (window.DeviceOrientationEvent) {
      window.addEventListener('deviceorientation', (e) => {
        if (!lightbox.classList.contains('active') || !e.gamma || !e.beta) return;
        const tiltX = Math.max(-20, Math.min(20, e.gamma));
        const tiltY = Math.max(-20, Math.min(20, e.beta - 45));
        card3D.style.transition = 'transform 0.1s ease-out';
        card3D.style.transform = `perspective(1200px) rotateX(${-tiltY.toFixed(1)}deg) rotateY(${tiltX.toFixed(1)}deg) translateZ(35px) scale3d(1.03, 1.03, 1.03)`;
      });
    }
  }
}

/* --------------------------------------------------------------------------
   6. BACK TO TOP BUTTON
   -------------------------------------------------------------------------- */
function initBackToTop() {
  const backTopBtn = document.getElementById('back-to-top');
  if (!backTopBtn) return;

  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      backTopBtn.classList.add('visible');
    } else {
      backTopBtn.classList.remove('visible');
    }
  }, { passive: true });

  backTopBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

/* --------------------------------------------------------------------------
   7. INTERACTIVE MODAL NOTIFICATIONS (CLEAR FRONTEND FEEDBACK)
   -------------------------------------------------------------------------- */
function initInteractiveModals() {
  const modalOverlay = document.getElementById('interactive-modal-overlay');
  const modalTitle = document.getElementById('modal-title');
  const modalDesc = document.getElementById('modal-desc');
  const modalClose = document.getElementById('modal-close-btn');

  if (!modalOverlay || !modalTitle || !modalDesc) return;

  window.showInteractiveModal = function(title, description) {
    modalTitle.textContent = title;
    modalDesc.textContent = description;
    modalOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  };

  function closeModal() {
    modalOverlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  if (modalClose) modalClose.addEventListener('click', closeModal);
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOverlay.classList.contains('active')) {
      closeModal();
    }
  });
}


/* --------------------------------------------------------------------------
   8. QUICK ASSOCIATION NAVBAR DROPDOWN
   -------------------------------------------------------------------------- */
function initNavDropdown() {
  const dropdowns = document.querySelectorAll('.nav-dropdown');
  if (!dropdowns.length) return;

  dropdowns.forEach(dropdown => {
    const trigger = dropdown.querySelector('.nav-dropdown-trigger');
    const menu = dropdown.querySelector('.nav-dropdown-menu');

    if (!trigger || !menu) return;

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isActive = dropdown.classList.contains('active');
      dropdowns.forEach(d => d.classList.remove('active'));
      if (!isActive) dropdown.classList.add('active');
    });
  });

  document.addEventListener('click', () => {
    dropdowns.forEach(d => d.classList.remove('active'));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      dropdowns.forEach(d => d.classList.remove('active'));
    }
  });
}

/* --------------------------------------------------------------------------
   9. FRESHERS' ASSOCIATION FINDER QUIZ
   -------------------------------------------------------------------------- */
function initAssociationQuiz() {
  const quizContainer = document.getElementById('association-quiz-container');
  if (!quizContainer) return;

  const questions = [
    {
      title: "Step 1: What engineering domain fires up your curiosity most?",
      desc: "Select the primary field of technology you enjoy exploring or building.",
      options: [
        { icon: "💻", title: "Software & Web Platforms", desc: "Algorithms, cybersecurity, cloud, and full-stack development", dept: "csesa" },
        { icon: "⚙️", title: "Machines & Automotive Systems", desc: "CAD/CAM, vehicle dynamics, robotics & thermal engineering", dept: "mesa" },
        { icon: "⚡", title: "Clean Energy & Smart Grids", desc: "Electric vehicles, solar power systems & industrial drives", dept: "eesa" },
        { icon: "🏗️", title: "Mega-Structures & Smart Cities", desc: "Structural load design, architecture & modern infrastructure", dept: "cesa" },
        { icon: "📡", title: "Wireless Tech & Microcontrollers", desc: "Embedded IoT sensors, microchips & RF telecommunications", dept: "aexs" },
        { icon: "🧠", title: "AI, Data Science & Neural Nets", desc: "Machine intelligence, computer vision & deep learning analytics", dept: "aiesa" }
      ]
    },
    {
      title: "Step 2: What kind of hands-on project do you want to build?",
      desc: "Pick the practical challenge you would like to participate in during your college journey.",
      options: [
        { icon: "🚀", title: "Production Web App or Codefest", desc: "Building scalable web tools, competitive hackathon software", dept: "csesa" },
        { icon: "🏎️", title: "Formula BAJA All-Terrain Vehicle", desc: "Designing and racing a student vehicle in national arenas", dept: "mesa" },
        { icon: "🔋", title: "Solar Micro-Grid & EV Power Setup", desc: "Building renewable energy storage & smart meter stations", dept: "eesa" },
        { icon: "🌉", title: "Seismic-Resistant Bridge Model", desc: "Testing physical structural loads, CAD bridge drafting", dept: "cesa" },
        { icon: "🤖", title: "Autonomous Drone or IoT Node", desc: "Circuit boards, microcontroller firmware & wireless mesh", dept: "aexs" },
        { icon: "📊", title: "Predictive AI or Computer Vision", desc: "Training neural models, image classification & NLP agents", dept: "aiesa" }
      ]
    },
    {
      title: "Step 3: What is your ideal workshop or learning format?",
      desc: "Choose the environment where you learn and thrive best.",
      options: [
        { icon: "⌨️", title: "24-Hour Hackathons & Coding Circles", desc: "Pair programming, sprint problem solving, git collaboration", dept: "csesa" },
        { icon: "🔧", title: "Central Workshop Fabrications", desc: "Lathes, CNC machinery, welding & chassis assembly", dept: "mesa" },
        { icon: "💡", title: "Power Labs & Substation Tech Tours", desc: "High voltage experiments, circuit simulations & transformer analysis", dept: "eesa" },
        { icon: "📐", title: "Drafting Labs & Field Surveying", desc: "Total station surveying, concrete stress analysis & CAD layout", dept: "cesa" },
        { icon: "🔌", title: "Breadboard & Microcontroller Bootcamps", desc: "Soldering, sensor interfacing & RF spectrum analysis", dept: "aexs" },
        { icon: "📈", title: "Data Hackathons & Kaggle Sprints", desc: "Python notebook analytics, model evaluation & GPU compute", dept: "aiesa" }
      ]
    }
  ];

  const deptDetails = {
    csesa: {
      name: "CSESA",
      title: "Computer Science & Engineering Students Association",
      desc: "Your passion aligns seamlessly with CSESA! You will thrive participating in coding circles, 24-hour hackathons, web platforms, and open-source project sprints under departmental mentorship.",
      link: "cep-cesa.html",
      coord: "Prof. P.D. Jawalkar",
      color: "var(--accent-csesa)"
    },
    mesa: {
      name: "MESA",
      title: "Mechanical Engineering Students Association",
      desc: "Your answers highlight a strong affinity for physical machinery, design, and vehicle engineering! MESA offers hands-on CAD prototyping, precision robotics, and national BAJA SAE racing.",
      link: "cep-mesa.html",
      coord: "Prof. S. S. Kale (HOD)",
      color: "var(--accent-mesa)"
    },
    eesa: {
      name: "EESA",
      title: "Electrical Engineering Students Association",
      desc: "You are oriented toward the future of clean energy, electric mobility, and smart grid automation! EESA is your gateway to high-voltage power systems, solar microgrids, and industrial drives.",
      link: "esa.html",
      coord: "Dr. P. R. Padghan (HOD)",
      color: "var(--accent-eesa)"
    },
    cesa: {
      name: "CESA",
      title: "Civil Engineering Students Association",
      desc: "Your vision is set on monumental infrastructure, smart urban development, and structural integrity! CESA provides total station surveying, bridge-load contests, and modern CAD architecture.",
      link: "civil.html",
      coord: "Dr. S. S. Jahagirdar (HOD)",
      color: "var(--accent-cesa)"
    },
    aexs: {
      name: "AEXS",
      title: "Electronics & Telecommunication Association",
      desc: "You are fascinated by hardware-to-cloud interfaces, RF signals, and embedded electronics! AEXS empowers students to build microchips, sensor telemetry networks, and IoT robotics.",
      link: "entc.html",
      coord: "Dr. P. D. Bahirgonde (HOD)",
      color: "var(--accent-aexs)"
    },
    aiesa: {
      name: "AIESA",
      title: "Artificial Intelligence & Data Science Association",
      desc: "You are driven by intelligent algorithms, data insights, and automated perception! AIESA is the launchpad for machine learning models, computer vision, and neural network innovation.",
      link: "aids.html",
      coord: "Prof. M. S. Otari (HOD)",
      color: "var(--accent-aiesa)"
    }
  };

  let currentStep = 0;
  const selections = [];

  function renderStep() {
    const q = questions[currentStep];
    const dotsHtml = questions.map((_, i) => {
      const cls = i === currentStep ? 'quiz-step-dot active' : (i < currentStep ? 'quiz-step-dot done' : 'quiz-step-dot');
      return `<span class="${cls}">${i < currentStep ? '✓' : (i + 1)}</span>`;
    }).join('');

    const optionsHtml = q.options.map((opt, idx) => `
      <button class="quiz-option-btn" data-dept="${opt.dept}" data-idx="${idx}">
        <span class="quiz-option-icon">${opt.icon}</span>
        <div class="quiz-option-text">
          <h4>${opt.title}</h4>
          <p>${opt.desc}</p>
        </div>
      </button>
    `).join('');

    quizContainer.innerHTML = `
      <div class="quiz-card">
        <div class="quiz-header">
          <div class="quiz-badge">
            <span>🎯</span>
            <span>Fresher Discovery Quiz • 60-Second Matcher</span>
          </div>
          <div class="quiz-progress-bar">
            ${dotsHtml}
          </div>
        </div>

        <h3 class="quiz-question-title">${q.title}</h3>
        <p class="quiz-question-desc">${q.desc}</p>

        <div class="quiz-options-grid">
          ${optionsHtml}
        </div>

        <div class="quiz-actions">
          <span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--color-text-muted);">
            Step ${currentStep + 1} of ${questions.length} • Click an option to proceed
          </span>
          ${currentStep > 0 ? `<button id="quiz-prev-btn" class="btn-secondary" style="padding: 0.4rem 1rem; font-size: 0.82rem;">← Previous Step</button>` : ''}
        </div>
      </div>
    `;

    // Bind option clicks
    const optionBtns = quizContainer.querySelectorAll('.quiz-option-btn');
    optionBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const dept = btn.getAttribute('data-dept');
        selections[currentStep] = dept;
        btn.classList.add('selected');
        setTimeout(() => {
          if (currentStep < questions.length - 1) {
            currentStep++;
            renderStep();
          } else {
            renderResult();
          }
        }, 220);
      });
    });

    const prevBtn = quizContainer.querySelector('#quiz-prev-btn');
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        if (currentStep > 0) {
          currentStep--;
          renderStep();
        }
      });
    }
  }

  function renderResult() {
    // Count tally
    const counts = {};
    selections.forEach(d => {
      counts[d] = (counts[d] || 0) + 1;
    });

    let bestDept = 'csesa';
    let maxCount = 0;
    Object.keys(counts).forEach(d => {
      if (counts[d] > maxCount) {
        maxCount = counts[d];
        bestDept = d;
      }
    });

    const result = deptDetails[bestDept] || deptDetails.csesa;
    const matchScore = Math.floor(88 + Math.random() * 10);

    quizContainer.innerHTML = `
      <div class="quiz-card">
        <div class="quiz-result-wrap">
          <span class="quiz-match-badge">🎯 ${matchScore}% Affinity Match Found!</span>
          <h2 class="quiz-result-title">${result.name}</h2>
          <div class="quiz-result-dept">${result.title}</div>
          <p class="quiz-result-desc">${result.desc}</p>

          <div style="margin-bottom: 2rem; font-family: var(--font-mono); font-size: 0.85rem; color: var(--color-text-muted);">
            Department Coordinator: <strong style="color: #ffffff;">${result.coord}</strong> • Solapur Campus Block
          </div>

          <div class="quiz-result-buttons">
            <a href="${result.link}" class="btn-primary" style="padding: 0.75rem 2rem;">
              <span>EXPLORE ${result.name} PORTAL</span>
              <span>→</span>
            </a>
            <button class="btn-secondary" style="padding: 0.75rem 1.75rem;" onclick="openMembershipModal('${result.name}')">
              <span>APPLY FOR MEMBERSHIP 📝</span>
            </button>
            <button id="quiz-restart-btn" class="btn-secondary" style="padding: 0.75rem 1.25rem;">
              <span>Retake Quiz ↺</span>
            </button>
          </div>
        </div>
      </div>
    `;

    const restartBtn = quizContainer.querySelector('#quiz-restart-btn');
    if (restartBtn) {
      restartBtn.addEventListener('click', () => {
        currentStep = 0;
        selections.length = 0;
        renderStep();
      });
    }
  }

  renderStep();
}

/* --------------------------------------------------------------------------
   10. FUNCTIONAL MEMBERSHIP FORM MODAL & CRYPTOGRAPHIC PASS
   -------------------------------------------------------------------------- */
function initMembershipModal() {
  const overlay = document.getElementById('membership-modal-overlay');
  if (!overlay) return;

  const form = document.getElementById('membership-form');
  const passContainer = document.getElementById('membership-pass-container');
  const formWrap = document.getElementById('membership-form-wrap');
  const closeBtns = overlay.querySelectorAll('.membership-modal-close, .btn-pass-close');

  const assocToDeptMap = {
    'CSESA': 'Computer Science & Engineering',
    'MESA': 'Mechanical Engineering',
    'EESA': 'Electrical Engineering',
    'CESA': 'Civil Engineering',
    'AEXS': 'Electronics & Telecommunication',
    'AIESA': 'AI & Data Science'
  };

  window.openMembershipModal = function(preselectedDept) {
    if (preselectedDept) {
      const assocSelect = document.getElementById('member-association');
      if (assocSelect) assocSelect.value = preselectedDept;

      const deptSelect = document.getElementById('member-dept');
      if (deptSelect && assocToDeptMap[preselectedDept]) {
        deptSelect.value = assocToDeptMap[preselectedDept];
      }
    }

    const existingAlert = document.getElementById('membership-alert');
    if (existingAlert) existingAlert.remove();

    if (formWrap) formWrap.style.display = 'block';
    if (passContainer) passContainer.style.display = 'none';
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    overlay.querySelector('.membership-modal')?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  function closeModal() {
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  closeBtns.forEach(btn => btn.addEventListener('click', closeModal));

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.classList.contains('active')) {
      closeModal();
    }
  });

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const nameInput = document.getElementById('member-name');
      const rollInput = document.getElementById('member-roll');
      const emailInput = document.getElementById('member-email');
      const deptInput = document.getElementById('member-dept');
      const yearInput = document.getElementById('member-year');
      const assocInput = document.getElementById('member-association');
      const interestInput = document.getElementById('member-interest');

      const name = (nameInput?.value || '').trim();
      const roll = (rollInput?.value || '').trim().toUpperCase();
      const email = (emailInput?.value || '').trim().toLowerCase();
      const dept = (deptInput?.value || 'Computer Science & Engineering').trim();
      const year = (yearInput?.value || 'Second Year (SY)').trim();
      const association = (assocInput?.value || 'CSESA').trim();
      const interest = (interestInput?.value || '').trim();

      // Clear previous alerts
      const prevAlert = document.getElementById('membership-alert');
      if (prevAlert) prevAlert.remove();

      // Validate required inputs
      if (!name || !roll) {
        if (!name && nameInput) nameInput.style.borderColor = '#ff5252';
        if (!roll && rollInput) rollInput.style.borderColor = '#ff5252';
        const alertDiv = document.createElement('div');
        alertDiv.id = 'membership-alert';
        alertDiv.className = 'alert-banner alert-warning';
        alertDiv.innerHTML = `<span>⚠️</span> <div><strong>Missing Information:</strong> Please provide your Full Name and Roll No / PRN to generate your official pass.</div>`;
        formWrap.insertBefore(alertDiv, form);
        if (typeof playAudioTone === 'function') playAudioTone(260, 0.15, 'sawtooth');
        return;
      }

      if (nameInput) nameInput.style.borderColor = '';
      if (rollInput) rollInput.style.borderColor = '';


      // Submit Button Loading State
      const submitBtn = form.querySelector('button[type="submit"]');
      const originalBtnHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>GENERATING DIGITAL PASS & QR...</span> <span>⏳</span>`;
      }

      const payload = {
        name: name,
        roll: roll,
        email: email,
        dept: dept,
        year: year,
        association: association,
        interest: interest || 'General Technical Participation & Workshops'
      };

      try {
        const response = await apiFetch('/api/memberships', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await response.json();

        // Check if student account is restricted / banned by Administrator
        if (response.status === 403) {
          const alertDiv = document.createElement('div');
          alertDiv.id = 'membership-alert';
          alertDiv.className = 'alert-banner alert-error';
          alertDiv.style.background = 'rgba(255, 82, 82, 0.15)';
          alertDiv.style.borderColor = '#ff5252';
          alertDiv.innerHTML = `
            <div style="font-size: 1.25rem;">⛔</div>
            <div>
              <strong style="color: #ff5252; display: block; margin-bottom: 0.35rem;">Account Restricted by Administrator</strong>
              <div style="font-size: 0.85rem; line-height: 1.45; color: #f8fafc;">
                ${data.detail || 'Your Roll No / Email was restricted by the Department Administrator. An official Rejoin Approval Request has been logged for Administrator review. Please contact the Coordinator or check back once approved.'}
              </div>
            </div>
          `;
          formWrap.insertBefore(alertDiv, form);
          overlay.querySelector('.membership-modal')?.scrollTo({ top: 0, behavior: 'smooth' });

          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHtml;
          }
          if (typeof playAudioTone === 'function') playAudioTone(220, 0.2, 'sawtooth');
          return;
        }

        if (!response.ok) {
          const alertDiv = document.createElement('div');
          alertDiv.id = 'membership-alert';
          alertDiv.className = 'alert-banner alert-warning';
          alertDiv.innerHTML = `<span>⚠️</span> <div>${data.detail || 'Registration encountered an issue. Please verify details.'}</div>`;
          formWrap.insertBefore(alertDiv, form);

          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHtml;
          }
          return;
        }

        // Success: Cache verified pass in localStorage
        try {
          localStorage.setItem('orchid_student_roll', roll);
          localStorage.setItem('orchid_student_name', name);
          localStorage.setItem('orchid_student_email', email);
          localStorage.setItem('orchid_student_pass', data.pass_id);
          if (data.student_id) localStorage.setItem('orchid_student_id', data.student_id);

          // Save into array of passes for instant retrieval
          let passList = JSON.parse(localStorage.getItem('orchid_saved_passes') || '[]');
          passList = passList.filter(p => p.pass_id !== data.pass_id && !(p.roll_no === roll && p.association === association));
          passList.unshift(data);
          localStorage.setItem('orchid_saved_passes', JSON.stringify(passList.slice(0, 20)));
        } catch(e) {}

        // Render official 3D Holographic Flip Smart Pass
        renderDigitalPass(data);

      } catch (networkErr) {
        console.warn('Backend API connection failed; membership outcome could not be confirmed:', networkErr);
        const alertDiv = document.createElement('div');
        alertDiv.id = 'membership-alert';
        alertDiv.className = 'alert-banner alert-warning';
        alertDiv.innerHTML = `<span>⚠️</span> <div>The membership service could not be reached. Check for an existing pass or try again when the service is online.</div>`;
        formWrap.insertBefore(alertDiv, form);

        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalBtnHtml;
        }
      }
    });
  }

  // Render Official 3D Holographic Flip Digi-Pass
  window.renderDigitalPass = function(data) {
    const fWrap = document.getElementById('membership-form-wrap');
    const pContainer = document.getElementById('membership-pass-container');
    const modalOverlay = document.getElementById('membership-modal-overlay');

    if (fWrap) fWrap.style.display = 'none';
    if (pContainer) {
      pContainer.style.display = 'block';
      modalOverlay?.querySelector('.membership-modal')?.scrollTo({ top: 0, behavior: 'smooth' });
      pContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });

      const initials = (data.name || '').split(' ').map(n => n[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'NK';
      const safeName = (data.name || '').replace(/'/g, "\\'");
      const safeAssoc = (data.association || '').replace(/'/g, "\\'");
      const stuId = data.student_id || data.pass_id;
      const assocThemes = {
        'CSESA': { gradient: 'linear-gradient(135deg, #061529 0%, #0B2B4A 50%, #041021 100%)', border: '#00D2FF', glow: 'rgba(0, 210, 255, 0.35)', text: '#00D2FF' },
        'MESA': { gradient: 'linear-gradient(135deg, #240E05 0%, #3D1807 50%, #150803 100%)', border: '#FF6B35', glow: 'rgba(255, 107, 53, 0.35)', text: '#FF6B35' },
        'EESA': { gradient: 'linear-gradient(135deg, #241D05 0%, #3D3208 50%, #141103 100%)', border: '#FFD700', glow: 'rgba(255, 215, 0, 0.35)', text: '#FFD700' },
        'CESA': { gradient: 'linear-gradient(135deg, #052417 0%, #083D28 50%, #03140D 100%)', border: '#10B981', glow: 'rgba(16, 185, 129, 0.35)', text: '#10B981' },
        'AEXS': { gradient: 'linear-gradient(135deg, #200529 0%, #340942 50%, #110217 100%)', border: '#A855F7', glow: 'rgba(168, 85, 247, 0.35)', text: '#A855F7' },
        'AIESA': { gradient: 'linear-gradient(135deg, #051A24 0%, #082E3D 50%, #031017 100%)', border: '#06B6D4', glow: 'rgba(6, 182, 212, 0.35)', text: '#06B6D4' }
      };
      const theme = assocThemes[data.association] || { gradient: 'linear-gradient(135deg, #101524 0%, #07090F 50%, #151D33 100%)', border: 'rgba(255,184,0,0.5)', glow: 'rgba(255,184,0,0.25)', text: 'var(--brand-gold)' };


      // Handle QR code image source (data URI or direct image URL)
      const qrSrc = data.qr_code_base64 || `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(data.verify_url || window.location.href)}`;

      pContainer.innerHTML = `
        <!-- Success Banner -->
        <div style="background: linear-gradient(135deg, rgba(25, 214, 140, 0.15), rgba(0, 168, 107, 0.25)); border: 1px solid rgba(25, 214, 140, 0.4); border-radius: 12px; padding: 0.85rem 1.15rem; margin-bottom: 1.25rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
          <div style="display: flex; align-items: center; gap: 0.65rem;">
            <div style="width: 36px; height: 36px; border-radius: 50%; background: #19D68C; color: #080A0F; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; font-weight: 800;">✓</div>
            <div>
              <div style="font-size: 0.95rem; font-weight: 800; color: #19D68C; letter-spacing: 0.02em;">OFFICIAL DIGI-PASS GENERATED!</div>
              <div style="font-size: 0.78rem; color: #cbd5e1;">Saved in NKOCET SQLite Database &bull; Verified Student Pass Ready</div>
            </div>
          </div>
          <span style="font-family: var(--font-mono); font-size: 0.75rem; background: rgba(0,0,0,0.4); padding: 0.25rem 0.6rem; border-radius: 4px; color: var(--brand-gold); border: 1px solid rgba(255,184,0,0.3);">
            ${data.association} 2026
          </span>
        </div>

        <div class="card-3d-scene">
          <div class="card-3d-flipper" id="smart-card-flipper" onclick="this.classList.toggle('flipped')" title="Click anywhere to flip card">
            <!-- FRONT FACE -->
            <div class="card-face card-face-front" style="background: ${theme.gradient} !important; border: 1.5px solid ${theme.border} !important; box-shadow: 0 12px 36px ${theme.glow} !important;">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <div style="font-size: 0.68rem; letter-spacing: 0.08em; color: var(--brand-gold); font-weight: 700; text-transform: uppercase;">NK ORCHID COLLEGE OF ENGG & TECH</div>
                  <div style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF; letter-spacing: 0.02em;">${data.association} OFFICIAL PASS</div>
                </div>
                <div class="smart-chip" title="Cryptographic NFC/Chip"></div>
              </div>

              <div style="display: flex; align-items: center; gap: 1rem; margin: 0.75rem 0;">
                <div class="card-avatar">${initials}</div>
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${data.name}</div>
                  <div style="font-size: 0.82rem; color: var(--color-text-secondary); font-family: var(--font-mono); margin-top: 0.2rem;">PRN: ${data.roll_no} • ${data.year}</div>
                  <div style="font-size: 0.78rem; color: var(--brand-gold); margin-top: 0.15rem;">${data.dept}</div>
                </div>
              </div>

              <div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end; font-size: 0.75rem; color: var(--color-text-muted);">
                  <div>
                    <div>
                      <span>PASS ID: </span>
                      <strong style="color: #FFFFFF; font-family: var(--font-mono);">${data.pass_id}</strong>
                    </div>
                    <div style="font-size: 0.72rem; color: #19D68C; margin-top: 0.2rem;">
                      VERIFIED ID: <strong style="color: #FFFFFF; font-family: var(--font-mono);">${stuId}</strong>
                    </div>
                  </div>
                  <div style="text-align: right;">
                    <span style="color: #19D68C; font-weight: 700; font-size: 0.76rem; display: block;">✓ Saved in SQLite Database</span>
                    <span style="color: #64b5f6; font-size: 0.7rem; font-family: var(--font-mono);">${data.email || ''}</span>
                  </div>
                </div>
                <div class="barcode-strip" title="Digital Gate Barcode"></div>
              </div>
            </div>

            <!-- BACK FACE -->
            <div class="card-face card-face-back" style="background: ${theme.gradient} !important; border: 1.5px solid ${theme.border} !important; box-shadow: 0 12px 36px ${theme.glow} !important;">
              <div style="width: 100%; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.4rem;">
                <span style="font-size: 0.75rem; color: var(--brand-gold); font-weight: 700;">GATE QR TOKEN</span>
                <span style="font-size: 0.72rem; font-family: var(--font-mono); color: var(--color-text-muted);">${stuId}</span>
              </div>

              <div style="display: flex; align-items: center; justify-content: center; gap: 1.25rem; margin: auto 0;">
                <div style="background: #FFFFFF; padding: 6px; border-radius: 8px; width: 110px; height: 110px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
                  <img src="${qrSrc}" alt="Gate Pass QR" style="width: 100%; height: 100%; object-fit: contain; display: block;">
                </div>
                <div style="text-align: left; max-width: 200px;">
                  <div style="font-size: 0.85rem; font-weight: 700; color: #FFFFFF;">Instant Gate Scan</div>
                  <p style="font-size: 0.72rem; color: var(--color-text-secondary); margin: 0.25rem 0 0.5rem 0; line-height: 1.4;">
                    Scan at entrance or campus events to verify active membership.
                  </p>
                  <a href="${data.verify_url}" target="_blank" style="color: var(--brand-gold); font-size: 0.75rem; text-decoration: underline; font-weight: 600;">
                    Open Public Link ↗
                  </a>
                </div>
              </div>

              <div style="font-size: 0.7rem; color: var(--color-text-muted); width: 100%;">
                Tap card to flip front ⟲ • Valid for Academic Session 2026
              </div>
            </div>
          </div>
        </div>

        <div style="text-align: center; margin-bottom: 1.25rem; font-size: 0.82rem; color: var(--brand-gold); cursor: pointer;" onclick="document.getElementById('smart-card-flipper').classList.toggle('flipped')">
          🔄 <strong>Click or Tap Card to Flip</strong> (View Gate QR / Verified ID)
        </div>

        <div style="background: rgba(25, 214, 140, 0.08); border: 1px solid rgba(25, 214, 140, 0.3); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1.25rem; text-align: center;">
          <div style="font-size: 0.88rem; color: #19D68C; font-weight: 700; margin-bottom: 0.2rem;">
            ✓ Pass Saved in NKOCET SQLite Database!
          </div>
          <div style="font-size: 0.8rem; color: #cbd5e1;">
            Verified Student ID: <strong style="color: #fff; font-family: var(--font-mono);">${stuId}</strong> &bull; Pass ID: <strong style="color: #fff; font-family: var(--font-mono);">${data.pass_id}</strong>
          </div>
        </div>

        <div style="display: flex; gap: 0.6rem; justify-content: center; flex-wrap: wrap;">
          <button type="button" class="btn-primary" onclick="copyPassDetails('${safeName}', '${data.roll_no}', '${data.dept}', '${safeAssoc}', '${data.pass_id}', '${stuId}', '${data.verify_url}')" style="padding: 0.65rem 1.15rem; background: #19D68C; color: #000; font-weight: 700; border: none; cursor: pointer;">
            <span>📋 COPY DIGI-PASS</span>
          </button>
          <button type="button" class="btn-secondary" onclick="downloadPassSvg('${safeName}', '${data.roll_no}', '${data.dept}', '${safeAssoc}', '${data.pass_id}', '${stuId}', '${qrSrc}')" style="padding: 0.65rem 1.15rem; cursor: pointer; border-color: rgba(255,184,0,0.4); color: var(--brand-gold);">
            <span>📥 DOWNLOAD PASS</span>
          </button>
          <button type="button" class="btn-primary" onclick="window.print()" style="padding: 0.65rem 1.15rem; cursor: pointer;">
            <span>🖨️ PRINT / PDF PASS</span>
          </button>
          <button type="button" class="btn-success" onclick="sharePassWhatsApp('${safeName}', '${safeAssoc}', '${data.verify_url}', '${data.pass_id}')" style="padding: 0.65rem 1.15rem; cursor: pointer;">
            <span>📱 SHARE ON WHATSAPP</span>
          </button>
          <a href="${data.verify_url}" target="_blank" class="btn-secondary" style="padding: 0.65rem 1.15rem; text-decoration: none; display: inline-flex; align-items: center; gap: 0.35rem;">
            <span>🔍 GATE PASS ↗</span>
          </a>
          <button type="button" class="btn-secondary" onclick="resetToMembershipForm()" style="padding: 0.65rem 1.15rem; cursor: pointer;" title="Register for another departmental association">
            <span>➕ JOIN ANOTHER CLUB</span>
          </button>
          <button type="button" class="btn-secondary btn-pass-close" style="padding: 0.65rem 1.15rem; cursor: pointer;" onclick="document.getElementById('membership-modal-overlay').classList.remove('active'); document.body.style.overflow='';">
            <span>✕ CLOSE</span>
          </button>
        </div>
      `;

      if (typeof playAudioTone === 'function') playAudioTone(880, 0.12, 'sine');
      if (typeof window.showToast === 'function') {
        window.showToast(data.message || `Official ${data.association} Digi-Pass Generated Successfully!`, "success");
      }
    }
  };

  // Switch from Pass back to Form to Register Another Association
  window.resetToMembershipForm = function() {
    if (formWrap) formWrap.style.display = 'block';
    if (passContainer) passContainer.style.display = 'none';
    const nameInput = document.getElementById('member-name');
    if (nameInput) nameInput.focus();
    overlay.querySelector('.membership-modal')?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Quick Digi-Pass Lookup Handler
  
  // Download Official Pass Vector Card (.SVG)
  window.downloadPassSvg = function(name, roll, dept, assoc, passId, studentId, qrDataUrl) {
    const initials = (name || '').split(' ').map(n => n[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'NK';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="380" viewBox="0 0 600 380">
      <defs>
        <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#080D1A"/>
          <stop offset="50%" stop-color="#101A30"/>
          <stop offset="100%" stop-color="#0B1324"/>
        </linearGradient>
      </defs>
      <rect width="600" height="380" rx="20" fill="url(#cardGrad)" stroke="#FFB800" stroke-width="2"/>
      <text x="35" y="42" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#FFB800" letter-spacing="2">NK ORCHID COLLEGE OF ENGG &amp; TECH</text>
      <text x="35" y="74" font-family="Arial, sans-serif" font-size="22" font-weight="800" fill="#FFFFFF">${assoc} OFFICIAL SMART PASS 2026</text>
      <circle cx="65" cy="140" r="28" fill="#FFB800" opacity="0.2"/>
      <circle cx="65" cy="140" r="28" fill="none" stroke="#FFB800" stroke-width="2"/>
      <text x="65" y="148" font-family="Arial, sans-serif" font-size="18" font-weight="800" fill="#FFB800" text-anchor="middle">${initials}</text>
      <text x="110" y="136" font-family="Arial, sans-serif" font-size="20" font-weight="800" fill="#FFFFFF">${name}</text>
      <text x="110" y="158" font-family="monospace" font-size="13" fill="#cbd5e1">PRN: ${roll}</text>
      <text x="35" y="210" font-family="Arial, sans-serif" font-size="13" font-weight="600" fill="#FFB800">${dept}</text>
      <line x1="35" y1="230" x2="565" y2="230" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
      <text x="35" y="260" font-family="monospace" font-size="12" fill="#94a3b8">PASS ID: <tspan fill="#FFFFFF" font-weight="700">${passId}</tspan></text>
      <text x="35" y="285" font-family="monospace" font-size="12" fill="#94a3b8">STUDENT ID: <tspan fill="#19D68C" font-weight="700">${studentId}</tspan></text>
      <text x="35" y="340" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#19D68C">&#10003; Verified &amp; Saved in NKOCET SQLite Database (Active 2026)</text>
      <image href="${qrDataUrl}" x="460" y="240" width="100" height="100"/>
    </svg>`;
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `NKOCET_${assoc}_Pass_${(roll || 'Student').replace(/[^a-zA-Z0-9]/g, '')}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    if (typeof playAudioTone === 'function') playAudioTone(960, 0.1, 'sine');
    if (typeof window.showToast === 'function') {
      window.showToast('📥 Official Digi-Pass Vector Card Downloaded!', 'green');
    }
  };

  window.lookupStudentPass = async function() {
    const input = document.getElementById('quick-pass-lookup');
    const query = (input ? input.value : '').trim();
    if (!query) {
      alert('Please enter your PRN / Roll No (e.g. C-62) or Gmail address to retrieve your pass.');
      if (input) input.focus();
      return;
    }

    const email = (window.prompt('Enter the Gmail address registered to this pass:') || '').trim().toLowerCase();
    if (!email) return;
    const sessionId = window.createVerificationSessionId();
    try {
      const sendRes = await apiFetch('/api/memberships/lookup/send-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, email, session_id: sessionId })
      });
      const sendData = await sendRes.json();
      if (!sendRes.ok) {
        alert(sendData.detail || 'Unable to send a verification code for that membership.');
        return;
      }

      const otp = (window.prompt(`Enter the OTP sent to ${sendData.masked_email || email}:`) || '').trim();
      if (!otp) return;
      const verifyRes = await apiFetch('/api/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          otp,
          roll_no: sendData.roll_no,
          association: sendData.association,
          session_id: sessionId
        })
      });
      const verifyData = await verifyRes.json();
      if (!verifyRes.ok || !verifyData.verified) {
        alert(verifyData.detail || 'Email verification failed.');
        return;
      }

      const res = await apiFetch('/api/memberships/lookup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          email,
          roll_no: sendData.roll_no,
          association: sendData.association,
          otp_token: verifyData.verification_token,
          session_id: sessionId
        })
      });
      const data = await res.json();
      if (res.ok) {
        renderDigitalPass(data);
        return;
      }
      alert(data.detail || 'Unable to retrieve that membership pass.');
    } catch (err) {
      alert('Unable to verify or retrieve the pass because the server could not be reached: ' + err.message);
    }
  };

  const quickInput = document.getElementById('quick-pass-lookup');
  if (quickInput) {
    quickInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        window.lookupStudentPass();
      }
    });
  }

  // 1-Click Copy Pass Details to Clipboard
  window.copyPassDetails = function(name, roll, dept, assoc, passId, studentId, verifyUrl) {
    const text = `🎓 NKOCET OFFICIAL DIGITAL MEMBERSHIP PASS
-----------------------------------------------
Student Name: ${name}
PRN / Roll No: ${roll}
Department: ${dept}
Association: ${assoc}
Verified Student ID: ${studentId || passId}
Official Pass ID: ${passId}
Database Status: SQLite Database Verified (Active)
Public Gate Verification URL: ${verifyUrl}
-----------------------------------------------
Issued by NK Orchid College of Engineering & Technology (NKOCET 2026)`;

    const onSuccess = () => {
      if (typeof playAudioTone === 'function') playAudioTone(660, 0.08, 'sine');
      if (typeof window.showToast === 'function') {
        window.showToast('📋 Official Digi-Pass copied to clipboard!', 'green');
      } else {
        alert('Digi-Pass details copied to clipboard!');
      }
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(onSuccess).catch(() => {
        fallbackCopy(text);
        onSuccess();
      });
    } else {
      fallbackCopy(text);
      onSuccess();
    }

    function fallbackCopy(str) {
      const el = document.createElement('textarea');
      el.value = str;
      el.setAttribute('readonly', '');
      el.style.position = 'absolute';
      el.style.left = '-9999px';
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
  };
}
/* --------------------------------------------------------------------------
   11. EVENT CALENDAR INTEGRATION (.ICS & GOOGLE CALENDAR)
   -------------------------------------------------------------------------- */
function initCalendarEvents() {
  window.addToGoogleCalendar = function(title, description, location, startDateStr, endDateStr) {
    const startIso = startDateStr ? startDateStr.replace(/-|:|\.\d\d\d/g, "") : "20261201T090000Z";
    const endIso = endDateStr ? endDateStr.replace(/-|:|\.\d\d\d/g, "") : "20261203T170000Z";
    const url = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&details=${encodeURIComponent(description)}&location=${encodeURIComponent(location)}&dates=${startIso}/${endIso}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  window.downloadIcsFile = function(title, description, location, startDateStr, endDateStr) {
    const start = startDateStr ? startDateStr.replace(/-|:|\.\d\d\d/g, "") : "20261201T090000Z";
    const end = endDateStr ? endDateStr.replace(/-|:|\.\d\d\d/g, "") : "20261203T170000Z";
    
    const icsContent = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//NKOCET//AssociationHub Events//EN',
      'CALSCALE:GREGORIAN',
      'BEGIN:VEVENT',
      `SUMMARY:${title}`,
      `DESCRIPTION:${description}`,
      `LOCATION:${location}`,
      `DTSTART:${start}`,
      `DTEND:${end}`,
      'STATUS:CONFIRMED',
      'END:VEVENT',
      'END:VCALENDAR'
    ].join('\r\n');

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.setAttribute('download', `${title.toLowerCase().replace(/[^a-z0-9]/g, '_')}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
}

/* --------------------------------------------------------------------------
   12. 3D CARD TILT & SMOOTH MICRO-INTERACTIONS
   -------------------------------------------------------------------------- */
function init3DTilt() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.innerWidth < 768) return; // Don't run tilt on small mobile touchscreens

  const tiltCards = document.querySelectorAll('.association-card, .team-card, .showcase-card, .quiz-card');
  if (!tiltCards.length) return;

  tiltCards.forEach(card => {
    card.classList.add('tilt-card');

    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;

      const rotateX = ((y - centerY) / centerY) * -5;
      const rotateY = ((x - centerX) / centerX) * 5;

      card.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-4px)`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px)';
    });
  });
}


/* --------------------------------------------------------------------------
   13. FRESHERS' FAQ ACCORDION INTERACTIVITY
   -------------------------------------------------------------------------- */
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');
  if (!faqItems.length) return;

  faqItems.forEach(item => {
    const questionBtn = item.querySelector('.faq-question');
    if (!questionBtn) return;

    questionBtn.addEventListener('click', () => {
      const isOpen = item.classList.contains('active');
      faqItems.forEach(i => i.classList.remove('active'));
      if (!isOpen) {
        item.classList.add('active');
      }
    });
  });
}

/* --------------------------------------------------------------------------
   14. DYNAMIC LIVE CAMPUS ANNOUNCEMENT BANNER
   -------------------------------------------------------------------------- */
async function initAnnouncementBanner() {
  const banner = document.querySelector('.announcement-banner');
  if (!banner) return;

  try {
    const res = await apiFetch('/api/announcements/current');
    if (!res.ok) return;
    const data = await res.json();
    const tagEl = banner.querySelector('.announcement-tag');
    const textEl = banner.querySelector('.announcement-text');
    const btnEl = banner.querySelector('.announcement-btn');
    if (tagEl && data.tag) tagEl.textContent = data.tag;
    if (textEl && data.message) textEl.textContent = data.message;
    if (btnEl && data.button_text) btnEl.textContent = data.button_text;
  } catch (err) {
    // Graceful fallback
  }
}

/* --------------------------------------------------------------------------
   15. CAMPUS PULSE: STUDENT EXPERIENCE & DISCUSSION HUB
   -------------------------------------------------------------------------- */
function initCampusPulse() {
  const grid = document.getElementById('community-posts-grid');
  const modal = document.getElementById('community-modal-overlay');
  const modalAlert = document.getElementById('community-modal-alert');
  const postForm = document.getElementById('community-post-form');

  let currentCategory = 'ALL';
  let loadedPosts = [];
  let _pulseRealtimeTimer = null;
  let _isSyncingPosts = false;
  let _currentChatUser = null;
  // Real-Time Background Synchronization Engine (Silent Auto-Sync every 3 seconds)
  async function syncRealtimeCommunityPosts() {
    if (_isSyncingPosts || !grid) return;
    _isSyncingPosts = true;
    try {
      const url = currentCategory === 'ALL' 
        ? '/api/community/posts' 
        : `/api/community/posts?category=${encodeURIComponent(currentCategory)}`;
      const res = await apiFetch(url);
      if (res.ok) {
        const data = await res.json();
        const incoming = data.posts || [];
        const curKeys = loadedPosts.map(p => `${p.post_id}_${p.likes}_${p.comment_count}`).join('|');
        const inKeys = incoming.map(p => `${p.post_id}_${p.likes}_${p.comment_count}`).join('|');
        if (curKeys !== inKeys) {
          loadedPosts = incoming;
          renderCommunityPosts(loadedPosts);
          const counterEl = document.getElementById('realtime-stream-counter');
          if (counterEl) {
            counterEl.textContent = `🟢 Live • ${incoming.length} Messages Synced`;
          }
        }
      }
    } catch(e) {
    } finally {
      _isSyncingPosts = false;
    }
  }

  if (!_pulseRealtimeTimer) {
    _pulseRealtimeTimer = setInterval(syncRealtimeCommunityPosts, 3000);
  }

  // --- GATED CHAT AUTHENTICATION GATEWAY STATE HANDLERS ---
  async function initChatGatewayState() {
    const token = localStorage.getItem('orchid_chat_token') || sessionStorage.getItem('orchid_chat_token');
    if (!token) {
      showLockedChat();
      return;
    }

    try {
      const res = await apiFetch('/api/chat/auth/me', {
        headers: { 'X-Chat-Token': token }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.user) {
          _currentChatUser = data.user;
          showUnlockedChat(_currentChatUser);
          return;
        }
      }
    } catch (e) {}

    showLockedChat();
  }

  function showUnlockedChat(user) {
    const lockedEl = document.getElementById('chat-gateway-locked');
    const unlockedEl = document.getElementById('chat-gateway-unlocked');
    if (lockedEl) lockedEl.style.display = 'none';
    if (unlockedEl) unlockedEl.style.display = 'block';

    const nameEl = document.getElementById('chat-user-name');
    const rollEl = document.getElementById('chat-user-roll');
    const deptEl = document.getElementById('chat-user-dept');
    const statusEl = document.getElementById('chat-user-status');

    if (nameEl && user.name) nameEl.textContent = user.name;
    if (rollEl && user.roll_no) rollEl.textContent = user.roll_no;
    if (deptEl && user.dept) deptEl.textContent = user.dept;
    if (statusEl && user.status) {
      statusEl.textContent = user.status;
      statusEl.className = user.status === 'MUTED' ? 'admin-badge admin-badge-status-suspended' : 'admin-badge admin-badge-status-active';
    }

    // Auto populate modal post inputs
    const postAuthor = document.getElementById('post-author');
    const postRoll = document.getElementById('post-roll');
    const postDept = document.getElementById('post-dept');
    if (postAuthor && user.name) postAuthor.value = user.name;
    if (postRoll && user.roll_no) postRoll.value = user.roll_no;
    if (postDept && user.dept) {
      for (let opt of postDept.options) {
        if (opt.value.includes(user.dept) || user.dept.includes(opt.value)) {
          postDept.value = opt.value;
          break;
        }
      }
    }
  }

  function showLockedChat() {
    const lockedEl = document.getElementById('chat-gateway-locked');
    const unlockedEl = document.getElementById('chat-gateway-unlocked');
    if (lockedEl) lockedEl.style.display = 'block';
    if (unlockedEl) unlockedEl.style.display = 'none';
    _currentChatUser = null;
  }

  window.enterChatGateway = async function() {
    const name = (document.getElementById('gate-name')?.value || '').trim();
    const roll = (document.getElementById('gate-roll')?.value || '').trim().toUpperCase();
    const dept = (document.getElementById('gate-dept')?.value || '').trim();
    const email = (document.getElementById('gate-email')?.value || '').trim().toLowerCase();
    const errEl = document.getElementById('gate-error-msg');
    const enterBtn = document.getElementById('gate-btn-enter');

    if (errEl) errEl.style.display = 'none';

    if (!name || name.length < 2) {
      if (errEl) { errEl.textContent = 'Please enter your full name.'; errEl.style.display = 'block'; }
      return;
    }
    if (!roll || roll.length < 2) {
      if (errEl) { errEl.textContent = 'Please enter your Roll No / PRN.'; errEl.style.display = 'block'; }
      return;
    }
    if (!email || !email.includes('@') || !email.includes('.')) {
      if (errEl) { errEl.textContent = 'Please enter a valid email address.'; errEl.style.display = 'block'; }
      return;
    }

    if (enterBtn) {
      enterBtn.disabled = true;
      enterBtn.innerHTML = '<span>Entering... ⏳</span>';
    }

    try {
      const res = await apiFetch('/api/chat/auth/verify-and-enter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          roll_no: roll,
          dept: dept,
          email: email
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        localStorage.setItem('orchid_chat_token', data.token);
        sessionStorage.setItem('orchid_chat_token', data.token);
        localStorage.setItem('orchid_chat_user', JSON.stringify(data.user));
        sessionStorage.setItem('orchid_chat_user', JSON.stringify(data.user));
        sessionStorage.setItem('orchid_verified_roll', roll);

        _currentChatUser = data.user;
        showUnlockedChat(data.user);
        if (typeof showToast === 'function') showToast(`✓ ${data.message}`, 'success');
        loadCommunityPosts();
      } else {
        if (errEl) {
          errEl.textContent = data.detail || 'Unable to enter chat.';
          errEl.style.display = 'block';
        }
      }
    } catch (e) {
      if (errEl) {
        errEl.textContent = 'Server connection error: ' + e.message;
        errEl.style.display = 'block';
      }
    } finally {
      if (enterBtn) {
        enterBtn.disabled = false;
        enterBtn.innerHTML = '<span>Enter Community Chat 🚀</span>';
      }
    }
  };

  window.signOutChatGateway = function() {
    localStorage.removeItem('orchid_chat_token');
    sessionStorage.removeItem('orchid_chat_token');
    localStorage.removeItem('orchid_chat_user');
    sessionStorage.removeItem('orchid_chat_user');
    showLockedChat();
    if (typeof showToast === 'function') showToast('Signed out of Community Chat.', 'info');
  };

  window.openCommunityModal = function() {
    if (!_currentChatUser) {
      const token = localStorage.getItem('orchid_chat_token') || sessionStorage.getItem('orchid_chat_token');
      if (!token) {
        if (typeof showToast === 'function') {
          showToast('Please enter your student details below to join the chat.', 'error');
        }
        const lockSec = document.getElementById('chat-gateway-locked');
        if (lockSec) lockSec.scrollIntoView({ behavior: 'smooth' });
        return;
      }
    }

    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
      if (modalAlert) modalAlert.style.display = 'none';
      if (postForm) {
        postForm.reset();
        if (_currentChatUser) {
          const authorInput = document.getElementById('post-author');
          const rollInput = document.getElementById('post-roll');
          const deptInput = document.getElementById('post-dept');
          if (authorInput) authorInput.value = _currentChatUser.name;
          if (rollInput) rollInput.value = _currentChatUser.roll_no;
          if (deptInput && _currentChatUser.dept) {
            for (let opt of deptInput.options) {
              if (opt.value.includes(_currentChatUser.dept) || _currentChatUser.dept.includes(opt.value)) {
                deptInput.value = opt.value;
                break;
              }
            }
          }
        }
      }
    }
  };

  window.closeCommunityModal = function() {
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  };

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeCommunityModal();
    });
  }

  window.filterCommunityPosts = function(category) {
    currentCategory = category;
    document.querySelectorAll('.community-pill').forEach(btn => {
      if (btn.getAttribute('data-category') === category) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    loadCommunityPosts();
  };

  async function loadCommunityPosts() {
    if (!grid) return;
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--color-text-muted);">
        <span>Loading campus experiences...</span>
      </div>
    `;

    try {
      const url = currentCategory === 'ALL' 
        ? '/api/community/posts' 
        : `/api/community/posts?category=${encodeURIComponent(currentCategory)}`;
      const res = await apiFetch(url);
      const data = await res.json();
      loadedPosts = data.posts || [];
      renderCommunityPosts(loadedPosts);
    } catch (err) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: #ff5252;">
          ⚠️ Unable to load community posts: ${err.message}
        </div>
      `;
    }
  }

  function getCategoryBadge(cat) {
    switch (cat) {
      case 'INTERVIEW': return '<span class="category-badge badge-interview">🎓 Placement & Interview</span>';
      case 'HACKATHON': return '<span class="category-badge badge-hackathon">🏆 Hackathon Experience</span>';
      case 'PROJECT_ADVICE': return '<span class="category-badge badge-project">💡 Project Advice</span>';
      case 'CLUB_LIFE': return '<span class="category-badge badge-club">⚡ Club Life</span>';
      default: return '<span class="category-badge badge-general">📢 Campus Guidance</span>';
    }
  }

  function renderCommunityPosts(posts) {
    if (!grid) return;
    if (posts.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1.5rem; background: rgba(8, 10, 15, 0.4); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md);">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">✍️</div>
          <h4 style="color: #FFFFFF; font-size: 1.1rem; margin-bottom: 0.25rem;">No Discussions Yet in this Category</h4>
          <p style="color: var(--color-text-muted); font-size: 0.88rem;">
            Be the first verified Orchidite to share your interview questions, hackathon memories, or project tips!
          </p>
          <button type="button" class="btn-primary" onclick="openCommunityModal()" style="margin-top: 1rem; padding: 0.5rem 1.25rem;">
            <span>Share My Experience</span>
          </button>
        </div>
      `;
      return;
    }

    grid.innerHTML = posts.map(p => `
      <div class="community-card" id="comm-card-${p.post_id}">
        <div>
          <div class="community-card-header">
            <div class="community-author-meta">
              <span class="community-author-name">${p.author_name}</span>
              <span class="community-author-sub">${p.dept} • ${p.year}</span>
            </div>
            ${getCategoryBadge(p.category)}
          </div>

          <h3 class="community-title">${p.title}</h3>
          <p class="community-content">${p.content.replace(/\n/g, '<br>')}</p>
        </div>

        <div>
          <div class="community-card-footer">
            <span style="font-size: 0.78rem; color: var(--color-text-muted); font-family: var(--font-mono);">
              ${p.created_at.split(' ')[0]}
            </span>
            <div style="display: flex; gap: 0.5rem;">
              <button type="button" class="community-action-btn" id="like-btn-${p.post_id}" onclick="likeCommunityPost('${p.post_id}')">
                <span>💡 Helpful</span>
                <span id="like-count-${p.post_id}">(${p.likes})</span>
              </button>
              <button type="button" class="community-action-btn" onclick="toggleComments('${p.post_id}')">
                <span>💬 (${p.comment_count})</span>
              </button>
            </div>
          </div>

          <!-- Expandable Comments Thread -->
          <div class="comments-thread" id="thread-${p.post_id}">
            <div id="comments-list-${p.post_id}">
              <div style="font-size: 0.8rem; color: var(--color-text-muted); text-align: center; padding: 0.5rem 0;">
                Loading replies...
              </div>
            </div>

            <!-- Comment Input -->
            <form onsubmit="submitPostComment('${p.post_id}', event)" class="comment-input-row">
              <input type="text" class="comment-input" id="comment-input-${p.post_id}" placeholder="Join discussion (Registered Roll No needed)..." required>
              <button type="submit" class="btn-primary" style="padding: 0.35rem 0.85rem; font-size: 0.8rem;">
                Reply
              </button>
            </form>
          </div>
        </div>
      </div>
    `).join('');
  }

  window.likeCommunityPost = async function(postId) {
    try {
      const res = await apiFetch(`/api/community/posts/${encodeURIComponent(postId)}/like`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const countEl = document.getElementById(`like-count-${postId}`);
        const btnEl = document.getElementById(`like-btn-${postId}`);
        if (countEl) countEl.textContent = `(${data.likes})`;
        if (btnEl) btnEl.classList.add('liked');
      }
    } catch (err) {
      console.error('Like error:', err);
    }
  };

  window.toggleComments = async function(postId) {
    const thread = document.getElementById(`thread-${postId}`);
    if (!thread) return;
    if (thread.classList.contains('active')) {
      thread.classList.remove('active');
    } else {
      thread.classList.add('active');
      loadThreadComments(postId);
    }
  };

  async function loadThreadComments(postId) {
    const listEl = document.getElementById(`comments-list-${postId}`);
    if (!listEl) return;
    try {
      const res = await apiFetch(`/api/community/posts/${encodeURIComponent(postId)}/comments`);
      const data = await res.json();
      const comments = data.comments || [];
      if (comments.length === 0) {
        listEl.innerHTML = `<div style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.35rem 0;">No replies yet. Ask a question or share advice!</div>`;
      } else {
        listEl.innerHTML = comments.map(c => `
          <div class="comment-bubble">
            <div class="comment-bubble-author">${c.author_name} (${c.roll_no}) <span style="font-weight: 400; color: var(--color-text-muted); font-size: 0.72rem; float: right;">${c.created_at.split(' ')[0]}</span></div>
            <div>${c.content}</div>
          </div>
        `).join('');
      }
    } catch (err) {
      listEl.innerHTML = `<div style="color: #ff5252; font-size: 0.8rem;">Failed to load comments.</div>`;
    }
  }

  window.submitPostComment = async function(postId, event) {
    event.preventDefault();
    const inputEl = document.getElementById(`comment-input-${postId}`);
    if (!inputEl || !inputEl.value.trim()) return;

    let roll = _currentChatUser ? _currentChatUser.roll_no : sessionStorage.getItem('orchid_verified_roll');
    if (!roll) {
      roll = prompt("Security Gate: Please enter your Roll No / PRN (e.g. C-62) to verify you are a registered student:");
      if (!roll || !roll.trim()) return;
      sessionStorage.setItem('orchid_verified_roll', roll.trim().toUpperCase());
    }

    try {
      const res = await apiFetch(`/api/community/posts/${encodeURIComponent(postId)}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_name: _currentChatUser ? _currentChatUser.name : 'Student',
          roll_no: roll.trim().toUpperCase(),
          content: inputEl.value.trim()
        })
      });

      const data = await res.json();
      if (res.ok) {
        inputEl.value = '';
        loadThreadComments(postId);
        if (typeof showToast === 'function') showToast('Reply posted!', 'success');
      } else {
        if (data.detail && data.detail.includes('Campus Anti-Troll Shield')) {
          alert(`🛡️ CAMPUS ANTI-TROLL SHIELD BLOCKED:\n\n${data.detail}`);
        } else {
          alert("Security Error: " + (data.detail || "Unable to post comment."));
        }
        if (res.status === 403) {
          sessionStorage.removeItem('orchid_verified_roll');
        }
      }
    } catch (err) {
      alert("Error contacting server: " + err.message);
    }
  };

  window.submitCommunityPost = async function(event) {
    event.preventDefault();
    const author = document.getElementById('post-author').value.trim();
    const roll = document.getElementById('post-roll').value.trim().toUpperCase();
    const dept = document.getElementById('post-dept').value;
    const year = document.getElementById('post-year').value;
    const category = document.getElementById('post-category').value;
    const title = document.getElementById('post-title').value.trim();
    const content = document.getElementById('post-content').value.trim();
    const isAnonymous = document.getElementById('post-anonymous').checked;
    const submitBtn = document.getElementById('post-submit-btn');

    if (modalAlert) modalAlert.style.display = 'none';
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>⏳ Verifying against Student Registry...</span>`;
    }

    try {
      const res = await apiFetch('/api/community/posts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_name: author,
          roll_no: roll,
          dept: dept,
          year: year,
          category: category,
          title: title,
          content: content,
          is_anonymous: isAnonymous
        })
      });

      const data = await res.json();

      if (res.ok) {
        sessionStorage.setItem('orchid_verified_roll', roll);
        if (modalAlert) {
          modalAlert.style.display = 'block';
          modalAlert.style.background = 'rgba(25, 214, 140, 0.15)';
          modalAlert.style.border = '1px solid rgba(25, 214, 140, 0.4)';
          modalAlert.style.color = '#19D68C';
          modalAlert.innerHTML = `✓ Verified & Published! Your experience is live on Campus Pulse.`;
        }
        setTimeout(() => {
          closeCommunityModal();
          loadCommunityPosts();
        }, 1200);
      } else {
        if (modalAlert) {
          modalAlert.style.display = 'block';
          modalAlert.style.background = 'rgba(255, 77, 77, 0.15)';
          modalAlert.style.border = '1px solid rgba(255, 77, 77, 0.4)';
          modalAlert.style.color = '#ff5252';
          if (data.detail && data.detail.includes('Campus Anti-Troll Shield')) {
            modalAlert.innerHTML = `🛡️ <strong>Anti-Troll Shield Triggered:</strong> ${data.detail}`;
          } else {
            modalAlert.innerHTML = `⚠️ ${data.detail || 'Failed to publish post.'}`;
          }
        }
      }
    } catch (err) {
      if (modalAlert) {
        modalAlert.style.display = 'block';
        modalAlert.style.background = 'rgba(255, 77, 77, 0.15)';
        modalAlert.style.border = '1px solid rgba(255, 77, 77, 0.4)';
        modalAlert.style.color = '#ff5252';
        modalAlert.innerHTML = `⚠️ Connection error: ${err.message}`;
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>PUBLISH TO CAMPUS PULSE</span> <span>🚀</span>`;
      }
    }
  };

  // Initial check & load
  initChatGatewayState();
  loadCommunityPosts();
}

/* --------------------------------------------------------------------------
   16. ANTIGRAVITY / ZERO-G PHYSICS MODE (EASTER EGG)
   -------------------------------------------------------------------------- */
function initZeroGMode() {
  // Inject Zero-G Floating HUD Button if not present
  let btn = document.getElementById('zerog-toggle-btn');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'zerog-toggle-btn';
    btn.className = 'zerog-hud-btn';
    btn.setAttribute('aria-label', 'Toggle Zero-Gravity Physics Mode');
    btn.innerHTML = `<span class="zerog-icon">🚀</span> <span class="zerog-text">Zero-G: OFF</span>`;
    document.body.appendChild(btn);
  }

  let isZeroG = false;
  let animId = null;
  let mouseX = -9999;
  let mouseY = -9999;
  let elementsData = [];

  function onMouseMove(e) {
    mouseX = e.clientX;
    mouseY = e.clientY;
  }

  function getPhysicsTargets() {
    return Array.from(document.querySelectorAll(
      '.association-card, .showcase-card, .team-card, .quiz-card, .stat-card, .cta-box'
    ));
  }

  function startPhysicsLoop() {
    const targets = getPhysicsTargets();
    if (!targets.length) return;

    elementsData = targets.map((el, i) => ({
      el,
      speedY: 0.0012 + (i % 5) * 0.0003,
      speedX: 0.0009 + (i % 4) * 0.0002,
      ampY: 10 + (i % 4) * 3,
      ampX: 6 + (i % 3) * 2,
      phaseY: (i * 1.3) % (Math.PI * 2),
      phaseX: (i * 0.9) % (Math.PI * 2),
      deflectX: 0,
      deflectY: 0,
      currentX: 0,
      currentY: 0
    }));

    window.addEventListener('mousemove', onMouseMove);

    const startTime = performance.now();

    function frame(now) {
      const t = now - startTime;

      for (let i = 0; i < elementsData.length; i++) {
        const d = elementsData[i];
        const el = d.el;

        const driftY = Math.sin(t * d.speedY + d.phaseY) * d.ampY;
        const driftX = Math.cos(t * d.speedX + d.phaseX) * d.ampX;

        const rect = el.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;

        const dist = Math.hypot(mouseX - cx, mouseY - cy);
        const radius = 220;

        let targetDeflectX = 0;
        let targetDeflectY = 0;

        if (dist < radius && dist > 0) {
          const force = (1 - dist / radius) * 28;
          const angle = Math.atan2(cy - mouseY, cx - mouseX);
          targetDeflectX = Math.cos(angle) * force;
          targetDeflectY = Math.sin(angle) * force;
        }

        d.deflectX += (targetDeflectX - d.deflectX) * 0.08;
        d.deflectY += (targetDeflectY - d.deflectY) * 0.08;

        const posX = driftX + d.deflectX;
        const posY = driftY + d.deflectY;

        const rotX = (posY / 15) * -1;
        const rotY = (posX / 15);

        el.style.transform = `perspective(1000px) translate3d(${posX.toFixed(1)}px, ${posY.toFixed(1)}px, 15px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg)`;
      }

      animId = requestAnimationFrame(frame);
    }

    animId = requestAnimationFrame(frame);
  }

  function stopPhysicsLoop() {
    if (animId) {
      cancelAnimationFrame(animId);
      animId = null;
    }
    window.removeEventListener('mousemove', onMouseMove);

    const targets = getPhysicsTargets();
    targets.forEach(el => {
      el.classList.add('zero-g-returning');
      el.style.transform = '';
      setTimeout(() => {
        el.classList.remove('zero-g-returning');
      }, 650);
    });
    elementsData = [];
  }

  btn.addEventListener('click', () => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      alert('Zero-G physics mode is disabled because "Reduce Motion" is enabled in your system preferences.');
      return;
    }

    isZeroG = !isZeroG;

    if (isZeroG) {
      btn.classList.add('active');
      btn.innerHTML = `<span class="zerog-icon">🛸</span> <span class="zerog-text">Zero-G: ACTIVE</span>`;
      document.body.classList.add('zero-g-active');
      startPhysicsLoop();
    } else {
      btn.classList.remove('active');
      btn.innerHTML = `<span class="zerog-icon">🚀</span> <span class="zerog-text">Zero-G: OFF</span>`;
      document.body.classList.remove('zero-g-active');
      stopPhysicsLoop();
    }
  });
}

/* --------------------------------------------------------------------------
   16. LIVE BACKEND TELEMETRY & STATS
   -------------------------------------------------------------------------- */
async function initLiveTelemetry() {
  const counterEl = document.getElementById('live-members-counter');
  if (!counterEl) return;

  try {
    const res = await apiFetch('/api/stats');
    if (!res.ok) return;
    const data = await res.json();
    if (typeof data.total_registered_members === 'number') {
      const formatted = data.total_registered_members < 10 
        ? `0${data.total_registered_members}+` 
        : `${data.total_registered_members}+`;
      counterEl.textContent = formatted;
    }
  } catch (err) {
    // Non-blocking fallback
  }
}

/* --------------------------------------------------------------------------
   17. MASTER ADMIN CONTROL SUITE (AUTHENTICATION, EXPORT, BROADCAST, MODERATION)
   -------------------------------------------------------------------------- */
function initAdminConsole() {
  const overlay = document.getElementById('admin-modal-overlay');
  if (!overlay) return;

  const pinScreen = document.getElementById('admin-pin-screen');
  const suiteScreen = document.getElementById('admin-suite-screen');
  const pinInput = document.getElementById('admin-pin-input');
  const pinError = document.getElementById('admin-pin-error');
  const statusMsg = document.getElementById('admin-status-msg');

  let sessionAdminPin = sessionStorage.getItem('orchid_admin_pin') || '';
  let sessionAdminToken = sessionStorage.getItem('orchid_admin_token') || '';
  let allMembers = [];

  window.openAdminModal = function() {
    if (!overlay) {
      window.location.href = 'index.html?open=admin';
      return;
    }
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    if (statusMsg) statusMsg.style.display = 'none';

    if (sessionAdminPin || sessionAdminToken) {
      showAdminSuite();
    } else {
      showPinScreen();
    }
  };

  window.closeAdminModal = function() {
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  };

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      closeAdminModal();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.classList.contains('active')) {
      closeAdminModal();
    }
  });

  function showPinScreen() {
    if (pinScreen) pinScreen.style.display = 'block';
    if (suiteScreen) suiteScreen.style.display = 'none';
    if (pinInput) {
      pinInput.value = '';
      setTimeout(() => pinInput.focus(), 150);
    }
    if (pinError) pinError.style.display = 'none';
  }

  function showAdminSuite() {
    if (pinScreen) pinScreen.style.display = 'none';
    if (suiteScreen) suiteScreen.style.display = 'block';
    const badge = document.getElementById('admin-session-badge');
    if (badge && sessionAdminToken) {
      badge.style.display = 'inline-block';
      const sigPart = sessionAdminToken.split('.')[2];
      badge.textContent = `🔑 HMAC: ${sigPart ? sigPart.substring(0,8) : 'ACTIVE'}`;
    }
    loadAdminMembers();
    loadModerationPosts();
    loadAdminChatUsers();
    loadCurrentBroadcastIntoForm();
    loadExecutiveAnalytics();
    loadAdminSmtpConfig();
    if (typeof updateRejoinBadge === 'function') updateRejoinBadge();
  }

  window.submitAdminPin = async function() {
    const pin = (pinInput ? pinInput.value : '').trim();
    if (!pin) return;

    try {
      const res = await apiFetch('/api/admin/verify-pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: pin })
      });

      const data = await res.json();
      if (res.ok && data.valid) {
        sessionAdminPin = pin;
        sessionAdminToken = data.token || '';
        sessionStorage.setItem('orchid_admin_pin', pin);
        if (data.token) sessionStorage.setItem('orchid_admin_token', data.token);

        if (typeof playAudioTone === 'function') playAudioTone(880, 0.12, 'sine');
        showAdminSuite();
      } else {
        if (typeof playAudioTone === 'function') playAudioTone(240, 0.2, 'triangle');
        if (pinError) {
          pinError.style.display = 'block';
          pinError.textContent = data.detail || 'Invalid Master Security PIN. Access denied.';
        }
      }
    } catch (err) {
      if (pinError) {
        pinError.style.display = 'block';
        pinError.textContent = 'Server connection error.';
      }
    }
  };

  if (pinInput) {
    pinInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') submitAdminPin();
    });
  }

  window.lockAdminSuite = async function() {
    const token = sessionAdminToken || sessionStorage.getItem('orchid_admin_token') || '';
    if (token) {
      try {
        await apiFetch('/api/admin/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'X-Admin-Token': token }
        });
      } catch (err) {
        // Local lockout still proceeds if the server is temporarily unavailable.
      }
    }
    sessionAdminPin = '';
    sessionAdminToken = '';
    sessionStorage.removeItem('orchid_admin_pin');
    sessionStorage.removeItem('orchid_admin_token');
    const badge = document.getElementById('admin-session-badge');
    if (badge) badge.style.display = 'none';
    showPinScreen();
  };

  window.switchAdminTab = function(tabName) {
    document.querySelectorAll('.admin-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.admin-tab-pane').forEach(pane => pane.classList.remove('active'));

    const activeBtn = document.getElementById(`tab-btn-${tabName}`);
    const activePane = document.getElementById(`admin-tab-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');
    if (activePane) activePane.classList.add('active');

    if (tabName === 'members') loadAdminMembers();
    if (tabName === 'broadcast') loadCurrentBroadcastIntoForm();
    if (tabName === 'moderation') {
      loadModerationPosts();
      loadAdminChatUsers();
    }
    if (tabName === 'analytics') loadExecutiveAnalytics();
    if (tabName === 'audit') loadSecurityAuditLogs();
    if (tabName === 'smtp') loadAdminSmtpConfig();
    if (tabName === 'students') loadAdminStudents();
    if (tabName === 'rejoin') loadAdminRejoinRequests();
    if (tabName === 'events') loadAdminEvents();
  };

  // 1-Click Excel / CSV Export
  window.exportMembersCsv = async function() {
    if (!sessionAdminPin) return;
    try {
      const response = await apiFetch('/api/admin/export/members.csv', {
        headers: { 'X-Admin-Key': sessionAdminPin }
      });
      if (!response.ok) throw new Error('CSV export was rejected. Please verify your admin session.');
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = 'associationhub-members.csv';
      link.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      alert('Unable to export members: ' + error.message);
    }
  };

  // Member Management
  const listContainer = document.getElementById('admin-members-list');
  const countEl = document.getElementById('admin-member-count');
  const searchInput = document.getElementById('admin-search-input');
  const deptFilter = document.getElementById('admin-dept-filter');

  window.loadAdminMembers = async function() {
    if (!listContainer) return;
    listContainer.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--color-text-muted);">
        <span>Loading registered members from database...</span>
      </div>
    `;

    try {
      const res = await apiFetch('/api/admin/members', {
        headers: {
          'X-Admin-Key': sessionAdminPin || ''
        }
      });
      if (!res.ok) throw new Error('Failed to fetch members with admin credentials');
      const data = await res.json();
      allMembers = Array.isArray(data) ? data : (data.members || []);
      filterAdminMembers();
    } catch (err) {
      listContainer.innerHTML = `
        <div style="padding: 2rem; text-align: center; color: #ff5252;">
          ⚠️ Error loading members: ${err.message}
        </div>
      `;
    }
  };

  window.filterAdminMembers = function() {
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
    const dept = (deptFilter ? deptFilter.value : 'ALL');

    const filtered = allMembers.filter(m => {
      const matchDept = (dept === 'ALL' || m.association === dept);
      const matchQuery = !query || 
        (m.name && m.name.toLowerCase().includes(query)) ||
        (m.roll_no && m.roll_no.toLowerCase().includes(query)) ||
        (m.email && m.email.toLowerCase().includes(query)) ||
        (m.pass_id && m.pass_id.toLowerCase().includes(query)) ||
        (m.dept && m.dept.toLowerCase().includes(query));
      return matchDept && matchQuery;
    });

    renderAdminMembers(filtered);
  };

  function renderAdminMembers(members) {
    if (!listContainer) return;

    if (countEl) {
      countEl.textContent = `Showing ${members.length} of ${allMembers.length} registered member${allMembers.length === 1 ? '' : 's'}`;
    }

    if (members.length === 0) {
      listContainer.innerHTML = `
        <div style="padding: 3rem 1.5rem; text-align: center; color: var(--color-text-muted);">
          <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">🔍</div>
          <div>No registered members found matching your search.</div>
        </div>
      `;
      return;
    }

    listContainer.innerHTML = members.map(m => {
      const safeName = (m.name || '').replace(/'/g, "\\'");
      const isSuspended = (m.status === 'SUSPENDED');
      const statusBadge = isSuspended 
        ? `<span class="admin-badge admin-badge-status-suspended">SUSPENDED</span>`
        : `<span class="admin-badge admin-badge-status-active">ACTIVE</span>`;

      const toggleActionBtn = isSuspended
        ? `<button type="button" class="btn-success" onclick="toggleMemberStatus('${m.pass_id}', 'ACTIVE')" title="Reactivate pass"><span>Activate ▶️</span></button>`
        : `<button type="button" class="btn-warning" onclick="toggleMemberStatus('${m.pass_id}', 'SUSPENDED')" title="Suspend access at gate"><span>Suspend ⏸️</span></button>`;

      return `
        <div class="admin-member-row" id="admin-row-${m.pass_id}">
          <div class="admin-member-info">
            <div class="admin-member-name">
              <span>${m.name}</span>
              <span class="admin-badge admin-badge-assoc">${m.association}</span>
              <span class="admin-badge admin-badge-year">${m.year}</span>
              ${statusBadge}
            </div>
            <div class="admin-member-meta">
              <span><strong>Roll:</strong> ${m.roll_no}</span>
              <span><strong>Branch:</strong> ${m.dept}</span>
              <span><strong style="color:var(--brand-gold);">🔒 Gmail:</strong> <code style="color:#00e676;">${m.email || 'Not Recorded'}</code></span>
              <span><strong>Pass ID:</strong> <code>${m.pass_id}</code></span>
              <span><strong>Date:</strong> ${m.created_at || 'N/A'}</span>
            </div>
          </div>
          <div class="admin-actions">
            ${toggleActionBtn}
            <a href="verify.html?pass_id=${encodeURIComponent(m.pass_id)}" target="_blank" class="btn-outline-small" title="Open gate verification">
              <span>Verify 📱</span>
            </a>
            <button type="button" class="btn-danger" onclick="removeMember('${m.pass_id}', '${safeName}', '${m.roll_no}')" title="Revoke and delete member">
              <span>Remove 🗑️</span>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  window.toggleMemberStatus = async function(passId, newStatus) {
    try {
      const pin = sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || window.sessionAdminPin || '';
      const res = await apiFetch(`/api/admin/members/${encodeURIComponent(passId)}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Key': pin,
          'X-Admin-Pin': pin
        },
        body: JSON.stringify({ status: newStatus })
      });
      const data = await res.json();
      if (res.ok) {
        loadAdminMembers();
        if (typeof updateRejoinBadge === 'function') updateRejoinBadge();
      } else {
        alert("Failed to update status: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error contacting server: " + err.message);
    }
  };

  window.removeMember = async function(passId, name, rollNo) {
    if (!confirm(`Are you sure you want to permanently revoke and delete the membership for:

Student: ${name}
Roll No: ${rollNo}
Pass ID: ${passId}

This will remove the record from SQLite database associationhub.db.`)) {
      return;
    }

    try {
      const pin = sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || window.sessionAdminPin || '';
      const res = await apiFetch(`/api/memberships/${encodeURIComponent(passId)}`, {
        method: 'DELETE',
        headers: {
          'X-Admin-Key': pin,
          'X-Admin-Pin': pin
        }
      });
      const data = await res.json();

      if (res.ok) {
        if (statusMsg) {
          statusMsg.style.display = 'block';
          statusMsg.style.background = 'rgba(25, 214, 140, 0.15)';
          statusMsg.style.border = '1px solid rgba(25, 214, 140, 0.4)';
          statusMsg.style.color = '#19D68C';
          statusMsg.innerHTML = `✓ Successfully removed <strong>${name}</strong> (${passId}) from database.`;
          setTimeout(() => { if (statusMsg) statusMsg.style.display = 'none'; }, 4000);
        }
        if (typeof updateRejoinBadge === 'function') updateRejoinBadge();

        const row = document.getElementById(`admin-row-${passId}`);
        if (row) {
          row.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
          row.style.opacity = '0';
          row.style.transform = 'translateX(20px)';
          setTimeout(() => loadAdminMembers(), 300);
        } else {
          loadAdminMembers();
        }

        if (typeof initLiveTelemetry === 'function') initLiveTelemetry();
      } else {
        alert('Failed to remove member: ' + (data.detail || 'Server error'));
      }
    } catch (err) {
      alert('Error contacting server: ' + err.message);
    }
  };

  // Broadcast Announcement Form Loading & Updating
  async function loadCurrentBroadcastIntoForm() {
    try {
      const res = await apiFetch('/api/announcements/current');
      if (res.ok) {
        const data = await res.json();
        const tagInput = document.getElementById('broadcast-tag');
        const btnInput = document.getElementById('broadcast-btn-text');
        const msgInput = document.getElementById('broadcast-msg');
        if (tagInput) tagInput.value = data.tag || '📢 Campus Notice';
        if (btnInput) btnInput.value = data.button_text || 'Apply Now →';
        if (msgInput) msgInput.value = data.message || '';
      }
    } catch (err) {}
  }

  window.publishBroadcastAnnouncement = async function(event) {
    event.preventDefault();
    const tag = document.getElementById('broadcast-tag').value.trim();
    const btnText = document.getElementById('broadcast-btn-text').value.trim();
    const msg = document.getElementById('broadcast-msg').value.trim();

    try {
      const res = await apiFetch('/api/admin/announcements', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Key': sessionAdminPin
        },
        body: JSON.stringify({
          tag: tag,
          button_text: btnText,
          message: msg
        })
      });

      const data = await res.json();
      if (res.ok) {
        alert("Broadcast announcement published successfully to top banner!");
        if (typeof initAnnouncementBanner === 'function') initAnnouncementBanner();
      } else {
        alert("Failed to publish: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error contacting server: " + err.message);
    }
  };

  // Moderation
  const postsListContainer = document.getElementById('admin-posts-list');
  async function loadModerationPosts() {
    if (!postsListContainer) return;
    try {
      const res = await apiFetch('/api/community/posts');
      const data = await res.json();
      const posts = data.posts || [];
      if (posts.length === 0) {
        postsListContainer.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--color-text-muted);">No community posts to moderate.</div>`;
        return;
      }
      postsListContainer.innerHTML = posts.map(p => `
        <div class="admin-member-row" id="admin-post-row-${p.post_id}">
          <div class="admin-member-info">
            <div class="admin-member-name">
              <span>${p.title}</span>
              <span class="admin-badge admin-badge-assoc">${p.category}</span>
              ${p.is_anonymous ? '<span class="admin-badge admin-badge-year">ANONYMOUS</span>' : ''}
            </div>
            <div class="admin-member-meta">
              <span><strong>Author:</strong> ${p.author_name}</span>
              <span><strong>Date:</strong> ${p.created_at}</span>
              <span><strong>Likes:</strong> ${p.likes}</span>
              <span><strong>Comments:</strong> ${p.comment_count}</span>
            </div>
            <div style="font-size: 0.82rem; color: #a0aec0; margin-top: 0.25rem;">
              ${p.content.substring(0, 120)}...
            </div>
          </div>
          <div class="admin-actions">
            ${p.is_anonymous ? `
              <button type="button" class="btn-outline-small" onclick="adminUnmaskAuthor('${p.post_id}')" title="Confidential identity check">
                <span>Unmask 🕵️</span>
              </button>
            ` : ''}
            <button type="button" class="btn-danger" onclick="adminDeletePost('${p.post_id}')" title="Delete inappropriate post">
              <span>Delete 🗑️</span>
            </button>
          </div>
        </div>
      `).join('');
    } catch (err) {
      postsListContainer.innerHTML = `<div style="padding: 2rem; text-align: center; color: #ff5252;">Failed to load posts.</div>`;
    }
  }

  // Chat User Roster & Disciplinary Authorities (Admin Exclusive)
  const chatUsersContainer = document.getElementById('admin-chat-users-list');

  window.loadAdminChatUsers = async function() {
    if (!chatUsersContainer) return;
    chatUsersContainer.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: var(--color-text-muted);">
        <span>Loading verified chat users from database...</span>
      </div>
    `;

    try {
      const res = await apiFetch('/api/admin/chat/users', {
        headers: {
          'X-Admin-Key': sessionAdminPin || '',
          'X-Admin-Token': sessionAdminToken || sessionAdminPin || ''
        }
      });
      if (!res.ok) throw new Error('Failed to load chat users');
      const data = await res.json();
      const users = data.users || [];
      renderAdminChatUsers(users);
    } catch (err) {
      chatUsersContainer.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; color: #ff5252;">
          ⚠️ Error loading chat users: ${err.message}
        </div>
      `;
    }
  };

  function renderAdminChatUsers(users) {
    if (!chatUsersContainer) return;
    if (users.length === 0) {
      chatUsersContainer.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; color: var(--color-text-muted);">
          No verified chat users registered yet.
        </div>
      `;
      return;
    }

    chatUsersContainer.innerHTML = users.map(u => {
      const safeName = (u.name || '').replace(/'/g, "\\'");
      let statusBadge = '<span class="admin-badge admin-badge-status-active">ACTIVE</span>';
      if (u.status === 'MUTED') statusBadge = '<span class="admin-badge admin-badge-status-suspended" style="background:rgba(255, 179, 0, 0.2); color:#ffb300; border-color:#ffb300;">MUTED</span>';
      if (u.status === 'BANNED') statusBadge = '<span class="admin-badge admin-badge-status-suspended" style="background:rgba(255, 65, 108, 0.2); color:#ff416c; border-color:#ff416c;">BANNED</span>';

      let statusControls = '';
      if (u.status === 'ACTIVE') {
        statusControls = `
          <button type="button" class="btn-warning" onclick="updateChatUserStatus('${u.user_id}', 'MUTED')" title="Mute user from sending messages" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
            <span>Mute 🔇</span>
          </button>
          <button type="button" class="btn-danger" onclick="updateChatUserStatus('${u.user_id}', 'BANNED')" title="Ban user from entering chat" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
            <span>Ban ⛔</span>
          </button>
        `;
      } else if (u.status === 'MUTED') {
        statusControls = `
          <button type="button" class="btn-success" onclick="updateChatUserStatus('${u.user_id}', 'ACTIVE')" title="Unmute user" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
            <span>Unmute 🔊</span>
          </button>
          <button type="button" class="btn-danger" onclick="updateChatUserStatus('${u.user_id}', 'BANNED')" title="Ban user from chat" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
            <span>Ban ⛔</span>
          </button>
        `;
      } else if (u.status === 'BANNED') {
        statusControls = `
          <button type="button" class="btn-success" onclick="updateChatUserStatus('${u.user_id}', 'ACTIVE')" title="Reactivate & Unban" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
            <span>Unban ▶️</span>
          </button>
        `;
      }

      return `
        <div class="admin-member-row" id="admin-chat-user-${u.user_id}" style="margin-bottom: 0.75rem;">
          <div class="admin-member-info" style="flex: 1;">
            <div class="admin-member-name">
              <span>${u.name}</span>
              <span class="admin-badge admin-badge-assoc">${u.dept}</span>
              ${statusBadge}
            </div>
            <div class="admin-member-meta" style="margin-top: 0.35rem; display: flex; flex-wrap: wrap; gap: 0.75rem;">
              <span><strong>Roll:</strong> ${u.roll_no}</span>
              <span><strong style="color:var(--brand-gold);">🔒 Confidential Gmail:</strong> <code style="color:#00e676;">${u.email}</code></span>
              <span><strong>Last Active:</strong> ${u.last_active || u.created_at}</span>
            </div>
          </div>
          <div class="admin-actions" style="display: flex; gap: 0.4rem; align-items: center;">
            ${statusControls}
            <button type="button" class="btn-danger" onclick="deleteChatUser('${u.user_id}', '${safeName}')" title="Kick and remove user from registry" style="padding: 0.3rem 0.7rem; font-size: 0.75rem;">
              <span>Kick 🗑️</span>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  window.updateChatUserStatus = async function(userId, newStatus) {
    try {
      const res = await apiFetch(`/api/admin/chat/users/${encodeURIComponent(userId)}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Key': sessionAdminPin || '',
          'X-Admin-Token': sessionAdminToken || sessionAdminPin || ''
        },
        body: JSON.stringify({ status: newStatus })
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof showToast === 'function') showToast(`User status updated to ${newStatus}`, 'success');
        loadAdminChatUsers();
      } else {
        alert("Failed to update status: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  window.deleteChatUser = async function(userId, name) {
    if (!confirm(`Are you sure you want to kick and remove student ${name} from the community chat?`)) return;
    try {
      const res = await apiFetch(`/api/admin/chat/users/${encodeURIComponent(userId)}`, {
        method: 'DELETE',
        headers: {
          'X-Admin-Key': sessionAdminPin || '',
          'X-Admin-Token': sessionAdminToken || sessionAdminPin || ''
        }
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof showToast === 'function') showToast(`User ${name} kicked from chat`, 'info');
        loadAdminChatUsers();
      } else {
        alert("Failed to kick user: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  window.adminUnmaskAuthor = async function(postId) {
    try {
      const res = await apiFetch(`/api/admin/community/unmask/${encodeURIComponent(postId)}`, {
        headers: { 'X-Admin-Key': sessionAdminPin || '' }
      });
      const data = await res.json();
      if (res.ok) {
        alert(`CONFIDENTIAL UNMASK AUDIT:\n\nTitle: "${data.title}"\nTrue Student: ${data.true_student_name}\nRoll No / PRN: ${data.true_roll_no}\nVerified Gmail: ${data.verified_gmail || 'Not Recorded'}\nBranch: ${data.department}\nYear: ${data.year}\nTimestamp: ${data.timestamp}`);
      } else {
        alert("Failed to unmask: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  window.adminDeletePost = async function(postId) {
    if (!confirm("Are you sure you want to permanently delete this discussion thread and all replies?")) return;
    try {
      const res = await apiFetch(`/api/community/posts/${encodeURIComponent(postId)}`, {
        method: 'DELETE',
        headers: { 'X-Admin-Key': sessionAdminPin }
      });
      const data = await res.json();
      if (res.ok) {
        loadModerationPosts();
        if (typeof filterCommunityPosts === 'function') filterCommunityPosts('ALL');
      } else {
        alert("Delete failed: " + (data.detail || "Server error"));
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  // Executive Analytics Dashboard
  async function loadExecutiveAnalytics() {
    try {
      const res = await apiFetch('/api/stats');
      if (!res.ok) throw new Error('Failed to fetch statistics');
      const data = await res.json();

      const kpiMembers = document.getElementById('kpi-total-members');
      const kpiCheckins = document.getElementById('kpi-total-checkins');
      const kpiPosts = document.getElementById('kpi-total-posts');
      const kpiEvents = document.getElementById('kpi-total-events');
      const kpiHealth = document.getElementById('kpi-health-status');

      if (kpiMembers) kpiMembers.textContent = data.total_registered_members || 0;
      if (kpiCheckins) kpiCheckins.textContent = data.total_gate_checkins || 0;
      if (kpiPosts) kpiPosts.textContent = data.total_community_posts || 0;
      if (kpiEvents) kpiEvents.textContent = data.total_department_events || 5;
      if (kpiHealth) kpiHealth.textContent = data.status === 'operational' ? '100%' : 'Online';

      const chartBars = document.getElementById('admin-chart-bars');
      if (chartBars) {
        const byAssoc = data.members_by_association || {};
        const associations = ['CSESA', 'MESA', 'EESA', 'CESA', 'AEXS', 'AIESA'];
        const total = data.total_registered_members || 1;

        chartBars.innerHTML = associations.map(assoc => {
          const count = byAssoc[assoc] || 0;
          const pct = Math.round((count / (total || 1)) * 100);
          return `
            <div class="chart-bar-row">
              <span class="chart-bar-label">${assoc}</span>
              <div class="chart-bar-track">
                <div class="chart-bar-fill" style="width: ${pct}%;"></div>
              </div>
              <span class="chart-bar-val">${count} (${pct}%)</span>
            </div>
          `;
        }).join('');
      }
    } catch (err) {
      console.error('Error loading analytics:', err);
      const chartBars = document.getElementById('admin-chart-bars');
      if (chartBars) chartBars.innerHTML = `<div style="color:#ff5252; padding:1rem; text-align:center;">Failed to load analytics: ${err.message}</div>`;
    }
  }

  // Security Audit Logs
  window.loadSecurityAuditLogs = async function() {
    const container = document.getElementById('admin-audit-logs-list');
    if (!container) return;
    container.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--color-text-muted);"><span>Loading security audit ledger...</span></div>`;

    try {
      const authKey = sessionAdminToken || sessionAdminPin;
      const res = await apiFetch('/api/admin/audit-logs', {
        headers: { 'X-Admin-Token': authKey, 'X-Admin-Key': sessionAdminPin }
      });
      const data = await res.json();
      const logs = data.logs || [];

      if (logs.length === 0) {
        container.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--color-text-muted);">No security events logged yet.</div>`;
        return;
      }

      container.innerHTML = logs.map(l => {
        let tagColor = 'var(--brand-gold)';
        if (l.event_type.includes('SUCCESS') || l.event_type.includes('DISPATCHED')) tagColor = '#19D68C';
        if (l.event_type.includes('FAILED') || l.event_type.includes('DENIED') || l.event_type.includes('PURGED') || l.event_type.includes('DELETED')) tagColor = '#FF416C';

        return `
          <div class="admin-member-row" style="align-items: center;">
            <div class="admin-member-info" style="flex: 1;">
              <div class="admin-member-name">
                <span style="font-family: var(--font-mono); font-size: 0.85rem; color: ${tagColor}; font-weight: 700;">[${l.event_type}]</span>
                <span style="font-size: 0.88rem; color: #FFFFFF;">${l.details}</span>
              </div>
              <div class="admin-member-meta" style="margin-top: 0.35rem;">
                <span><strong>Timestamp:</strong> ${l.timestamp}</span>
                <span><strong>Actor IP:</strong> <code>${l.actor_ip || 'Internal'}</code></span>
              </div>
            </div>
            <span style="font-size: 0.75rem; background: rgba(255,255,255,0.06); padding: 0.2rem 0.5rem; border-radius: 4px; font-family: var(--font-mono); color: var(--color-text-muted);">#${l.id}</span>
          </div>
        `;
      }).join('');
    } catch (err) {
      container.innerHTML = `<div style="padding: 2rem; text-align: center; color: #ff5252;">⚠️ Error loading audit logs: ${err.message}</div>`;
    }
  };

  // Real SMTP Mailer Configuration Handlers
  window.loadAdminSmtpConfig = async function() {
    const statusCard = document.getElementById('admin-smtp-status-card');
    const indicator = document.getElementById('smtp-status-indicator');
    const title = document.getElementById('smtp-status-title');
    const subtitle = document.getElementById('smtp-status-subtitle');

    try {
      const res = await apiFetch('/api/admin/smtp-config', {
        headers: {
          'X-Admin-Key': sessionAdminPin || '',
          'X-Admin-Token': sessionAdminToken || sessionAdminPin || ''
        }
      });
      if (!res.ok) throw new Error('Failed to fetch SMTP configuration');
      const data = await res.json();

      if (data.configured) {
        if (indicator) indicator.style.background = '#00e676';
        if (title) title.innerHTML = `🟢 Live Gmail SMTP Active &bull; <span style="font-family:var(--font-mono); color:var(--brand-gold);">${data.user}</span>`;
        if (subtitle) subtitle.textContent = `Real-time OTP delivery is active via ${data.host}:${data.port}. Credentials are configured on the server.`;
        if (statusCard) {
          statusCard.style.background = 'rgba(0, 230, 118, 0.08)';
          statusCard.style.border = '1px solid rgba(0, 230, 118, 0.3)';
        }
      } else {
        if (indicator) indicator.style.background = '#ff9800';
        if (title) title.textContent = '🟡 SMTP is not configured';
        if (subtitle) subtitle.textContent = 'OTP email delivery is unavailable. Configure SMTP_USER and SMTP_PASSWORD in the server environment and restart the backend.';
        if (statusCard) {
          statusCard.style.background = 'rgba(229, 169, 60, 0.08)';
          statusCard.style.border = '1px solid var(--color-border-subtle)';
        }
      }
    } catch (err) {
      if (title) title.textContent = '⚠️ Unable to query SMTP status';
      if (subtitle) subtitle.textContent = err.message;
    }
  };

  window.testAdminSmtpEmail = async function() {
    const testInput = document.getElementById('smtp-test-email');
    const msgEl = document.getElementById('smtp-test-msg');
    const testBtn = document.getElementById('btn-test-smtp');
    const email = (testInput ? testInput.value : '').trim().toLowerCase();

    if (!email || !email.includes('@')) {
      alert('Please enter a recipient email address to receive the test email.');
      if (testInput) testInput.focus();
      return;
    }

    if (testBtn) {
      testBtn.disabled = true;
      testBtn.innerHTML = '<span>Sending live email... ⏳</span>';
    }
    if (msgEl) {
      msgEl.style.display = 'block';
      msgEl.style.color = 'var(--brand-gold)';
      msgEl.style.background = 'rgba(229, 169, 60, 0.1)';
      msgEl.textContent = 'Connecting to Gmail SMTP and transmitting test message...';
    }

    try {
      const res = await apiFetch('/api/admin/smtp-test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Key': sessionAdminPin || '',
          'X-Admin-Token': sessionAdminToken || sessionAdminPin || ''
        },
        body: JSON.stringify({ test_email: email })
      });
      const data = await res.json();

      if (res.ok) {
        if (msgEl) {
          msgEl.style.color = '#00e676';
          msgEl.style.background = 'rgba(0, 230, 118, 0.12)';
          msgEl.innerHTML = `✓ <strong>Success!</strong> ${data.message}`;
        }
        if (typeof showToast === 'function') showToast(`Test email successfully delivered to ${email}!`, 'success');
      } else {
        if (msgEl) {
          msgEl.style.color = '#ff5252';
          msgEl.style.background = 'rgba(255, 65, 108, 0.12)';
          msgEl.innerHTML = `⚠️ <strong>Delivery Failed:</strong> ${data.detail || 'Error transmitting test email.'}`;
        }
      }
    } catch (err) {
      if (msgEl) {
        msgEl.style.color = '#ff5252';
        msgEl.style.background = 'rgba(255, 65, 108, 0.12)';
        msgEl.textContent = 'Connection error: ' + err.message;
      }
    } finally {
      if (testBtn) {
        testBtn.disabled = false;
        testBtn.innerHTML = '<span>Send Test Email ✉️</span>';
      }
    }
  };
}

/* --------------------------------------------------------------------------
   18. SPOTLIGHT QUICK COMMAND SEARCH (CTRL + K)
   -------------------------------------------------------------------------- */
function initSpotlightSearch() {
  const overlay = document.getElementById('spotlight-overlay');
  const input = document.getElementById('spotlight-input');
  const resultsContainer = document.getElementById('spotlight-results');
  if (!overlay || !input || !resultsContainer) return;

  const searchCatalog = [
    { title: 'CSESA — Computer Science & Engg', desc: 'Hackathons, coding workshops, HackOrchid Codefest marathon', url: 'cep-cesa.html', category: 'Department Chapter', icon: '💻' },
    { title: 'MESA — Mechanical Engg Students', desc: 'SAE BAJA Racing Arena, CAD/CAM drafting, MechaFest expo', url: 'cep-mesa.html', category: 'Department Chapter', icon: '🏎️' },
    { title: 'EESA — Electrical Engg Students', desc: 'Smart Grid, Solar Energy, EV power drives, Vidyut expo', url: 'esa.html', category: 'Department Chapter', icon: '⚡' },
    { title: 'CESA — Civil Engg Students', desc: 'Bridge-Craft, concrete structural load testing, Nirman symposium', url: 'civil.html', category: 'Department Chapter', icon: '🌉' },
    { title: 'AEXS — Electronics & Telecom', desc: 'Embedded IoT, STM32 robotics, LoRa wireless sensors, ElectroWave', url: 'entc.html', category: 'Department Chapter', icon: '📡' },
    { title: 'AIESA — AI & Data Science', desc: 'Neural intelligence, vision hub, Datathon, transformers, deep learning', url: 'aids.html', category: 'Department Chapter', icon: '🧠' },
    { title: 'Apply for Club Membership Pass', desc: 'Official student intake & dynamic 3D holographic digital pass', action: 'openMembershipModal', category: 'Action', icon: '📝' },
    { title: 'Campus Pulse — Student Discussions', desc: 'Verified peer interview guidance, hackathon stories & placement tips', url: '#community', category: 'Community', icon: '💬' },
    { title: 'Share Your Experience on Campus Pulse', desc: 'Post interview guidance or project tips for fellow Orchidites', action: 'openCommunityModal', category: 'Action', icon: '🚀' },
    { title: 'QR Gate Pass Check-In & Verification', desc: 'Cryptographic public check-in scanner for gate & symposium entry', url: 'verify.html', category: 'Security & Verification', icon: '📱' },
    { title: 'Master Admin Command Center', desc: 'PIN-protected member roster, CSV export, live broadcasts, and executive analytics', action: 'openAdminModal', category: 'Coordinator Tool', icon: '⚙️' },
    { title: 'Upcoming Events & Technical Fests', desc: 'Hackathons, auto expos, robotics arenas across 6 departments', url: '#events', category: 'Events', icon: '📅' },
    { title: 'Interactive Club Discovery Quiz', desc: 'Find your best engineering association match in 30 seconds', url: '#quiz', category: 'Interactive', icon: '🎯' },
    { title: 'Freshers FAQs', desc: 'Everything you need to know about joining NKOCET associations', url: '#faq', category: 'Help', icon: '❓' },
    { title: 'About the Project & Team', desc: '2nd Year B.Tech 3rd Semester CEP Initiative information and creators', url: 'cep-about us.html', category: 'About', icon: '👥' }
  ];

  let selectedIndex = 0;
  let currentMatches = [...searchCatalog];

  window.openSpotlightSearch = function() {
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    input.value = '';
    renderResults(searchCatalog);
    if (typeof playAudioTone === 'function') playAudioTone(920, 0.06, 'sine');
    setTimeout(() => input.focus(), 80);
  };

  window.closeSpotlightSearch = function() {
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  };

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeSpotlightSearch();
  });

  document.addEventListener('keydown', (e) => {
    // Open on Ctrl+K or Cmd+K
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (overlay.classList.contains('active')) {
        closeSpotlightSearch();
      } else {
        openSpotlightSearch();
      }
      return;
    }

    if (!overlay.classList.contains('active')) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      closeSpotlightSearch();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (currentMatches.length === 0) return;
      selectedIndex = (selectedIndex + 1) % currentMatches.length;
      updateHighlight();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (currentMatches.length === 0) return;
      selectedIndex = (selectedIndex - 1 + currentMatches.length) % currentMatches.length;
      updateHighlight();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (currentMatches[selectedIndex]) {
        executeItem(currentMatches[selectedIndex]);
      }
    }
  });

  input.addEventListener('input', () => {
    const query = input.value.toLowerCase().trim();
    if (!query) {
      currentMatches = [...searchCatalog];
    } else {
      currentMatches = searchCatalog.filter(item =>
        item.title.toLowerCase().includes(query) ||
        item.desc.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query)
      );
    }
    selectedIndex = 0;
    renderResults(currentMatches);
  });

  function renderResults(items) {
    if (items.length === 0) {
      resultsContainer.innerHTML = `
        <div style="padding: 2.5rem; text-align: center; color: var(--color-text-muted);">
          <div style="font-size: 2rem; margin-bottom: 0.5rem;">🔍</div>
          <div>No matching commands, departments, or actions found.</div>
        </div>
      `;
      return;
    }

    resultsContainer.innerHTML = items.map((item, idx) => `
      <div class="spotlight-item ${idx === selectedIndex ? 'selected' : ''}" data-idx="${idx}" onclick="selectSpotlightItem(${idx})">
        <div style="display: flex; align-items: center; gap: 0.85rem;">
          <span style="font-size: 1.25rem;">${item.icon}</span>
          <div>
            <div style="font-weight: 700; color: #FFFFFF; font-size: 0.92rem;">${item.title}</div>
            <div style="font-size: 0.78rem; color: var(--color-text-muted); margin-top: 0.15rem;">${item.desc}</div>
          </div>
        </div>
        <span style="font-size: 0.72rem; background: rgba(255, 255, 255, 0.08); padding: 0.2rem 0.55rem; border-radius: 4px; color: var(--brand-gold); font-family: var(--font-mono); white-space: nowrap;">${item.category}</span>
      </div>
    `).join('');
  }

  function updateHighlight() {
    const items = resultsContainer.querySelectorAll('.spotlight-item');
    items.forEach((el, idx) => {
      if (idx === selectedIndex) {
        el.classList.add('selected');
        el.scrollIntoView({ block: 'nearest' });
      } else {
        el.classList.remove('selected');
      }
    });
  }

  window.selectSpotlightItem = function(idx) {
    if (currentMatches[idx]) {
      executeItem(currentMatches[idx]);
    }
  };

  function executeItem(item) {
    closeSpotlightSearch();
    if (item.action && typeof window[item.action] === 'function') {
      window[item.action]();
    } else if (item.url) {
      if (item.url.startsWith('#')) {
        const target = document.querySelector(item.url);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth' });
        }
      } else {
        window.location.href = item.url;
      }
    }
  }
}

// STUDENT REGISTRATION

(function initStudentRegistrationSystem() {
  let studentOtpTimer = null;
  let studentCooldownTimer = null;
  let pendingStudentData = null;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function showAlert(alertElId, message, type = 'error') {
    const alertEl = document.getElementById(alertElId);
    if (!alertEl) return;
    alertEl.style.display = 'block';
    if (type === 'error') {
      alertEl.style.background = 'rgba(255, 65, 108, 0.12)';
      alertEl.style.border = '1px solid #FF416C';
      alertEl.style.color = '#ff809b';
    } else if (type === 'success') {
      alertEl.style.background = 'rgba(25, 214, 140, 0.12)';
      alertEl.style.border = '1px solid #19D68C';
      alertEl.style.color = '#19D68C';
    } else {
      alertEl.style.background = 'rgba(229, 169, 60, 0.12)';
      alertEl.style.border = '1px solid #E5A93C';
      alertEl.style.color = '#E5A93C';
    }
    alertEl.innerHTML = message;
  }

  function hideAlert(alertElId) {
    const alertEl = document.getElementById(alertElId);
    if (alertEl) alertEl.style.display = 'none';
  }

  // Open Modal
  window.openStudentRegisterModal = function() {
    const overlay = document.getElementById('student-register-modal-overlay');
    if (!overlay) return;
    
    // Reset to step 1 if not mid-verification
    if (!pendingStudentData) {
      document.getElementById('student-reg-step-1').style.display = 'block';
      document.getElementById('student-reg-step-2').style.display = 'none';
      document.getElementById('student-reg-step-3').style.display = 'none';
      hideAlert('student-reg-alert-1');
      hideAlert('student-reg-alert-2');
    }

    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  };

  // Close Modal
  window.closeStudentRegisterModal = function() {
    const overlay = document.getElementById('student-register-modal-overlay');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
  };

  // Back to Form
  window.backToStudentRegForm = function() {
    document.getElementById('student-reg-step-1').style.display = 'block';
    document.getElementById('student-reg-step-2').style.display = 'none';
    hideAlert('student-reg-alert-1');
  };

  // Setup paste & input handlers for 6-digit OTP input
  document.addEventListener('DOMContentLoaded', () => {
    const otpInput = document.getElementById('student-reg-otp');
    if (otpInput) {
      otpInput.addEventListener('paste', (e) => {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData).getData('text');
        const digits = (pasted || '').replace(/\D/g, '').slice(0, 6);
        otpInput.value = digits;
        if (digits.length === 6) {
          showAlert('student-reg-alert-2', '📋 6-Digit OTP pasted! Click "Verify OTP & Complete Registration".', 'gold');
        }
      });

      otpInput.addEventListener('input', (e) => {
        otpInput.value = otpInput.value.replace(/\D/g, '').slice(0, 6);
      });

      otpInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          window.handleStudentRegVerifyAndComplete();
        }
      });
    }

    // Close modal on click outside
    const overlay = document.getElementById('student-register-modal-overlay');
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          window.closeStudentRegisterModal();
        }
      });
    }
  });

  // Direct student registration
  window.handleStudentRegistration = async function(event) {
    if (event) event.preventDefault();

    const name = (document.getElementById('student-reg-name')?.value || '').trim();
    const roll = (document.getElementById('student-reg-roll')?.value || '').trim();
    const email = (document.getElementById('student-reg-email')?.value || '').trim().toLowerCase();
    const dept = (document.getElementById('student-reg-dept')?.value || '').trim();
    const password = document.getElementById('student-reg-password')?.value || '';
    const confirmPassword = document.getElementById('student-reg-confirm-password')?.value || '';
    const submitBtn = document.getElementById('btn-student-register');

    hideAlert('student-reg-alert-1');

    if (!name || !roll || !email || !dept || !password) {
      showAlert('student-reg-alert-1', '⚠️ Please complete all required registration fields.');
      return;
    }

    if (!email.includes('@') || !email.includes('.')) {
      showAlert('student-reg-alert-1', '⚠️ Please enter a valid student Gmail address.');
      return;
    }

    if (password.length < 6) {
      showAlert('student-reg-alert-1', '⚠️ Password must be at least 6 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      showAlert('student-reg-alert-1', '⚠️ Password Mismatch: Password and Confirm Password do not match.');
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Creating Student Account... ⏳</span>';
    }

    try {
      const res = await apiFetch('/api/student/register/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          roll_no: roll,
          email,
          dept,
          password
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showAlert('student-reg-alert-1', `⚠️ ${escapeHtml(data.detail || 'Could not complete registration.')}`);
        return;
      }

      document.getElementById('student-reg-step-1').style.display = 'none';
      document.getElementById('student-reg-step-3').style.display = 'block';
      document.getElementById('success-student-id').textContent = data.student_id;
      document.getElementById('success-student-name').textContent = data.full_name;
      document.getElementById('success-student-email').textContent = data.email;
      document.getElementById('success-student-roll').textContent = data.roll_no;
      document.getElementById('success-student-dept').textContent = data.dept;
      document.getElementById('success-student-verified-at').textContent = data.email_verified_at || '-';
      document.getElementById('success-student-created-at').textContent = data.created_at || '-';
      document.getElementById('student-registration-form')?.reset();
    } catch (err) {
      showAlert('student-reg-alert-1', `⚠️ Connection error: ${escapeHtml(err.message)}`);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Create Student Account</span><span>→</span>';
      }
    }
  };

  // Keep the legacy function name from older cached frontends from reaching the OTP flow.
  window.handleStudentSendOtp = window.handleStudentRegistration;

  
// Admin Registered Students Loader
  window.loadAdminStudents = async function() {
    const tbody = document.getElementById('admin-students-tbody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: var(--color-text-secondary);">Loading registered students...</td></tr>`;

    try {
      const res = await apiFetch('/api/admin/students', {
        headers: {
          'X-Admin-Pin': (window.sessionAdminPin || '')
        }
      });
      const data = await res.json();
      if (typeof updateRejoinBadge === 'function') updateRejoinBadge();
      if (!res.ok) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 1.5rem; color: #ff5252;">${escapeHtml(data.detail || 'Failed to load students')}</td></tr>`;
        return;
      }

      if (!data.students || data.students.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: var(--color-text-secondary);">No registered students found yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.students.map(s => {
        const isBlocked = s.status === 'BLOCKED';
        const isSuspended = s.status === 'SUSPENDED';
        
        let statusBadge = `<span style="color: #19D68C; font-weight: 700; font-size: 0.75rem; background: rgba(25, 214, 140, 0.1); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(25, 214, 140, 0.3);">ACTIVE</span>`;
        if (isBlocked) {
          statusBadge = `<span style="color: #ff5252; font-weight: 700; font-size: 0.75rem; background: rgba(255, 82, 82, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(255, 82, 82, 0.4);">🚫 BLOCKED</span>`;
        } else if (isSuspended) {
          statusBadge = `<span style="color: #ff9800; font-weight: 700; font-size: 0.75rem; background: rgba(255, 152, 0, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(255, 152, 0, 0.4);">⏸️ SUSPENDED</span>`;
        }

        const blockBtn = isBlocked
          ? `<button type="button" class="btn-secondary" onclick="toggleStudentStatus('${s.student_id}', 'ACTIVE')" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; color: #19D68C; border-color: rgba(25,214,140,0.4);" title="Unblock Student">✅ Unblock</button>`
          : `<button type="button" class="btn-secondary" onclick="toggleStudentStatus('${s.student_id}', 'BLOCKED')" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; color: #ff5252; border-color: rgba(255,82,82,0.4);" title="Block Student from Site & OTP">🚫 Block</button>`;

        const deleteBtn = `<button type="button" class="btn-secondary" onclick="deleteStudentAccount('${s.student_id}', '${escapeHtml(s.full_name)}')" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; color: #ef4444; border-color: rgba(239,68,68,0.4);" title="Permanently Delete Student Record">🗑️ Remove</button>`;

        return `
          <tr style="${isBlocked ? 'opacity: 0.75; background: rgba(255, 65, 108, 0.05);' : ''}">
            <td><span style="font-family: var(--font-mono); font-weight: 700; color: #19D68C; font-size: 0.8rem;">${escapeHtml(s.student_id)}</span></td>
            <td><strong>${escapeHtml(s.full_name)}</strong></td>
            <td><span style="font-family: var(--font-mono); font-size: 0.82rem;">${escapeHtml(s.roll_no)}</span></td>
            <td><span style="font-size: 0.82rem;">${escapeHtml(s.dept)}</span></td>
            <td><code style="color: #64b5f6; font-size: 0.82rem; font-weight: 600;">${escapeHtml(s.email)}</code></td>
            <td><span style="color: #19D68C; font-weight: 700; font-size: 0.76rem; background: rgba(25, 214, 140, 0.12); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(25, 214, 140, 0.3);">✅ VERIFIED</span></td>
            <td>${statusBadge}</td>
            <td><span style="font-family: var(--font-mono); font-size: 0.78rem; color: #94a3b8;">${escapeHtml(s.email_verified_at || '-')}</span></td>
            <td>
              <div style="display: flex; gap: 0.4rem; align-items: center;">
                ${blockBtn}
                ${deleteBtn}
              </div>
            </td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 1.5rem; color: #ff5252;">Error contacting server: ${escapeHtml(err.message)}</td></tr>`;
    }
  };

  // Administrator Authority: Toggle Status (Block / Unblock)
  window.toggleStudentStatus = async function(studentId, newStatus) {
    const actionLabel = newStatus === 'BLOCKED' ? 'BLOCK' : 'UNBLOCK';
    if (!confirm(`Are you sure you want to ${actionLabel} student account (${studentId})?`)) {
      return;
    }

    try {
      const res = await apiFetch(`/api/admin/students/${encodeURIComponent(studentId)}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Pin': (window.sessionAdminPin || '')
        },
        body: JSON.stringify({ status: newStatus })
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Action Failed: ' + (data.detail || 'Could not update student status.'));
        return;
      }
      if (typeof showToast === 'function') {
        showToast(data.message || `Student status updated to ${newStatus}`, newStatus === 'BLOCKED' ? 'red' : 'green');
      }
      loadAdminStudents();
      if (typeof updateRejoinBadge === 'function') updateRejoinBadge();
    } catch (err) {
      alert('Error updating student: ' + err.message);
    }
  };

  // Administrator Authority: Permanently Delete Student Account
  window.deleteStudentAccount = async function(studentId, studentName) {
    if (!confirm(`⚠️ DANGER: Permanently delete student account for "${studentName}" (${studentId})?\n\nThis will completely purge their record and reset their verification.`)) {
      return;
    }

    try {
      const res = await apiFetch(`/api/admin/students/${encodeURIComponent(studentId)}`, {
        method: 'DELETE',
        headers: {
          'X-Admin-Pin': (window.sessionAdminPin || '')
        }
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Delete Failed: ' + (data.detail || 'Could not delete student.'));
        return;
      }
      if (typeof showToast === 'function') {
        showToast(`🗑️ ${data.message || 'Student account removed.'}`, 'red');
      }
      loadAdminStudents();
      if (typeof updateRejoinBadge === 'function') updateRejoinBadge();
    } catch (err) {
      alert('Error deleting student: ' + err.message);
    }
  };

  // Administrator Authority: Export Registry as CSV
  window.exportStudentsCsv = function() {
    const pin = window.sessionAdminPin || '';
    apiFetch('/api/admin/export/students.csv', {
      headers: { 'X-Admin-Pin': pin }
    })
    .then(resp => {
      if (!resp.ok) throw new Error('Export failed');
      return resp.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `NKOCET_Verified_Students_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      if (typeof showToast === 'function') {
        showToast('📥 Student Registry CSV Downloaded!', 'green');
      }
    })
    .catch(err => alert('Export failed: ' + err.message));
  };

  // Administrator Authority: Update Rejoin Approvals Count Badge
  window.updateRejoinBadge = async function() {
    const badge = document.getElementById('admin-rejoin-count-badge');
    if (!badge) return;
    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch('/api/admin/rejoin-requests', {
        headers: { 'X-Admin-Pin': pin }
      });
      if (!res.ok) return;
      const data = await res.json();
      const pendingCount = data.pending_count || 0;
      if (pendingCount > 0) {
        badge.textContent = pendingCount;
        badge.style.display = 'inline-block';
      } else {
        badge.textContent = '0';
        badge.style.display = 'none';
      }
    } catch (e) {
      // Quiet fail for badge polling
    }
  };

  // Administrator Authority: Load Rejoin Approvals Queue
  window.loadAdminRejoinRequests = async function() {
    const tbody = document.getElementById('admin-rejoin-tbody');
    const badge = document.getElementById('admin-rejoin-count-badge');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--color-text-secondary);">Loading rejoining approval queue...</td></tr>`;

    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch('/api/admin/rejoin-requests', {
        headers: {
          'X-Admin-Pin': pin
        }
      });
      const data = await res.json();
      if (!res.ok) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 1.5rem; color: #ff5252;">${escapeHtml(data.detail || 'Failed to load rejoin queue')}</td></tr>`;
        return;
      }

      const pendingCount = data.pending_count || 0;
      if (badge) {
        if (pendingCount > 0) {
          badge.textContent = pendingCount;
          badge.style.display = 'inline-block';
        } else {
          badge.textContent = '0';
          badge.style.display = 'none';
        }
      }

      if (!data.requests || data.requests.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2.5rem; color: #19D68C; font-weight: 600;">✓ No banned or restricted students in queue. Registry is completely clean!</td></tr>`;
        return;
      }

      tbody.innerHTML = data.requests.map(r => {
        const isPending = r.status === 'REJOIN_PENDING';
        const isApproved = r.status === 'REJOIN_APPROVED';
        const isRestricted = r.status === 'RESTRICTED';

        let statusBadge = '';
        if (isPending) {
          statusBadge = `<span style="color: #ff9800; font-weight: 700; font-size: 0.75rem; background: rgba(255, 152, 0, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(255, 152, 0, 0.4);">⏳ REJOIN PENDING</span>`;
        } else if (isApproved) {
          statusBadge = `<span style="color: #19D68C; font-weight: 700; font-size: 0.75rem; background: rgba(25, 214, 140, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(25, 214, 140, 0.4);">✅ APPROVED</span>`;
        } else {
          statusBadge = `<span style="color: #ff5252; font-weight: 700; font-size: 0.75rem; background: rgba(255, 82, 82, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid rgba(255, 82, 82, 0.4);">🚫 RESTRICTED</span>`;
        }

        const actions = isApproved
          ? `<span style="color: #19D68C; font-size: 0.76rem; font-weight: 700;">✓ Authorized by Admin</span>`
          : `
            <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
              <button type="button" class="btn-primary" onclick="approveRejoinRequest(${r.id}, '${escapeHtml(r.name || r.email)}')" style="padding: 0.28rem 0.65rem; font-size: 0.75rem; background: #19D68C; color: #000; font-weight: 700; border: none; border-radius: 4px; cursor: pointer;" title="Grant permission to rejoin">
                ✅ Approve
              </button>
              <button type="button" class="btn-secondary" onclick="rejectRejoinRequest(${r.id}, '${escapeHtml(r.name || r.email)}')" style="padding: 0.28rem 0.65rem; font-size: 0.75rem; color: #ff5252; border-color: rgba(255,82,82,0.4); border-radius: 4px; cursor: pointer;" title="Keep account restricted">
                ❌ Keep Blocked
              </button>
            </div>
          `;

        const rowBg = isPending 
          ? 'background: rgba(255, 152, 0, 0.08);' 
          : (isApproved ? 'background: rgba(25, 214, 140, 0.04);' : 'background: rgba(255, 82, 82, 0.04);');

        return `
          <tr style="${rowBg}">
            <td><strong>${escapeHtml(r.name || 'Student')}</strong></td>
            <td><span style="font-family: var(--font-mono); font-size: 0.82rem;">${escapeHtml(r.roll_no || 'N/A')}</span></td>
            <td><code style="color: #64b5f6; font-size: 0.82rem; font-weight: 600;">${escapeHtml(r.email)}</code></td>
            <td><span style="font-size: 0.8rem; color: #cbd5e1;">${escapeHtml(r.reason || 'Restricted by Administrator')}</span></td>
            <td><span style="font-family: var(--font-mono); font-size: 0.76rem; color: #94a3b8;">${escapeHtml(r.restricted_at || '-')}</span></td>
            <td>${statusBadge}</td>
            <td><span style="font-family: var(--font-mono); font-size: 0.76rem; color: ${isPending ? '#ff9800' : '#94a3b8'};">${escapeHtml(r.rejoin_requested_at || 'Not requested')}</span></td>
            <td>${actions}</td>
          </tr>
        `;
      }).join('');

    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 1.5rem; color: #ff5252;">Error contacting server: ${escapeHtml(err.message)}</td></tr>`;
    }
  };

  // Administrator Authority: Approve Rejoin Request
  window.approveRejoinRequest = async function(requestId, studentName) {
    if (!confirm(`Are you sure you want to APPROVE rejoining for "${studentName}"?\n\nThis will remove their restriction and allow them to register, receive Gmail OTPs, and join clubs & community.`)) {
      return;
    }

    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch(`/api/admin/rejoin-requests/${requestId}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Pin': pin
        }
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Approval Failed: ' + (data.detail || 'Could not approve rejoin request.'));
        return;
      }
      if (typeof showToast === 'function') {
        showToast(data.message || `Rejoin approved for ${studentName}!`, 'green');
      }
      loadAdminRejoinRequests();
      if (typeof loadAdminStudents === 'function') loadAdminStudents();
      if (typeof loadAdminMembers === 'function') loadAdminMembers();
    } catch (err) {
      alert('Error approving rejoin: ' + err.message);
    }
  };

  // Administrator Authority: Reject Rejoin Request (Keep Restricted)
  window.rejectRejoinRequest = async function(requestId, studentName) {
    if (!confirm(`Keep "${studentName}" RESTRICTED?\n\nTheir rejoin request will be rejected and they will remain blocked from OTP and registration.`)) {
      return;
    }

    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch(`/api/admin/rejoin-requests/${requestId}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Pin': pin
        }
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Rejection Failed: ' + (data.detail || 'Could not reject rejoin request.'));
        return;
      }
      if (typeof showToast === 'function') {
        showToast(data.message || `Account remains restricted for ${studentName}.`, 'gold');
      }
      loadAdminRejoinRequests();
    } catch (err) {
      alert('Error rejecting rejoin: ' + err.message);
    }
  };

  // --------------------------------------------------------------------------
  // Tab 9: Campus Events Management
  // --------------------------------------------------------------------------
  window.loadAdminEvents = async function() {
    const listEl = document.getElementById('admin-events-list');
    if (!listEl) return;
    listEl.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--color-text-secondary);">Loading collegiate events schedule...</div>`;

    try {
      const res = await apiFetch('/api/events');
      const data = await res.json();
      const events = data.events || [];

      if (events.length === 0) {
        listEl.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--color-text-muted); background: rgba(8, 10, 15, 0.4); border-radius: var(--radius-md); border: 1px dashed var(--color-border-subtle);">
          <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📅</div>
          <h4 style="color: #fff; font-size: 1rem; margin-bottom: 0.25rem;">No Events Scheduled Yet</h4>
          <p style="font-size: 0.85rem; color: var(--color-text-muted);">Use the form above to schedule a collegiate hackathon or workshop.</p>
        </div>`;
        return;
      }

      listEl.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">
          ${events.map(ev => `
            <div style="background: rgba(13, 18, 32, 0.6); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between;">
              <div>
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                  <span style="display: inline-block; background: rgba(229, 169, 60, 0.15); color: var(--brand-gold); border: 1px solid var(--brand-gold); border-radius: 4px; padding: 0.2rem 0.55rem; font-size: 0.75rem; font-weight: 700;">
                    ${escapeHtml(ev.association)}
                  </span>
                  <span style="font-size: 0.75rem; color: #19D68C; font-family: var(--font-mono); background: rgba(25, 214, 140, 0.1); padding: 0.2rem 0.5rem; border-radius: 4px;">
                    ${escapeHtml(ev.category)}
                  </span>
                </div>
                <h4 style="color: #fff; font-size: 1rem; margin: 0 0 0.4rem 0;">${escapeHtml(ev.title)}</h4>
                <div style="font-size: 0.8rem; color: var(--color-text-secondary); margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.4rem;">
                  <span>🗓️</span>
                  <span>${escapeHtml(ev.date_str)}</span>
                </div>
                <p style="font-size: 0.84rem; color: var(--color-text-muted); line-height: 1.5; margin: 0;">
                  ${escapeHtml(ev.description)}
                </p>
              </div>
              <div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(255, 255, 255, 0.06); display: flex; justify-content: flex-end;">
                <button type="button" class="btn-danger" onclick="deleteAdminEvent(${ev.id}, '${escapeHtml(ev.title)}')" style="padding: 0.35rem 0.85rem; font-size: 0.78rem;">
                  <span>🗑️ Delete Event</span>
                </button>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    } catch (err) {
      listEl.innerHTML = `<div style="padding: 1.5rem; text-align: center; color: #ff5252;">Error loading events: ${escapeHtml(err.message)}</div>`;
    }
  };

  window.handleCreateAdminEvent = async function(e) {
    if (e) e.preventDefault();
    const title = (document.getElementById('admin-event-title')?.value || '').trim();
    const assoc = (document.getElementById('admin-event-assoc')?.value || '').trim();
    const dateStr = (document.getElementById('admin-event-date')?.value || '').trim();
    const cat = (document.getElementById('admin-event-cat')?.value || '').trim();
    const desc = (document.getElementById('admin-event-desc')?.value || '').trim();
    const alertEl = document.getElementById('admin-events-alert');
    const submitBtn = document.getElementById('btn-admin-add-event');

    if (!title || !assoc || !dateStr || !cat || !desc) {
      if (alertEl) {
        alertEl.style.display = 'block';
        alertEl.style.background = 'rgba(255, 65, 108, 0.15)';
        alertEl.style.color = '#ff5252';
        alertEl.textContent = 'Please fill out all required event fields.';
      }
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Publishing to Campus Schedule... ⏳</span>`;
    }

    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch('/api/admin/events', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Pin': pin
        },
        body: JSON.stringify({
          title: title,
          association: assoc,
          date_str: dateStr,
          category: cat,
          description: desc
        })
      });
      const data = await res.json();
      if (!res.ok) {
        if (alertEl) {
          alertEl.style.display = 'block';
          alertEl.style.background = 'rgba(255, 65, 108, 0.15)';
          alertEl.style.color = '#ff5252';
          alertEl.textContent = data.detail || 'Failed to publish event to calendar.';
        }
        return;
      }

      if (alertEl) {
        alertEl.style.display = 'block';
        alertEl.style.background = 'rgba(25, 214, 140, 0.15)';
        alertEl.style.color = '#19D68C';
        alertEl.textContent = `🚀 ${data.message || 'Event published successfully!'}`;
      }

      // Reset form
      document.getElementById('admin-event-title').value = '';
      document.getElementById('admin-event-date').value = '';
      document.getElementById('admin-event-cat').value = '';
      document.getElementById('admin-event-desc').value = '';

      loadAdminEvents();
      if (typeof loadExecutiveAnalytics === 'function') loadExecutiveAnalytics();
      if (typeof showToast === 'function') showToast('Event published to collegiate calendar!', 'success');
    } catch (err) {
      if (alertEl) {
        alertEl.style.display = 'block';
        alertEl.style.background = 'rgba(255, 65, 108, 0.15)';
        alertEl.style.color = '#ff5252';
        alertEl.textContent = 'Network error: ' + err.message;
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>Publish Event to Campus Calendar 🚀</span>`;
      }
    }
  };

  window.deleteAdminEvent = async function(eventId, title) {
    if (!confirm(`Remove event "${title}" from the active campus schedule?\n\nThis will remove it from all collegiate portals and the live event calendar.`)) return;

    try {
      const pin = window.sessionAdminPin || sessionStorage.getItem('orchid_admin_pin') || '';
      const res = await apiFetch(`/api/admin/events/${eventId}`, {
        method: 'DELETE',
        headers: {
          'X-Admin-Pin': pin
        }
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Delete Event Failed: ' + (data.detail || 'Could not delete event from schedule.'));
        return;
      }
      if (typeof showToast === 'function') {
        showToast(data.message || 'Event removed from calendar.', 'gold');
      }
      loadAdminEvents();
      if (typeof loadExecutiveAnalytics === 'function') loadExecutiveAnalytics();
    } catch (err) {
      alert('Error removing event: ' + err.message);
    }
  };

})();
