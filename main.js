let activeTab = 'dashboard', audioCtx = null, soundCooldown = 0, chart1 = null, chart2 = null;

document.addEventListener("DOMContentLoaded", () => {
    // Tab switching
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            document.querySelectorAll(".nav-item, .tab-pane").forEach(el => el.classList.remove("active"));
            item.classList.add("active");
            document.getElementById(`tab-${item.dataset.tab}`).classList.add("active");
            activeTab = item.dataset.tab;
            if (activeTab === 'logs') loadLogs(true);
            else if (activeTab === 'analytics') loadStats();
            else if (activeTab === 'settings') loadSettings();
        });
    });

    // Slider controls syncing
    const sliders = {
        safety_threshold: [document.getElementById("range-safety-limit"), document.getElementById("val-safety-limit"), " m"],
        warning_threshold: [document.getElementById("range-warning-limit"), document.getElementById("val-warning-limit"), " m"],
        focal_length_factor: [document.getElementById("range-camera-factor"), document.getElementById("val-camera-factor"), "x"]
    };

    Object.entries(sliders).forEach(([key, [el, valEl, suffix]]) => {
        el.addEventListener("input", () => {
            valEl.textContent = el.value + suffix;
        });
        el.addEventListener("change", () => {
            fetch("/api/settings", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ [key]: el.value })
            });
        });
    });

    // Form settings submission
    document.getElementById("settings-details-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const activeClasses = Array.from(document.querySelectorAll("input[name='active-class-cb']:checked")).map(cb => cb.value);
        fetch("/api/settings", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                safety_threshold: document.getElementById("input-safety-threshold").value,
                warning_threshold: document.getElementById("input-warning-threshold").value,
                focal_length_factor: document.getElementById("input-focal-factor").value,
                min_confidence: document.getElementById("input-min-confidence").value,
                active_classes: activeClasses.join(",")
            })
        }).then(() => alert("Settings saved."));
    });

    // Video uploads & switching
    const select = document.getElementById("video-source-select");
    select.addEventListener("change", () => {
        const opt = select.options[select.selectedIndex];
        fetch("/api/change_source", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_id: opt.value, path: opt.dataset.path })
        }).then(() => document.getElementById("video-stream-img").src = "/video_feed?t=" + Date.now());
    });

    const fileInput = document.getElementById("video-file-input");
    document.getElementById("upload-trigger-btn").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
        if (!fileInput.files.length) return;
        const fd = new FormData();
        fd.append("file", fileInput.files[0]);

        const prog = document.getElementById("upload-progress-container");
        const fill = document.getElementById("upload-progress-fill");
        const text = document.getElementById("upload-percentage");

        prog.classList.remove("hide");
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/upload_video", true);
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                fill.style.width = pct + "%";
                text.textContent = pct + "%";
            }
        };
        xhr.onload = () => {
            prog.classList.add("hide");
            if (xhr.status === 200) {
                loadSources();
                document.getElementById("video-stream-img").src = "/video_feed?t=" + Date.now();
                alert("Upload success. Processing video feed.");
            } else alert("Upload error.");
        };
        xhr.send(fd);
    });

    // Clear logs button
    document.getElementById("clear-logs-btn").addEventListener("click", () => {
        if (confirm("Reset safety logs?")) {
            fetch("/api/logs/clear", { method: "POST" }).then(() => {
                loadLogs(false);
                if (activeTab === 'logs') loadLogs(true);
            });
        }
    });

    // Bell alerts
    document.getElementById("global-alert-bell").addEventListener("click", () => {
        document.getElementById("alert-count-badge").classList.add("hide");
        document.querySelector("[data-tab='logs']").click();
    });

    // Initial setups
    loadSources();
    loadLogs(false);

    // Telemetry polling loop
    setInterval(() => {
        fetch("/api/active_alert")
            .then(res => res.json())
            .then(data => updateUI(data))
            .catch(() => { });
    }, 450);

    // Modal click backdrop handler
    document.getElementById("modal-backdrop-el").onclick = () => document.getElementById("snapshot-modal").classList.add("hide");
    document.getElementById("modal-close-btn").onclick = () => document.getElementById("snapshot-modal").classList.add("hide");
});

// Settings loader
function loadSettings() {
    fetch("/api/settings").then(res => res.json()).then(s => {
        document.getElementById("range-safety-limit").value = s.safety_threshold;
        document.getElementById("val-safety-limit").textContent = s.safety_threshold + " m";
        document.getElementById("range-warning-limit").value = s.warning_threshold;
        document.getElementById("val-warning-limit").textContent = s.warning_threshold + " m";
        document.getElementById("range-camera-factor").value = s.focal_length_factor;
        document.getElementById("val-camera-factor").textContent = s.focal_length_factor + "x";

        document.getElementById("input-safety-threshold").value = s.safety_threshold;
        document.getElementById("input-warning-threshold").value = s.warning_threshold;
        document.getElementById("input-focal-factor").value = s.focal_length_factor;
        document.getElementById("input-min-confidence").value = s.min_confidence;

        const classes = s.active_classes.split(",");
        document.querySelectorAll("input[name='active-class-cb']").forEach(cb => {
            cb.checked = classes.includes(cb.value);
        });
    });
}

// Fetch sources list
function loadSources() {
    fetch("/api/video_sources").then(res => res.json()).then(data => {
        const select = document.getElementById("video-source-select");
        select.innerHTML = "";
        data.sources.forEach(src => {
            const opt = document.createElement("option");
            opt.value = src.id;
            opt.textContent = src.name;
            opt.dataset.path = src.path;
            if (data.current === src.path || (src.id === "webcam" && data.current === "webcam")) opt.selected = true;
            select.appendChild(opt);
        });
    });
}

// Synthesizer logic
function playSound(severity) {
    if (!document.getElementById("toggle-sound-alert").checked) return;
    const now = Date.now();
    if (now - soundCooldown < 1500) return;
    soundCooldown = now;

    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();

        const osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
        osc.connect(gain); gain.connect(audioCtx.destination);

        if (severity === 'CRITICAL') {
            osc.type = 'sawtooth'; osc.frequency.setValueAtTime(950, audioCtx.currentTime);
            gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25);
            osc.start(); osc.stop(audioCtx.currentTime + 0.25);
        } else {
            osc.type = 'sine'; osc.frequency.setValueAtTime(520, audioCtx.currentTime);
            gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
            osc.start(); osc.stop(audioCtx.currentTime + 0.3);
        }
    } catch (e) { }
}

// UI updates on telemetry poll
function updateUI(data) {
    document.getElementById("active-targets-count").textContent = data.objects.length;
    let closest = 999, closestName = "";
    data.objects.forEach(o => {
        if (o.distance < closest) { closest = o.distance; closestName = o.class; }
    });
    document.getElementById("closest-target-distance").textContent = closest < 999 ? `${closest.toFixed(1)}m (${closestName})` : "- m";

    const statusEl = document.getElementById("zone-status-text");
    const banner = document.getElementById("dashboard-alert-banner");
    const flash = document.getElementById("danger-flash-border");

    if (data.alert) {
        statusEl.className = "value " + (data.severity === 'CRITICAL' ? 'red-text' : 'orange-text');
        statusEl.textContent = data.severity;
        playSound(data.severity);

        flash.className = `critical-overlay-flash ${data.severity === 'CRITICAL' ? 'alert-border-flash' : ''}`;
        banner.className = `banner-alert-msg ${data.severity.toLowerCase()}`;
        banner.innerHTML = `<div class="banner-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
            <div class="banner-text"><strong>${data.severity}: Object in Safety Zone</strong><span>${data.message}</span></div>`;

        document.getElementById("alert-count-badge").classList.remove("hide");
        loadLogs(false);
    } else {
        statusEl.className = "value green-text"; statusEl.textContent = "CLEAR";
        flash.className = "critical-overlay-flash hide";
        banner.className = "banner-alert-msg clear";
        banner.innerHTML = `<div class="banner-icon"><i class="fa-solid fa-circle-check"></i></div>
            <div class="banner-text"><strong>Safety Zone clear</strong><span>No hazards inside path.</span></div>`;
    }

    const tbody = document.getElementById("active-targets-tbody");
    if (!data.objects.length) tbody.innerHTML = `<tr><td colspan="4" class="no-data">Scanning safety zones...</td></tr>`;
    else {
        tbody.innerHTML = data.objects.map(o => `
            <tr>
                <td><strong>${o.class}</strong></td>
                <td>${o.distance.toFixed(1)}m</td>
                <td><span class="badge-boolean ${o.in_lane}">${o.in_lane ? 'LANE' : 'SIDE'}</span></td>
                <td><span class="badge-status ${o.status.toLowerCase()}">${o.status}</span></td>
            </tr>
        `).join('');
    }
}

// Logs fetching and showing inside dashboard and logs tab
function loadLogs(fullTab = false) {
    const severity = fullTab ? document.getElementById("filter-severity").value : "";
    const name = fullTab ? document.getElementById("filter-class").value : "";
    const limit = fullTab ? 50 : 5;

    let url = `/api/logs?limit=${limit}`;
    if (severity) url += `&severity=${severity}`;
    if (name) url += `&class=${name}`;

    fetch(url).then(res => res.json()).then(logs => {
        const tbody = document.getElementById(fullTab ? "full-logs-tbody" : "logs-tbody");
        if (!logs.length) {
            tbody.innerHTML = `<tr><td colspan="${fullTab ? 6 : 5}" class="no-data">No logs recorded.</td></tr>`;
            return;
        }
        tbody.innerHTML = logs.map(l => `
            <tr>
                ${fullTab ? `<td>#${l.id}</td>` : ''}
                <td>${l.timestamp.split(' ')[1] || l.timestamp}</td>
                <td><strong>${l.object_type}</strong></td>
                <td>${l.distance}m</td>
                <td><span class="badge-status ${l.severity.toLowerCase()}">${l.severity}</span></td>
                <td>${l.snapshot_path ? `<img src="/static/${l.snapshot_path}" class="snapshot-thumbnail" onclick="viewSnapshot('${l.snapshot_path}','${l.object_type}',${l.distance})">` : '-'}</td>
            </tr>
        `).join('');
    });
}

function viewSnapshot(path, cl, dist) {
    document.getElementById("modal-image-view").src = `/static/${path}`;
    document.getElementById("modal-subtitle").textContent = `${cl.toUpperCase()} logged at ${dist}m`;
    document.getElementById("snapshot-modal").classList.remove("hide");
}

// Analytics and statistical graphs loader
function loadStats() {
    fetch("/api/stats").then(res => res.json()).then(data => {
        document.getElementById("stats-total-breaches").textContent = data.total_logs;
        document.getElementById("stats-average-distance").textContent = data.avg_distance + " m";
        document.getElementById("stats-min-distance").textContent = data.min_distance + " m";

        const classes = Object.keys(data.objects), count = Object.values(data.objects);
        if (chart1) chart1.destroy();
        chart1 = new Chart(document.getElementById("chart-object-distribution").getContext("2d"), {
            type: 'bar',
            data: {
                labels: classes,
                datasets: [{ label: 'Breaches', data: count, backgroundColor: '#6366f1', borderRadius: 4 }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });

        const categories = Object.keys(data.severities), values = Object.values(data.severities);
        if (chart2) chart2.destroy();
        chart2 = new Chart(document.getElementById("chart-severity-levels").getContext("2d"), {
            type: 'doughnut',
            data: {
                labels: categories,
                datasets: [{ data: values, backgroundColor: ['#f43f5e', '#f97316'] }]
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: '70%' }
        });
    });
}

// Filter triggers on all logs pane
function refreshFullLogsList() { loadLogs(true); }
document.getElementById("filter-severity").onchange = refreshFullLogsList;
document.getElementById("filter-class").onchange = refreshFullLogsList;
document.getElementById("filter-clear-all").onclick = () => {
    document.getElementById("filter-severity").value = "";
    document.getElementById("filter-class").value = "";
    loadLogs(true);
};
