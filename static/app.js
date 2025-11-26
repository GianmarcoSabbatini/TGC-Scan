// TCG Scan - Main JavaScript Application
// WebSocket connection and shared utilities

// Initialize WebSocket connection
const socket = io('http://localhost:5000');

socket.on('connect', () => {
    console.log('Connected to TCG Scan server');
    updateConnectionStatus(true);
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    updateConnectionStatus(false);
});

socket.on('card_scanned', (data) => {
    console.log('Card scanned:', data);
    showNotification(`Card scanned: ${data.card.name}`, 'success');
});

socket.on('batch_progress', (data) => {
    console.log('Batch progress:', data);
});

socket.on('sorting_complete', (data) => {
    console.log('Sorting complete:', data);
    showNotification(`Sorting complete: ${data.total_cards} cards sorted`, 'success');
});

socket.on('import_progress', (data) => {
    console.log('Import progress:', data);
});

function updateConnectionStatus(connected) {
    const wsStatus = document.getElementById('wsStatus');
    if (wsStatus) {
        if (connected) {
            wsStatus.className = 'badge badge-success';
            wsStatus.textContent = '● WebSocket Connected';
        } else {
            wsStatus.className = 'badge badge-error';
            wsStatus.textContent = '● WebSocket Disconnected';
        }
    }
}

// Notification system
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: var(--spacing-md) var(--spacing-lg);
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-lg);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;

    const colors = {
        success: 'var(--success)',
        error: 'var(--error)',
        warning: 'var(--warning)',
        info: 'var(--info)'
    };

    notification.innerHTML = `
        <div style="display: flex; align-items: center; gap: var(--spacing-md);">
            <div style="width: 4px; height: 40px; background: ${colors[type]}; border-radius: var(--radius-sm);"></div>
            <div>${message}</div>
        </div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Export window.socket for use in other scripts
window.socket = socket;
window.showNotification = showNotification;
