document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const menuToggle = document.getElementById('menu-toggle');
    const navMenu = document.getElementById('nav-menu');
    const navLinks = document.querySelectorAll('.nav-link');

    if (menuToggle && navMenu) {
        menuToggle.addEventListener('click', () => {
            menuToggle.classList.toggle('active');
            navMenu.classList.toggle('active');
            
            // Toggle body scroll to prevent scrolling when menu is open
            if (navMenu.classList.contains('active')) {
                document.body.style.overflow = 'hidden';
            } else {
                document.body.style.overflow = '';
            }
        });

        // Close menu when clicking a link
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                menuToggle.classList.remove('active');
                navMenu.classList.remove('active');
                document.body.style.overflow = '';
            });
        });
    }

    // 2. Navbar Style Change on Scroll
    const navbar = document.getElementById('navbar');
    
    const handleScroll = () => {
        if (window.scrollY > 20) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    };

    window.addEventListener('scroll', handleScroll);
    // Initial call in case page starts scrolled
    handleScroll();

    // 3. Scroll Spy (Active nav link on scroll)
    const sections = document.querySelectorAll('section[id]');
    
    const scrollSpy = () => {
        const scrollPosition = window.scrollY + 100; // offset for navbar height

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');
            
            if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
                navLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${sectionId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    };

    window.addEventListener('scroll', scrollSpy);

    // 4. Download Buttons Micro-interaction
    const downloadBtns = document.querySelectorAll('.download-btn');
    
    downloadBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // We won't block the download link navigation, just show a temporary feedback state
            const originalHTML = btn.innerHTML;
            
            // Temporary loading state
            btn.style.pointerEvents = 'none';
            btn.innerHTML = `
                <svg class="icon spin" viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="2" x2="12" y2="6"></line>
                    <line x1="12" y1="18" x2="12" y2="22"></line>
                    <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                    <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                    <line x1="2" y1="12" x2="6" y2="12"></line>
                    <line x1="18" y1="12" x2="22" y2="12"></line>
                    <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                    <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                </svg>
                Iniciando Descarga...
            `;
            
            // Add spin animation dynamically if not present
            if (!document.getElementById('spin-style')) {
                const style = document.createElement('style');
                style.id = 'spin-style';
                style.innerHTML = `
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    .spin {
                        animation: spin 1s linear infinite;
                    }
                `;
                document.head.appendChild(style);
            }

            setTimeout(() => {
                btn.innerHTML = `
                    <svg class="icon" viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    ¡Descargado!
                `;
                
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.style.pointerEvents = 'auto';
                }, 2000);
            }, 1500);
        });
    });

    // 5. Scroll Reveal Animation for Cards
    const revealElements = document.querySelectorAll('.app-card, .feature-card, .step-card');
    
    const revealOnScroll = () => {
        const triggerBottom = window.innerHeight * 0.85;
        
        revealElements.forEach(el => {
            const elTop = el.getBoundingClientRect().top;
            
            if (elTop < triggerBottom) {
                el.classList.add('revealed');
            }
        });
    };

    // Set initial classes for reveal animation
    revealElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
    });

    // Dynamic style rules for revealed cards
    const styleReveal = document.createElement('style');
    styleReveal.innerHTML = `
        .app-card.revealed, .feature-card.revealed, .step-card.revealed {
            opacity: 1 !important;
            transform: translateY(0) !important;
        }
    `;
    document.head.appendChild(styleReveal);

    window.addEventListener('scroll', revealOnScroll);
    // Initial check on load
    setTimeout(revealOnScroll, 100);

    // 6. Dynamic Changelog / Updates System
    const updatesData = [
        {
            version: "v3.0.0",
            date: "Julio 2026",
            title: "Lanzamiento Unificado (MXP Suite v3.0.0)",
            changes: [
                { type: "new", text: "<strong>Fusión de Suite Completa:</strong> MXP Downloader, Converter y Compressor unificados en un único ejecutable optimizado." },
                { type: "new", text: "<strong>Compresor Integrado:</strong> Sección dedicada a la reducción de tamaño de videos (presets WhatsApp/Discord), audio e imágenes." },
                { type: "optimize", text: "<strong>Reducción drástica de Peso:</strong> Exclusión de módulos redundantes y eliminación de ffprobe, bajando el ZIP final de 139 MB a solo 78.4 MB." },
                { type: "optimize", text: "<strong>Descargas en Paralelo:</strong> Soporte para descargar hasta 3 videos concurrentemente con barra de progreso amarilla individual." },
                { type: "fix", text: "<strong>Estabilidad y Caché:</strong> Corrección del parpadeo con URLs inválidas y guardado persistente de miniaturas." }
            ]
        },
        {
            version: "v2.0.0",
            date: "Julio 2026",
            title: "Lanzamiento Inicial (MXP Suite Beta)",
            changes: [
                { type: "new", text: "<strong>Conversión local por lotes:</strong> Soporte inicial para cambiar de formato videos y audios de manera rápida y privada." },
                { type: "new", text: "<strong>Tratamiento Drag & Drop:</strong> Arrastra archivos locales a la ventana de la app para agregarlos a la cola de trabajo." }
            ]
        },
        {
            version: "v1.8.0",
            date: "Mayo 2026",
            title: "Mejoras de Estabilidad en Downloader",
            changes: [
                { type: "new", text: "<strong>Extracción local de Audio:</strong> Convierte videos descargados a MP3/WAV de alta fidelidad directamente en la suite." },
                { type: "optimize", text: "<strong>Control de descargas individuales:</strong> Botón ✕ al lado de cada tarea para abortar descargas sin parar las demás." },
                { type: "fix", text: "<strong>Detección de plataformas:</strong> Corrección en el parser de enlaces de TikTok e Instagram Reels." }
            ]
        }
    ];

    const changelogNav = document.getElementById('changelog-nav');
    const changelogDisplay = document.getElementById('changelog-display');

    if (changelogNav && changelogDisplay) {
        let activeVersion = updatesData[0].version;
        let autoplayTimer = null;
        let isHovered = false;

        const renderChangelog = () => {
            // Render navigation buttons
            changelogNav.innerHTML = updatesData.map(item => `
                <button class="changelog-tab ${item.version === activeVersion ? 'active' : ''}" data-version="${item.version}">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <span class="changelog-tab-ver">${item.version}</span>
                        ${item.version === 'v3.0.0' ? '<span class="latest-badge" style="background: var(--accent-yellow); color: var(--bg-main); font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 800; text-transform: uppercase; font-family: inherit; box-shadow: 0 0 8px rgba(255, 230, 0, 0.4);">Actual</span>' : ''}
                    </div>
                    <span class="changelog-tab-date">${item.date}</span>
                </button>
            `).join('');

            // Get active version details
            const data = updatesData.find(item => item.version === activeVersion);

            // Render display card
            changelogDisplay.innerHTML = `
                <div class="changelog-header">
                    <h3 class="changelog-title">${data.title}</h3>
                    <span class="changelog-date">${data.date}</span>
                </div>
                <ul class="changelog-list">
                    ${data.changes.map(c => `
                        <li class="changelog-item">
                            <span class="changelog-badge ${c.type}">${c.type === 'new' ? 'Nuevo' : c.type === 'optimize' ? 'Optimiz' : 'Fix'}</span>
                            <span class="changelog-text">${c.text}</span>
                        </li>
                    `).join('')}
                </ul>
            `;

            // Bind click events to tabs
            const tabs = document.querySelectorAll('.changelog-tab');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    const selectedVer = tab.getAttribute('data-version');
                    if (selectedVer !== activeVersion) {
                        activeVersion = selectedVer;
                        changelogDisplay.classList.add('switching');
                        setTimeout(() => {
                            renderChangelog();
                            changelogDisplay.classList.remove('switching');
                        }, 200);
                        // Reset automatic transition timer on manual user interaction
                        startAutoplay();
                    }
                });
            });
        };

        const startAutoplay = () => {
            stopAutoplay();
            autoplayTimer = setInterval(() => {
                if (isHovered) return;
                const currentIndex = updatesData.findIndex(item => item.version === activeVersion);
                const nextIndex = (currentIndex + 1) % updatesData.length;
                activeVersion = updatesData[nextIndex].version;
                
                changelogDisplay.classList.add('switching');
                setTimeout(() => {
                    renderChangelog();
                    changelogDisplay.classList.remove('switching');
                }, 200);
            }, 5000); // Cycles every 5 seconds
        };

        const stopAutoplay = () => {
            if (autoplayTimer) {
                clearInterval(autoplayTimer);
                autoplayTimer = null;
            }
        };

        // Pause autoplay on hover of the changelog section
        const changelogSection = document.querySelector('.changelog-container');
        if (changelogSection) {
            changelogSection.addEventListener('mouseenter', () => {
                isHovered = true;
            });
            changelogSection.addEventListener('mouseleave', () => {
                isHovered = false;
            });
        }

        // Initial render & timer start
        renderChangelog();
        startAutoplay();
    }
});
