/* Vigil — minimal JavaScript */

// Auto-refresh dashboard every 30s if a run is in progress
if (window.location.pathname === '/') {
    setInterval(() => {
        fetch('/api/runs')
            .then(r => r.json())
            .then(runs => {
                const hasRunning = runs.some(r => r.avg_score === null);
                if (hasRunning) {
                    window.location.reload();
                }
            })
            .catch(() => {});
    }, 30000);
}
