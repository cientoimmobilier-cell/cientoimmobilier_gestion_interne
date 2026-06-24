document.addEventListener('DOMContentLoaded', function() {
    // Bouton de masquage/affichage de la sidebar
    const sidebarCollapse = document.getElementById('sidebarCollapse');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    
    if (sidebarCollapse && sidebar) {
        sidebarCollapse.addEventListener('click', function() {
            sidebar.classList.toggle('active');
            if (overlay) {
                overlay.classList.toggle('active');
            }
        });
    }

    // Fermer la sidebar en cliquant sur l'overlay
    if (overlay) {
        overlay.addEventListener('click', function() {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        });
    }

    // Fermer la sidebar sur mobile en cliquant sur un lien
    const sidebarLinks = document.querySelectorAll('#sidebar ul li a');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth < 992) {
                sidebar.classList.remove('active');
                if (overlay) {
                    overlay.classList.remove('active');
                }
            }
        });
    });

    // Auto-disparition des messages d'alerte Flask après 5 secondes
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            // Utilisation d'une transition en douceur si possible
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(function() {
                alert.remove();
            }, 500);
        }, 5000);
    });

    // Prévisualisation d'image pour l'upload de photos
    const photoInput = document.getElementById('photo-input');
    const photoPreview = document.getElementById('photo-preview');
    
    if (photoInput && photoPreview) {
        photoInput.addEventListener('change', function() {
            photoPreview.innerHTML = '';
            const files = this.files;
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const imgWrapper = document.createElement('div');
                        imgWrapper.className = 'position-relative m-2 d-inline-block';
                        imgWrapper.style.width = '100px';
                        imgWrapper.style.height = '100px';
                        
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.className = 'img-thumbnail w-100 h-100';
                        img.style.objectFit = 'cover';
                        
                        imgWrapper.appendChild(img);
                        photoPreview.appendChild(imgWrapper);
                    };
                    reader.readAsDataURL(file);
                }
            }
        });
    }
});
