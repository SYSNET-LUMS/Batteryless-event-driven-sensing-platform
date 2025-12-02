// Global Variables
let map;
let bins = [];
let trucks = [];
let depots = [];
let simulationInterval;
let simulationTime = 0;
let simulationSpeed = 1;
let isSimulationRunning = false;
let selectedItem = null;
let collectionsToday = 0;
let displayedTrafficTime = "07:00";
let displayedTrafficDensity = 1.0;
let displayedTrafficLevel = "Light";

// New global variables for GPT decisions
let gptDecisions = null;
let allRoutes = null;
let isSystemAnalyzed = false;

// Route visualization
let routePolylines = new Map(); // Store all route polylines for clearing

// Configuration from backend
let simulationStartHour = 7; // Default value, will be fetched from backend

// Backend API configuration
const API_BASE = 'http://localhost:5001/api';

// ---------- Small utilities (keep near top for reuse) ----------
// Convert simulation seconds to a clock string based on simulationStartHour.
// If withSeconds is true, returns HH:MM:SS else HH:MM
function formatSimTime(simSeconds, withSeconds = false) {
    const actual = simSeconds + (simulationStartHour * 3600);
    const h = Math.floor(actual / 3600) % 24;
    const m = Math.floor((actual % 3600) / 60);
    const s = Math.floor(actual % 60);
    const hh = h.toString().padStart(2, '0');
    const mm = m.toString().padStart(2, '0');
    if (!withSeconds) return `${hh}:${mm}`;
    const ss = s.toString().padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
}

// Compute remaining wait minutes given an absolute wait-until time and current sim time
function getWaitRemainingMinutes(waitUntil, currentTime) {
    return Math.max(0, Math.ceil((waitUntil - currentTime) / 60));
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function () {
    initializeMap();
    initializeControls();
    initializeModal();
    initializeScheduling();
    initializeBackend();
    updateStats();
    // Initialize time display immediately
    updateSimulationTime();
});

const ITEM_CONFIGS = {
    bin: {
        icon: '🗑️',
        color: '#27ae60',
        size: [25, 30],
        defaultValues: {
            fillLevel: 20,
            capacity: 500,
            fillRate: 3.5,
            threshold: 80
        },
        getStatusColor: function (bin) {
            if (bin.fillLevel >= 90) return '#e74c3c'; // urgent
            if (bin.fillLevel >= 70) return '#f39c12'; // warning
            if (bin.fillLevel >= 50) return '#f1c40f'; // moderate
            return '#27ae60'; // normal
        }
    },
    truck: {
        icon: '🚛',
        color: '#3498db',
        size: [30, 20],
        defaultValues: {
            capacity: 1000,
            speed: 50,
            currentLoad: 0,
            status: 'idle'
        },
        getStatusColor: function (truck) {
            return '#3498db';
        }
    },
    depot: {
        icon: '🏭',
        color: '#8e44ad',
        size: [35, 35],
        defaultValues: {
            name: 'Default Depot'
        },
        getStatusColor: function (depot) {
            return '#8e44ad';
        }
    }
};

let items = {
    bins: [],
    trucks: [],
    depots: []
};

function lerp(a, b, t) {
    return a + (b - a) * t;
}

async function initializeBackend() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        console.log('Connection established:', data);

        // Initialize system
        await fetch(`${API_BASE}/initialize`, { method: 'POST' });
        console.log('Backend initialized');

        // Fetch simulation start hour from backend
        await fetchSimulationStartHour();

        // Initialize simulation time display after config is loaded
        updateSimulationTime();

    } catch (error) {
        console.error('Backend connection failed:', error);
        showBackendError();

        // Still initialize time display with default value
        updateSimulationTime();
    }
}

async function fetchSimulationStartHour() {
    try {
        console.log('Fetching simulation start hour from backend...');
        const response = await fetch(`${API_BASE}/config/simulation_start_hour`);
        const data = await response.json();

        if (data.status === 'success') {
            simulationStartHour = data.simulation_start_hour;
            console.log(`✅ Simulation start hour fetched from backend: ${simulationStartHour}`);
            console.log(`Time will now display starting from ${simulationStartHour}:00:00`);
        } else {
            console.warn('❌ Failed to fetch simulation start hour, using default:', simulationStartHour);
        }
    } catch (error) {
        console.error('❌ Error fetching simulation start hour:', error);
        console.warn('Using default simulation start hour:', simulationStartHour);
    }
}

async function fetchTrafficInfoFromBackend(simulationTimeParam) {
    try {
        const response = await fetch(`${API_BASE}/config/traffic_info?simulation_time=${simulationTimeParam}`);
        const data = await response.json();

        if (data.status === 'success' && data.traffic_info) {
            // Use existing updateTrafficDisplay function that properly handles backend traffic data
            updateTrafficDisplay(data.traffic_info);
        } else {
            console.warn('❌ Failed to fetch traffic info from backend');
        }
    } catch (error) {
        console.error('❌ Error fetching traffic info:', error);
    }
}

function showBackendError() {
    const errorDiv = document.createElement('div');
    errorDiv.innerHTML = `
        <div style="background: #e74c3c; color: white; padding: 10px; margin: 10px; border-radius: 5px;">
            Backend not connected.
        </div>
    `;
    document.body.insertBefore(errorDiv, document.body.firstChild);
}

function initializeMap() {
    // Initialize map centered on Islamabad
    map = L.map('map').setView([33.6844, 73.0479], 13);
    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    // No marker clustering: all markers will be added directly to map
}

function initializeControls() {
    // Simulation controls
    document.getElementById('startBtn').addEventListener('click', startSimulation);
    document.getElementById('stopBtn').addEventListener('click', stopSimulation);
    document.getElementById('resetBtn').addEventListener('click', resetSimulation);

    // Speed slider
    const speedSlider = document.getElementById('speedSlider');
    speedSlider.addEventListener('input', function () {
        simulationSpeed = parseInt(this.value);
        document.getElementById('speedValue').textContent = simulationSpeed + 'x';
    });

    // Add item buttons - auto-add items in map center area
    document.getElementById('addBinBtn').addEventListener('click', () => autoAddItem('bin'));
    document.getElementById('addTruckBtn').addEventListener('click', () => autoAddItem('truck'));
    document.getElementById('addDepotBtn').addEventListener('click', () => autoAddItem('depot'));

    initializeSaveLoadControls();
}

let savedFiles = [];

function initializeSaveLoadControls() {
    document.getElementById('saveSystemBtn').addEventListener('click', saveCurrentSystem);
    document.getElementById('loadSystemBtn').addEventListener('click', openLoadDialog);
    document.getElementById('fileInput').addEventListener('change', handleFileLoad);

    // Load saved files list on startup
    loadSavedFilesList();
}

function initializeModal() {
    const modal = document.getElementById('editModal');
    const closeBtn = document.querySelector('.close');
    const cancelBtn = document.getElementById('cancelBtn');
    const saveBtn = document.getElementById('saveBtn');
    const deleteBtn = document.getElementById('deleteBtn');

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    saveBtn.addEventListener('click', saveItemProperties);
    deleteBtn.addEventListener('click', deleteItem);

    // Close modal when clicking outside
    window.addEventListener('click', function (event) {
        if (event.target === modal) {
            closeModal();
        }
    });
}

function createMarker(item, type) {
    const config = ITEM_CONFIGS[type];
    const color = config.getStatusColor(item);
    
    let html;
    if (type === 'bin') {
        // Use circular shape for bins with smooth transitions
        html = `<div class="bin-marker-content" style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; transition: all 0.3s ease;">${config.icon}</div>`;
    } else {
        // Use rectangular shape for trucks and depots
        html = `<div style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 4px; border: 2px solid #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">${config.icon}</div>`;
    }
    
    const icon = L.divIcon({
        className: `${type}-icon`,
        html: html,
        iconSize: config.size,
        iconAnchor: [config.size[0] / 2, config.size[1] / 2]
    });

    const marker = L.marker([item.lat, item.lng], { icon: icon, draggable: true }).addTo(map);

    marker.on('click', () => openEditModal(item, type));
    marker.on('drag', (e) => updateItemPosition(item, type, e.target.getLatLng()));

    return marker;
}

async function addItem(type, lat, lng) {
    const center = map.getCenter();
    const bounds = map.getBounds();

    if (!lat || !lng) {
        const latOffset = (Math.random() - 0.5) * (bounds.getNorth() - bounds.getSouth()) * 0.3;
        const lngOffset = (Math.random() - 0.5) * (bounds.getEast() - bounds.getWest()) * 0.3;
        lat = center.lat + latOffset;
        lng = center.lng + lngOffset;
    }

    try {
        const config = ITEM_CONFIGS[type];
        const requestData = {
            lat: lat,
            lng: lng,
            ...config.defaultValues
        };

        // Special handling for trucks (place at depot)
        if (type === 'truck' && items.depots.length > 0) {
            const nearestDepot = items.depots[0];
            requestData.lat = nearestDepot.lat;
            requestData.lng = nearestDepot.lng;
        }

        const response = await fetch(`${API_BASE}/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();
        if (data.status === 'success') {
            const item = data[type];
            item.marker = createMarker(item, type);

            // Add type-specific properties
            if (type === 'truck') {
                item.targetBin = null;
                item.targetDepot = null;
                item.route = [];
                item.routeIndex = 0;
                item.returnRoute = [];
                item.returnRouteIndex = 0;
                item.waitingUntil = null;  // ADD THIS
                item.waitReason = '';
            }

            items[`${type}s`].push(item);
            updateStats();

            if (type === 'depot') {
                map.setView([lat, lng], 14);
            }
        }
    } catch (error) {
        console.error(`Failed to add ${type}:`, error);
    }
}

function autoAddItem(type) {
    addItem(type);
}

async function updateBackendPosition(item, type) {
    try {
        // Extract only data properties, not the marker
        const dataToSend = {
            id: item.id,
            lat: item.lat,
            lng: item.lng
        };

        // Add type-specific properties
        if (type === 'bin') {
            dataToSend.fillLevel = item.fillLevel;
            dataToSend.capacity = item.capacity;
            dataToSend.fillRate = item.fillRate;
            dataToSend.threshold = item.threshold;
            if (item.lastCollection !== undefined) {
                dataToSend.lastCollection = item.lastCollection;
            }
        } else if (type === 'truck') {
            dataToSend.capacity = item.capacity;
            dataToSend.speed = item.speed;
            dataToSend.currentLoad = item.currentLoad;
            dataToSend.status = item.status;
        } else if (type === 'depot') {
            dataToSend.name = item.name;
        }

        await fetch(`${API_BASE}/${type}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dataToSend)  // Send clean data only
        });
    } catch (error) {
        console.error(`Failed to update backend ${type} position:`, error);
    }
}

function updateItemPosition(item, type, latlng) {
    item.lat = latlng.lat;
    item.lng = latlng.lng;
    updateBackendPosition(item, type);
}

function updateItemMarkerColor(item, type) {
    const marker = item.marker;
    if (!marker) return;
    const config = ITEM_CONFIGS[type];
    const color = config.getStatusColor(item);

    if (type === 'bin') {
        // Use smooth transition for bins
        const markerElement = marker._icon;
        if (markerElement) {
            const binDiv = markerElement.querySelector('.bin-marker-content');
            if (binDiv) {
                binDiv.style.background = color;
                return; // Exit early, we've updated smoothly
            }
        }
    }

    // Fallback for non-bins or when smooth update fails
    let html;
    if (type === 'bin') {
        html = `<div class="bin-marker-content" style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; transition: all 0.3s ease;">${config.icon}</div>`;
    } else {
        html = `<div style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 4px; border: 2px solid #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">${config.icon}</div>`;
    }

    const icon = L.divIcon({
        className: `${type}-icon`,
        html: html,
        iconSize: config.size,
        iconAnchor: [config.size[0] / 2, config.size[1] / 2]
    });

    marker.setIcon(icon);
}

function showItemRoute(item, routeType = 'forward', options = {}) {
    const route = routeType === 'return' ? item.returnRoute : item.route;
    if (!route || route.length < 2) return;
    hideItemRoute(item, routeType); // Clear existing

    const defaultOptions = {
        color: routeType === 'return' ? '#3498db' : '#e74c3c',
        weight: routeType === 'return' ? 3 : 4,
        opacity: 0.8,
        dashArray: routeType === 'return' ? '10, 10' : null
    };

    const finalOptions = { ...defaultOptions, ...options };
    const latlngs = route.map(wp => [wp.lat, wp.lng]);

    const polyline = L.polyline(latlngs, finalOptions).addTo(map);

    const target = routeType === 'return' ? 'Depot' : (item.targetBin?.id || 'Target');
    polyline.bindPopup(`
        <b>${item.id} → ${target}</b><br>
        Type: ${routeType} route<br>
        Distance: ${(item.totalDistance || item.totalReturnDistance || 0).toFixed(0)}m<br>
        Waypoints: ${route.length}
    `);

    // Store route
    const routeKey = `${item.id}_${routeType}`;
    routePolylines.set(routeKey, polyline);

    console.log(`🗺️ Showing ${routeType} route for ${item.id}`);
}

function hideItemRoute(item, routeType = 'both') {
    const routesToHide = routeType === 'both' ? ['forward', 'return'] : [routeType];
    routesToHide.forEach(type => {
        const routeKey = `${item.id}_${type}`;
        const polyline = routePolylines.get(routeKey);

        if (polyline && map.hasLayer(polyline)) {
            map.removeLayer(polyline);
            routePolylines.delete(routeKey);
            console.log(`🗺️ Hiding ${type} route for ${item.id}`);
        }
    });
}

function moveItemAlongRoute(truck, routeType = 'forward') {
    const route = routeType === 'return' ? truck.returnRoute : truck.route;
    const indexProp = routeType === 'return' ? 'returnRouteIndex' : 'routeIndex';
    const currentIndex = truck[indexProp] || 0;
    if (!route || route.length === 0 || currentIndex >= route.length) {
        handleRouteCompletion(truck, routeType);
        return;
    }

    const targetWaypoint = route[currentIndex];
    const distance = calculateDistance(truck.lat, truck.lng, targetWaypoint.lat, targetWaypoint.lng);

    if (distance < 0.0001) {
        truck[indexProp] = currentIndex + 1;
        if (truck[indexProp] >= route.length) {
            handleRouteCompletion(truck, routeType);
            return;
        }
    }

    // Move towards waypoint
    const speed = truck.speed / 3600;
    const moveDistance = speed * simulationSpeed;
    const ratio = Math.min(moveDistance / distance, 1);

    truck.lat = lerp(truck.lat, targetWaypoint.lat, ratio);
    truck.lng = lerp(truck.lng, targetWaypoint.lng, ratio);
    truck.marker.setLatLng([truck.lat, truck.lng]);

    if (Math.random() < 0.1) updateBackendPosition(truck, 'truck');
}

function moveItemStraightLine(truck, target) {
    const distance = calculateDistance(truck.lat, truck.lng, target.lat, target.lng);
    if (distance < 0.001) {
        if (target === truck.targetDepot) {
            truck.status = 'idle';
            truck.currentLoad = 0;
            truck.targetDepot = null;
            console.log(`🏭 ${truck.id} returned to depot and unloaded`);
            // Notify backend that truck completed its route and is now available
            updateTruckAssignmentStatus(truck.id, 'completed_route');
        } else {
            truck.status = 'collecting';
        }
        updateBackendPosition(truck, 'truck');
        return;
    }

    const speed = truck.speed / 3600;
    const moveDistance = speed * simulationSpeed;
    const ratio = Math.min(moveDistance / distance, 1);

    truck.lat += (target.lat - truck.lat) * ratio;
    truck.lng += (target.lng - truck.lng) * ratio;
    truck.marker.setLatLng([truck.lat, truck.lng]);
}

function handleRouteCompletion(truck, routeType) {
    if (routeType === 'return') {
        truck.lat = truck.targetDepot.lat;
        truck.lng = truck.targetDepot.lng;
        truck.marker.setLatLng([truck.lat, truck.lng]);
        truck.status = 'idle';
        truck.currentLoad = 0;
        truck.targetDepot = null;
        truck.returnRoute = [];
        truck.returnRouteIndex = 0;
        truck.hasAssignment = false;

        hideItemRoute(truck, 'return');
        console.log(`${truck.id} completed return route`);

        // Notify backend that route is completed
        updateTruckAssignmentStatus(truck.id, 'route_completed');

        // If there is a pending route (remaining bins), resume immediately
        if (truck.pendingRoute && truck.pendingRoute.length > 0) {
            const pending = truck.pendingRoute;
            truck.pendingRoute = null;
            // Dispatch to the remaining bins that were deferred until after unloading
            assignTruckToMultipleBins(truck, pending);
            return; // exit early; assignTruckToMultipleBins sets status/travel
        }
    } else {
        truck.lat = truck.targetBin.lat;
        truck.lng = truck.targetBin.lng;
        truck.marker.setLatLng([truck.lat, truck.lng]);
        truck.status = 'collecting';
        truck.routeIndex = 0;
        console.log(`${truck.id} completed forward route to ${truck.targetBin.id}`);
    }
    updateBackendPosition(truck, 'truck');
}

async function startSimulation() {
    if (isSimulationRunning) return;
    if (items.depots.length === 0 || items.bins.length === 0 || items.trucks.length === 0) {
        alert('Please add at least one depot, bin, and truck before starting simulation');
        return;
    }

    console.log('Starting simulation...');

    try {
        const response = await fetch(`${API_BASE}/start_simulation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (data.status === 'success') {
            isSimulationRunning = true;

            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;

            // APPLY AI ROUTING DECISIONS TO TRUCKS
            await applyAIRoutingDecisions();

            // Start simulation loop
            simulationInterval = setInterval(simulationStep, Math.max(20, 1000 / simulationSpeed));

            console.log('✅ Simulation started');
        }

    } catch (error) {
        console.error('⚠️ Failed to start simulation:', error);
        alert(`Failed to start simulation: ${error.message}`);
    }
}

async function applyAIRoutingDecisions() {
    try {
        // Use new minimalist dispatch endpoint
        const response = await fetch(`${API_BASE}/dispatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                simulation_time: simulationTime
            })
        });

        const data = await response.json();

        if (data.status === 'success' && data.routes && data.routes.length > 0) {
            console.log(`🚛 Processing ${data.routes.length} VROOM routes...`);

            for (const route of data.routes) {
                const truck = items.trucks.find(t => t.id === route.truck_id);

                if (truck && truck.status === 'idle') {
                    // Dispatch immediately with VROOM route
                    truck.dispatchTime = simulationTime;
                    await assignTruckToMultipleBins(truck, route.bin_ids);
                    console.log(`${truck.id} → ${route.bin_ids.join(', ')} (VROOM optimized)`);
                }
            }
            
            if (data.waiting?.length > 0) {
                console.log(`⏳ ${data.waiting.length} bins waiting for light traffic`);
            }
        } else {
            console.log('ℹ️ No urgent bins for routing');
        }

    } catch (error) {
        console.error('Routing application failed:', error);
    }
}

function stopSimulation() {
    if (!isSimulationRunning) return;
    isSimulationRunning = false;
    clearInterval(simulationInterval);

    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
}
function resetSimulation() {
    stopSimulation();
    simulationTime = 0;
    collectionsToday = 0;

    // Reset all items
    items.bins.forEach(bin => {
        bin.fillLevel = Math.random() * 50 + 10;
        bin.lastCollection = 0;
        updateItemMarkerColor(bin, 'bin');
    });

    items.trucks.forEach(truck => {
        truck.status = 'idle';
        truck.currentLoad = 0;
        truck.targetBin = null;
        truck.targetDepot = null;
        truck.route = [];
        truck.routeIndex = 0;
        truck.returnRoute = [];
        truck.returnRouteIndex = 0;
        hideItemRoute(truck, 'both');
    });

    updateStats();
    updateSimulationTime(); // This will also update traffic info
    console.log('🔄 Simulation reset');
}

async function checkScheduledDispatches() {
    try {
        // Get active schedules from backend
        const response = await fetch(`${API_BASE}/schedules/active?simulation_time=${simulationTime}`);
        const data = await response.json();

        if (data.status === 'success' && data.active_schedules.length > 0) {
            console.log(`📅 Found ${data.active_schedules.length} scheduled dispatches ready for execution`);

            for (const schedule of data.active_schedules) {
                await executeScheduledDispatch(schedule);
            }
        }

    } catch (error) {
        console.error('Error checking scheduled dispatches:', error);
    }
}

async function executeScheduledDispatch(schedule) {
    try {
        // Find the truck
        const truck = items.trucks.find(t => t.id === schedule.truck_id);
        if (!truck) {
            console.warn(`Truck ${schedule.truck_id} not found for scheduled dispatch`);
            return;
        }

        // Check if truck is available
        if (truck.status !== 'idle') {
            console.warn(`Truck ${schedule.truck_id} is not idle (${truck.status}), skipping scheduled dispatch`);
            // Could implement queuing or rescheduling here
            return;
        }

        // Mark schedule as executing
        const executeResponse = await fetch(`${API_BASE}/schedules/${schedule.id}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ simulation_time: simulationTime })
        });

        const executeData = await executeResponse.json();
        if (executeData.status !== 'success') {
            console.error(`Failed to mark schedule ${schedule.id} as executing`);
            return;
        }

        // Execute the dispatch
        truck.dispatchReason = `Scheduled: ${schedule.reason}`;
        truck.dispatchTime = simulationTime;

        // Assign truck to the scheduled route
        await assignTruckToMultipleBins(truck, schedule.target_bin_ids);

        console.log(`📅 ✅ Executed scheduled dispatch: ${schedule.truck_id} → ${schedule.target_bin_ids.join(', ')} (${schedule.area_name})`);

        // Update schedule status to completed after successful dispatch
        setTimeout(async () => {
            try {
                await fetch(`${API_BASE}/schedules/${schedule.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: 'completed' })
                });

                // Reload schedules to update UI
                await loadSchedules();
            } catch (error) {
                console.error('Error updating schedule status:', error);
            }
        }, 1000); // Small delay to ensure dispatch is processed

    } catch (error) {
        console.error(`Error executing scheduled dispatch ${schedule.id}:`, error);
    }
}

async function handleScheduledDispatchFromBackend(dispatch) {
    try {
        const truck = items.trucks.find(t => t.id === dispatch.truck_id);
        if (!truck) {
            console.warn(`Truck ${dispatch.truck_id} not found for backend scheduled dispatch`);
            return;
        }

        // Set dispatch reason and execute
        truck.dispatchReason = dispatch.reason;
        truck.dispatchTime = simulationTime;

        // Assign truck to the scheduled route
        await assignTruckToMultipleBins(truck, dispatch.route);

        console.log(`📅 ✅ Backend scheduled dispatch executed: ${dispatch.truck_id} → ${dispatch.route.join(', ')}`);

        // Reload schedules to update UI
        await loadSchedules();

    } catch (error) {
        console.error('Error handling backend scheduled dispatch:', error);
    }
}

async function simulationStep() {
    simulationTime += simulationSpeed;
    await callBackendSimulationStep(simulationSpeed);

    items.trucks.forEach(updateTruck);

    // Check for scheduled dispatches
    await checkScheduledDispatches();

    const idleTrucks = items.trucks.filter(t => t.status === 'idle' && !t.hasAssignment);
    if (idleTrucks.length > 0) {
        await assignIdleTrucks();
    }
    updateStats();
    updateSimulationTime();

    if (simulationInterval && isSimulationRunning) {  // Add isSimulationRunning check
        clearInterval(simulationInterval);
        simulationInterval = setInterval(simulationStep, Math.max(20, 1000 / simulationSpeed));
    }
}

async function assignIdleTrucks() {
    try {
        // Call new minimalist dispatch endpoint
        const response = await fetch(`${API_BASE}/dispatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                simulation_time: simulationTime
            })
        });

        const data = await response.json();

        if (data.status === 'success' && data.routes?.length > 0) {
            console.log(`🚛 Processing ${data.routes.length} VROOM routes...`);
            
            for (const route of data.routes) {
                const truck = items.trucks.find(t => t.id === route.truck_id);
                
                if (truck && truck.status === 'idle') {
                    // Assign truck to multiple bins from VROOM route
                    await assignTruckToMultipleBins(truck, route.bin_ids);
                }
            }
            
            if (data.waiting?.length > 0) {
                console.log(`⏳ ${data.waiting.length} bins waiting for light traffic`);
            }
        }
    } catch (error) {
        console.error('⚠️ Dispatch error:', error);
    }
}

function updateTruck(truck) {
    switch (truck.status) {
        case 'waiting':  // ADD THIS CASE
            if (simulationTime >= truck.waitingUntil) {
                // Waiting period over, dispatch now
                truck.status = 'idle';
                truck.waitingUntil = null;
                truck.waitReason = '';
                if (truck.pendingRoute) {
                    assignTruckToMultipleBins(truck, truck.pendingRoute);
                    truck.pendingRoute = null;
                }
            }
            break;
        case 'traveling':
            if (truck.route && truck.route.length > 0) {
                moveItemAlongRoute(truck, 'forward');
            } else {
                moveItemStraightLine(truck, truck.targetBin);
            }
            break;
        case 'collecting':
            performCollection(truck);
            break;
        case 'returning_to_depot':
            if (truck.returnRoute && truck.returnRoute.length > 0) {
                moveItemAlongRoute(truck, 'return');
            } else {
                moveItemStraightLine(truck, truck.targetDepot);
            }
            break;
        case 'idle':
            if (truck.currentLoad > 0) {
                truck.status = 'returning_to_depot';
                const depot = findNearestDepot(truck);
                if (depot) {
                    truck.targetDepot = depot;
                    getTruckReturnRoute(truck, depot);
                }
            } else {
                // Truck is truly idle with no load - ensure backend knows it's available
                // This handles edge cases where status wasn't properly synchronized
                if (!truck._idleNotified) {
                    updateTruckAssignmentStatus(truck.id, 'available');
                    truck._idleNotified = true;
                }
            }
            break;
    }
}

async function performCollection(truck) {
    const bin = truck.targetBin;
    if (!bin || bin.fillLevel <= 1) {
        truck.status = 'idle';
        truck.targetBin = null;
        return;
    }

    const distance = calculateDistance(truck.lat, truck.lng, bin.lat, bin.lng);
    if (distance > 0.001) return;

    // Collect current bin
    const wasteAmount = (bin.fillLevel / 100) * bin.capacity;
    truck.currentLoad += wasteAmount;
    bin.fillLevel = 0;
    bin.lastCollection = simulationTime;

    updateItemMarkerColor(bin, 'bin');
    await updateBackendPosition(bin, 'bin');
    collectionsToday++;

    console.log(`✅ ${truck.id} collected ${bin.id} (${wasteAmount.toFixed(0)}L)`);
    
    // Notify backend that bin was collected (prevents duplicate dispatch)
    try {
        await fetch(`${API_BASE}/bins_collected`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                truck_id: truck.id,
                collected_bin_ids: [bin.id],
                simulation_time: simulationTime
            })
        });
    } catch (error) {
        console.error('Failed to notify backend of bin collection:', error);
    }

    // Continue with queued bins from the current assignment if possible
    if (Array.isArray(truck.routeQueue) && truck.routeQueue.length > 0) {
        truck.routeQueue = truck.routeQueue.filter(b => b.id !== bin.id);

        while (truck.routeQueue.length > 0) {
            const nextPlanned = truck.routeQueue[0];
            const nextAmount = (nextPlanned.fillLevel / 100) * nextPlanned.capacity;
            if (truck.currentLoad + nextAmount <= truck.capacity) {
                truck.targetBin = nextPlanned;
                truck.status = 'traveling';
                await assignTruckToRoute(truck, nextPlanned);
                return;
            }
            // Can't fit next planned bin; store remaining IDs for after depot unload
            truck.pendingRoute = truck.routeQueue.map(b => b.id);
            truck.routeQueue = [];
            break;
        }
    }

    // Ask backend for additional nearby bins to collect on this run
    try {
        const response = await fetch(`${API_BASE}/check_urgent_bins`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                truck_id: truck.id,
                target_bin_id: bin.id,
                current_load: truck.currentLoad,
                simulation_time: simulationTime
            })
        });

        const data = await response.json();

        if (data.status === 'success' && Array.isArray(data.bins_to_collect) && data.bins_to_collect.length > 1) {
            // Build full sequence from backend (preserve order), excluding the one just collected
            const allIds = data.bins_to_collect.map(b => b.id);
            const remainingIds = allIds.filter(id => id !== bin.id);
            const remainingBins = remainingIds
                .map(id => items.bins.find(localBin => localBin.id === id))
                .filter(Boolean);
            console.log(`🔍 Backend suggested sequence: ${allIds.join(', ')}`);

            // Determine which of these can fit before needing a dump
            const feasibleBins = [];
            let tempLoad = truck.currentLoad;
            for (const cand of remainingBins) {
                const amt = (cand.fillLevel / 100) * cand.capacity;
                if (tempLoad + amt <= truck.capacity) {
                    feasibleBins.push(cand);
                    tempLoad += amt;
                } else {
                    break; // first that doesn't fit -> stop here
                }
            }

            const overflowBins = remainingBins.slice(feasibleBins.length);

            if (overflowBins.length > 0) {
                truck.pendingRoute = overflowBins.map(b => b.id);
            }

            if (feasibleBins.length > 0) {
                truck.routeQueue = feasibleBins;
                const next = feasibleBins[0];
                truck.targetBin = next;
                truck.status = 'traveling';
                await assignTruckToRoute(truck, next);
                return;
            }
        }
    } catch (error) {
        console.error('Failed to fetch follow-up bins:', error);
    }

    // Return to depot if no more bins to collect or truck is full
    truck.status = 'returning_to_depot';
    truck.targetBin = null;
    truck.routeQueue = [];
    hideItemRoute(truck, 'forward');

    const depot = findNearestDepot(truck);
    if (depot) {
        truck.targetDepot = depot;
        getTruckReturnRoute(truck, depot);
    }
}

async function assignTruckToMultipleBins(truck, binIds) {
    const targetBins = binIds.map(id => items.bins.find(b => b.id === id)).filter(Boolean);
    if (targetBins.length === 0) return;

    truck.status = 'traveling';
    truck.targetBin = targetBins[0];
    truck.routeQueue = targetBins;
    truck.currentRouteIndex = 0;
    console.log(`🚛 ${truck.id} assigned to bins:`, targetBins.map(b => `${b.id}(${b.fillLevel}%)`));

    // Get route to first bin
    await assignTruckToRoute(truck, targetBins[0]);
}

async function assignTruckToRoute(truck, bin) {
    if (truck._routePending) {
        console.log(`⏳ Route request already pending for ${truck.id}`);
        return;
    }
    truck._routePending = true;
    try {
        const response = await fetch(`${API_BASE}/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_lat: truck.lat,
                from_lng: truck.lng,
                to_lat: bin.lat,
                to_lng: bin.lng
            })
        });
        const data = await response.json();

        if (data.status === 'success') {
            truck.targetBin = bin;
            truck.status = 'traveling';
            truck.route = data.route.waypoints || [];
            truck.routeIndex = 0;
            truck.totalDistance = data.route.distance;

            hideItemRoute(truck, 'forward');
            showItemRoute(truck, 'forward');

            console.log(`🚛 ${truck.id} assigned to ${bin.id}`);
        } else {
            truck.targetBin = bin;
            truck.status = 'traveling';
            truck.route = [];
        }

    } catch (error) {
        console.error('Route calculation failed:', error);
        truck.targetBin = bin;
        truck.status = 'traveling';
        truck.route = [];
    } finally {
        truck._routePending = false;
    }
}

async function getTruckReturnRoute(truck, depot) {
    if (truck._returnRoutePending) {
        console.log(`⏳ Return route request already pending for ${truck.id}`);
        return;
    }
    truck._returnRoutePending = true;
    try {
        const response = await fetch(`${API_BASE}/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_lat: truck.lat,
                from_lng: truck.lng,
                to_lat: depot.lat,
                to_lng: depot.lng
            })
        });
        const data = await response.json();

        if (data.status === 'success') {
            truck.returnRoute = data.route.waypoints || [];
            truck.returnRouteIndex = 0;
            truck.totalReturnDistance = data.route.distance;

            showItemRoute(truck, 'return');
        } else {
            truck.returnRoute = [];
            truck.returnRouteIndex = 0;
        }

    } catch (error) {
        console.error('Failed to get return route:', error);
        truck.returnRoute = [];
        truck.returnRouteIndex = 0;
    } finally {
        truck._returnRoutePending = false;
    }
}

async function callBackendSimulationStep(timeDelta) {
    try {
        const response = await fetch(`${API_BASE}/simulation_step`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                time_delta: timeDelta,
                simulation_time: simulationTime
            })
        });

        const data = await response.json();
        if (data.status === 'success') {
            // Update bin data first
            data.bins.forEach(backendBin => {
                const localBin = items.bins.find(b => b.id === backendBin.id);
                if (localBin) {
                    const timeSinceCollection = simulationTime - (localBin.lastCollection || 0);
                    if (timeSinceCollection < 10 && localBin.fillLevel === 0) return;

                    localBin.fillLevel = backendBin.fillLevel;
                    localBin.dynamic_threshold = backendBin.dynamic_threshold;
                }
            });

            // NEW: Trigger proactive dispatch when bins cross threshold in this step
            if (Array.isArray(data.bins_hit_threshold) && data.bins_hit_threshold.length > 0) {
                console.log(`⚠️ Bins hit threshold this step: ${data.bins_hit_threshold.join(', ')}`);
                for (const binId of data.bins_hit_threshold) {
                    // Fire-and-forget; internal logging will show the decision
                    handleBinReachedDT(binId);
                }
            }

            // Update all bin markers smoothly based on latest fill state
            items.bins.forEach(bin => {
                updateBinMarkerStyle(bin);
            });

            if (data.traffic_info) {
                updateTrafficDisplay(data.traffic_info);
            }

            // Handle scheduled dispatches
            if (data.schedule_dispatches && data.schedule_dispatches.length > 0) {
                console.log(`📅 Processing ${data.schedule_dispatches.length} scheduled dispatches from backend`);
                for (const dispatch of data.schedule_dispatches) {
                    await handleScheduledDispatchFromBackend(dispatch);
                }
            }

            // Store the backend collection queue for UI synchronization
            window.backendCollectionQueue = data.collection_queue || [];
            
            // Update the collection queue UI immediately with backend data
            updateCollectionQueueFromBackend();
        }
    } catch (error) {
        console.error('Backend simulation step failed:', error);
    }
}

// POST helper: notify backend when a bin crosses its disposal threshold
async function handleBinReachedDT(binId) {
    try {
        console.log(`🔔 Triggering proactive dispatch for bin ${binId} at t=${simulationTime}s`);
        const response = await fetch(`${API_BASE}/bin_reached_dt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bin_id: binId,
                simulation_time: simulationTime
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            const decision = data.dispatch_decision || {};
            console.log(`🤖 Proactive decision for ${binId}:`, decision);
        } else {
            console.warn(`❌ Proactive dispatch call failed for ${binId}:`, data.message || data);
        }
    } catch (err) {
        console.error(`⚠️ Error calling /api/bin_reached_dt for ${binId}:`, err);
    }
}

// POST helper: update truck assignment status for proactive dispatch tracking
async function updateTruckAssignmentStatus(truckId, status, assignedBins = []) {
    try {
        const response = await fetch(`${API_BASE}/update_truck_assignment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                truck_id: truckId,
                status: status,
                assigned_bins: assignedBins,
                simulation_time: simulationTime
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            console.log(`Updated truck ${truckId} status to ${status}`);
        } else {
            console.warn(`❌ Failed to update truck ${truckId} status:`, data.message || data);
        }
    } catch (err) {
        console.error(`⚠️ Error updating truck ${truckId} assignment status:`, err);
    }
}

function calculateDistance(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLng / 2) * Math.sin(dLng / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function findNearestDepot(truck) {
    if (items.depots.length === 0) return null;
    let nearest = items.depots[0];
    let minDistance = calculateDistance(truck.lat, truck.lng, nearest.lat, nearest.lng);

    for (let i = 1; i < items.depots.length; i++) {
        const distance = calculateDistance(truck.lat, truck.lng, items.depots[i].lat, items.depots[i].lng);
        if (distance < minDistance) {
            minDistance = distance;
            nearest = items.depots[i];
        }
    }

    return nearest;
}

function updateStats() {
    document.getElementById('totalBins').textContent = items.bins.length;
    document.getElementById('totalTrucks').textContent = items.trucks.length;
    document.getElementById('totalDepots').textContent = items.depots.length;
    document.getElementById('collectionsToday').textContent = collectionsToday;
    updateItemsList();
    updateSchedulesDisplay();
}

function updateItemsList() {
    updateBinsList();
    updateTrucksList();
    updateCollectionQueue();
}

function updateBinsList() {
    const container = document.getElementById('binsList');
    container.innerHTML = '';
    
    // Get backend collection queue for visual indicators
    const backendQueue = window.backendCollectionQueue || [];
    const queueSet = new Set(backendQueue);
    
    items.bins.forEach(bin => {
        const dynamicThreshold = bin.dynamic_threshold || bin.threshold || 80;
        const staticThreshold = bin.threshold || 80;
        const isTargeted = items.trucks.some(truck => truck.targetBin === bin);
        const inQueue = queueSet.has(bin.id);
        
        // Enhanced status - bins in queue always need collection
        let statusText = isTargeted ? 'TARGETED' :
            (bin.fillLevel >= dynamicThreshold || inQueue) ? 'NEEDS COLLECTION' : 'OK';

        // Show both thresholds if they differ
        const thresholdText = Math.abs(dynamicThreshold - staticThreshold) > 0.1
            ? `DT: ${dynamicThreshold.toFixed(2)}%`
            : `T: ${staticThreshold}%`;

        const card = document.createElement('div');
        let cardClass = `item-card ${getStatusClass(bin.fillLevel)}`;
        if (inQueue) {
            cardClass += ' in-queue';
        }
        card.className = cardClass;
        card.innerHTML = `
            <div class="item-header">
                <span class="item-id">${bin.id}</span>
                <span class="item-status">${bin.fillLevel.toFixed(1)}%</span>
            </div>
            <div class="item-details">
                ${statusText} | ${thresholdText} | Rate: ${bin.fillRate.toFixed(1)}L/h
            </div>
        `;
        card.addEventListener('click', () => openEditModal(bin, 'bin'));
        container.appendChild(card);
    });
}

function updateTrucksList() {
    const container = document.getElementById('trucksList');
    container.innerHTML = '';
    items.trucks.forEach(truck => {
        let statusDisplay = truck.status;
        let targetInfo = '';
        let cardClass = 'normal';

        if (truck.status === 'waiting') {
            const waitRemaining = getWaitRemainingMinutes(truck.waitingUntil, simulationTime);
            statusDisplay = `waiting (${waitRemaining}min)`;
            targetInfo = ` - ${truck.waitReason}`;
            cardClass = 'warning';  // Highlight waiting trucks
        } else if (truck.dispatchReason && (simulationTime - truck.dispatchTime) < 30) {
            // Show dispatch reason for 30 seconds after dispatch
            targetInfo += ` - ${truck.dispatchReason}`;
        } else {
            targetInfo = truck.targetBin ? ` → ${truck.targetBin.id}` :
                truck.targetDepot ? ` → ${truck.targetDepot.id}` : '';
        }

        const card = document.createElement('div');
        card.className = `item-card ${cardClass}`;
        card.innerHTML = `
            <div class="item-header">
                <span class="item-id">${truck.id}</span>
                <span class="item-status">${statusDisplay}</span>
            </div>
            <div class="item-details">
                Load: ${truck.currentLoad.toFixed(0)}/${truck.capacity}L${targetInfo}
            </div>
        `;
        card.addEventListener('click', () => openEditModal(truck, 'truck'));
        container.appendChild(card);
    });
}

// Store previous queue state for smooth transitions
let previousQueue = [];

// New function: Update collection queue using backend data from simulation step
function updateCollectionQueueFromBackend() {
    const container = document.getElementById('collectionQueue');
    
    // Use backend queue stored from simulation_step response
    const queueIds = window.backendCollectionQueue || [];
    
    if (queueIds.length === 0) {
        smoothUpdateQueueContainer(container, [], 'No collections needed');
        return;
    }
    
    // Map queue IDs to full bin objects
    const queueBins = queueIds
        .map(binId => items.bins.find(b => b.id === binId))
        .filter(bin => bin !== undefined);
    
    smoothUpdateQueueContainer(container, queueBins);
    previousQueue = [...queueBins];
}

// Legacy function: Fetch collection queue from dedicated endpoint (fallback)
async function updateCollectionQueue() {
    const container = document.getElementById('collectionQueue');
    try {
        const response = await fetch(`${API_BASE}/collection_queue`);
        const data = await response.json();
        if (data.status === 'success' && Array.isArray(data.collection_queue)) {
            const newQueue = data.collection_queue;
            if (newQueue.length === 0) {
                smoothUpdateQueueContainer(container, [], 'No collections needed');
                return;
            }
            smoothUpdateQueueContainer(container, newQueue);
            previousQueue = [...newQueue]; // Store for next comparison
        } else {
            // Only show error, not 'No collections needed' for non-success cases
            smoothUpdateQueueContainer(container, [], 'Error loading queue');
        }
    } catch (err) {
        smoothUpdateQueueContainer(container, [], 'Error loading queue');
        console.error('Error fetching collection queue:', err);
    }
}

function smoothUpdateQueueContainer(container, newQueue, emptyMessage = null) {
    if (emptyMessage) {
        // Fade out existing items and show nothing (no message)
        const existingCards = container.querySelectorAll('.item-card');
        existingCards.forEach((card, index) => {
            setTimeout(() => {
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                setTimeout(() => card.remove(), 200);
            }, index * 50);
        });
        setTimeout(() => {
            container.innerHTML = "";
        }, existingCards.length * 50 + 200);
        return;
    }

    // If there was a "no-selection" message shown previously, remove it before
    // rendering real queue items so the message doesn't appear alongside cards.
    const noSelectionEl = container.querySelector('.no-selection');
    if (noSelectionEl) {
        // Fade it out for consistency with other animations
        noSelectionEl.style.opacity = '0';
        noSelectionEl.style.transform = 'translateX(-10px)';
        setTimeout(() => {
            if (noSelectionEl.parentNode) noSelectionEl.remove();
        }, 200);
    }

    const existingCards = new Map();
    container.querySelectorAll('.item-card').forEach(card => {
        const binId = card.querySelector('.item-id').textContent;
        existingCards.set(binId, card);
    });

    const newBinIds = new Set(newQueue.map(bin => bin.id));
    
    // Remove bins no longer in queue with fade animation
    existingCards.forEach((card, binId) => {
        if (!newBinIds.has(binId)) {
            card.style.opacity = '0';
            card.style.transform = 'translateX(-20px)';
            setTimeout(() => card.remove(), 200);
        }
    });

    // Add or update bins
    newQueue.forEach((bin, index) => {
        const existingCard = existingCards.get(bin.id);
        
        if (existingCard) {
            // Update existing card smoothly
            updateExistingQueueCard(existingCard, bin);
        } else {
            // Create new card with slide-in animation
            const card = createQueueCard(bin);
            card.style.opacity = '0';
            card.style.transform = 'translateX(20px)';
            
            // Insert at correct position
            const nextCard = container.children[index];
            if (nextCard && nextCard.classList.contains('item-card')) {
                container.insertBefore(card, nextCard);
            } else {
                container.appendChild(card);
            }
            
            // Animate in
            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateX(0)';
            }, 50);
        }
    });
}

function createQueueCard(bin) {
    const card = document.createElement('div');
    card.className = `item-card ${getStatusClass(bin.fillLevel)}`;
    card.innerHTML = `
        <div class="item-header">
            <span class="item-id">${bin.id}</span>
            <span class="item-status">${bin.fillLevel.toFixed(1)}%</span>
        </div>
        <div class="item-details">
            Priority: ${bin.fillLevel >= 90 ? 'HIGH' : 'MEDIUM'}
        </div>
    `;
    return card;
}

function updateExistingQueueCard(card, bin) {
    // Smoothly update fill level
    const statusSpan = card.querySelector('.item-status');
    const currentFill = parseFloat(statusSpan.textContent);
    const targetFill = bin.fillLevel;
    
    // Animate fill level change
    if (Math.abs(currentFill - targetFill) > 0.1) {
        animateValue(statusSpan, currentFill, targetFill, 500, (value) => `${value.toFixed(1)}%`);
    }
    
    // Update card class for status color
    const newStatusClass = getStatusClass(bin.fillLevel);
    card.className = `item-card ${newStatusClass}`;
    
    // Update priority text
    const priorityText = bin.fillLevel >= 90 ? 'HIGH' : 'MEDIUM';
    const detailsDiv = card.querySelector('.item-details');
    detailsDiv.textContent = `Priority: ${priorityText}`;
}

function animateValue(element, start, end, duration, formatter) {
    const startTime = performance.now();
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Use easeOutCubic for smooth deceleration
        const eased = 1 - Math.pow(1 - progress, 3);
        const currentValue = start + (end - start) * eased;
        
        element.textContent = formatter(currentValue);
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    
    requestAnimationFrame(update);
}

function updateBinMarkerStyle(bin) {
    const config = ITEM_CONFIGS.bin;
    const fillColor = config.getStatusColor(bin);
    const borderColor = '#fff';
    const borderWidth = '2px';

    // Get existing marker element or create if needed
    const markerElement = bin.marker._icon;
    if (markerElement) {
        const binDiv = markerElement.querySelector('.bin-marker-content') || markerElement.querySelector('div');
        if (binDiv) {
            // Smoothly update styles using CSS transitions
            binDiv.style.background = fillColor;
            binDiv.style.borderColor = borderColor;
            binDiv.style.borderWidth = borderWidth;
        }
    } else {
        // Create new icon if marker doesn't exist yet
        const icon = L.divIcon({
            className: 'bin-icon',
            html: `<div class="bin-marker-content" style="background: ${fillColor}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 50%; border: ${borderWidth} solid ${borderColor}; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; transition: all 0.3s ease;">${config.icon}</div>`,
            iconSize: config.size,
            iconAnchor: [config.size[0] / 2, config.size[1] / 2]
        });
        bin.marker.setIcon(icon);
    }
}

function getStatusClass(fillLevel) {
    if (fillLevel >= 90) return 'urgent';
    if (fillLevel >= 70) return 'warning';
    return 'normal';
}

let displayedSimulationTime = 0;

function updateSimulationTime() {
    displayedSimulationTime = lerp(displayedSimulationTime, simulationTime, 0.2);
    const timeString = formatSimTime(displayedSimulationTime, true);
    const timeStringHM = formatSimTime(displayedSimulationTime, false);

    // Update main simulation time display (map overlay)
    const timeElement = document.getElementById('simulationTime');
    if (timeElement) {
        timeElement.textContent = timeString;
    }

    // Also update traffic time display (sidebar)
    const trafficTimeElement = document.getElementById('trafficTime');
    if (trafficTimeElement) {
        trafficTimeElement.textContent = timeStringHM;
    }

    // Fetch traffic info from backend instead of calculating locally
    fetchTrafficInfoFromBackend(simulationTime);
}

// Debug function - call this from browser console to test
function debugTimeDisplay() {
    const simulationElement = document.getElementById('simulationTime');
    const trafficElement = document.getElementById('trafficTime');
    const trafficLevelElement = document.getElementById('trafficLevel');
    const trafficDensityElement = document.getElementById('trafficDensity');

    console.log('=== TIME & TRAFFIC DISPLAY DEBUG ===');
    console.log('Main simulationTime element:', simulationElement);
    console.log('Current simulationTime textContent:', simulationElement?.textContent);
    console.log('Traffic trafficTime element:', trafficElement);
    console.log('Current trafficTime textContent:', trafficElement?.textContent);
    console.log('Traffic level element:', trafficLevelElement?.textContent);
    console.log('Traffic density element:', trafficDensityElement?.textContent);
    console.log('simulationTime variable:', simulationTime);
    console.log('simulationStartHour variable:', simulationStartHour);
    console.log('displayedSimulationTime variable:', displayedSimulationTime);

    // Force update
    updateSimulationTime();
    console.log('After forced update:');
    console.log('- simulationTime element:', simulationElement?.textContent);
    console.log('- trafficTime element:', trafficElement?.textContent);
    console.log('- trafficLevel element:', trafficLevelElement?.textContent);
    console.log('- trafficDensity element:', trafficDensityElement?.textContent);
    console.log('=======================================');
}

// MODAL FUNCTIONS

function openEditModal(item, type) {
    selectedItem = { item, type };
    const modal = document.getElementById('editModal');
    const title = document.getElementById('modalTitle');
    const content = document.getElementById('modalContent');

    title.textContent = `Edit ${type.charAt(0).toUpperCase() + type.slice(1)}: ${item.id}`;
    content.innerHTML = generateModalContent(item, type);
    modal.style.display = 'block';
}

function generateModalContent(item, type) {
    const config = ITEM_CONFIGS[type];
    const fields = Object.keys(config.defaultValues);
    let html = '';
    fields.forEach(field => {
        const value = item[field] !== undefined ? item[field] : config.defaultValues[field];
        const inputType = typeof value === 'number' ? 'number' : 'text';
        const step = field.includes('Rate') || field.includes('Level') ? '0.1' : '1';

        html += `
            <div class="form-group">
                <label>${field.charAt(0).toUpperCase() + field.slice(1)}:</label>
                <input type="${inputType}" id="${field}" value="${value}" step="${step}">
            </div>
        `;
    });

    return html;
}

function saveItemProperties() {
    if (!selectedItem) return;
    const { item, type } = selectedItem;
    const config = ITEM_CONFIGS[type];

    // Update item properties
    Object.keys(config.defaultValues).forEach(field => {
        const input = document.getElementById(field);
        if (input) {
            const value = input.type === 'number' ? parseFloat(input.value) : input.value;
            item[field] = value;
        }
    });

    // Update marker color if applicable
    if (type === 'bin') {
        updateItemMarkerColor(item, type);
    }

    // Update backend
    updateBackendPosition(item, type);
    updateStats();
    closeModal();
}

function deleteItem() {
    if (!selectedItem) return;
    const { item, type } = selectedItem;

    // Remove marker from map
    map.removeLayer(item.marker);

    // Remove from array
    const itemsArray = items[`${type}s`];
    const index = itemsArray.indexOf(item);
    if (index > -1) {
        itemsArray.splice(index, 1);
    }

    updateStats();
    closeModal();
}

function closeModal() {
    document.getElementById('editModal').style.display = 'none';
    selectedItem = null;
}

// SAVE/LOAD FUNCTIONS

async function saveCurrentSystem() {
    const btn = document.getElementById('saveSystemBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<div class="loading"></div> Saving...';
    btn.disabled = true;
    try {
        const systemState = {
            timestamp: new Date().toISOString(),
            version: "2.0-simplified",
            bins: items.bins.map(bin => ({
                id: bin.id, lat: bin.lat, lng: bin.lng,
                fillLevel: bin.fillLevel, capacity: bin.capacity,
                fillRate: bin.fillRate, threshold: bin.threshold
            })),
            trucks: items.trucks.map(truck => ({
                id: truck.id, lat: truck.lat, lng: truck.lng,
                capacity: truck.capacity, speed: truck.speed,
                currentLoad: truck.currentLoad, status: truck.status
            })),
            depots: items.depots.map(depot => ({
                id: depot.id, lat: depot.lat, lng: depot.lng, name: depot.name
            })),
            simulation: {
                time: simulationTime,
                collectionsToday: collectionsToday,
                isRunning: isSimulationRunning
            }
        };

        const response = await fetch(`${API_BASE}/save_system`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(systemState)
        });

        const data = await response.json();

        if (data.status === 'success') {
            showNotification(`System saved as: ${data.filename}`, 'success');
            loadSavedFilesList();
        } else {
            throw new Error(data.message);
        }

    } catch (error) {
        showNotification(`Save failed: ${error.message}`, 'error');
    }

    btn.innerHTML = originalText;
    btn.disabled = false;
}

function openLoadDialog() {
    document.getElementById('fileInput').click();
}

function handleFileLoad(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (e) {
        try {
            const systemState = JSON.parse(e.target.result);
            loadSystemFromState(systemState);
            showNotification(`Loaded: ${file.name}`, 'success');
        } catch (error) {
            showNotification(`Load failed: ${error.message}`, 'error');
        }
    };
    reader.readAsText(file);
    event.target.value = '';
}

function loadSystemFromState(systemState) {
    stopSimulation();
    clearAllItems();

    // Batch marker creation for bins, trucks, depots
    function batchCreateMarkers(itemType, type, dataArray, batchSize = 20, delay = 10, callback) {
        let i = 0;
        function processBatch() {
            for (let j = 0; j < batchSize && i < dataArray.length; j++, i++) {
                const itemData = dataArray[i];
                const item = { ...itemData, marker: createMarker(itemData, type) };
                if (type === 'truck') {
                    item.targetBin = null;
                    item.targetDepot = null;
                    item.route = [];
                    item.routeIndex = 0;
                    item.returnRoute = [];
                    item.returnRouteIndex = 0;
                    item.collectionPartners = [];
                }
                items[itemType].push(item);
            }
            if (i < dataArray.length) {
                setTimeout(processBatch, delay);
            } else if (callback) {
                callback();
            }
        }
        processBatch();
    }

    let types = ['bins', 'trucks', 'depots'];
    let idx = 0;
    function processTypes() {
        if (idx >= types.length) {
            // Sync with backend after all markers are created
            syncLoadedDataWithBackend();
            // Load simulation state
            if (systemState.simulation) {
                simulationTime = systemState.simulation.time || 0;
                collectionsToday = systemState.simulation.collectionsToday || 0;
            }
            updateStats();
            updateSimulationTime();
            centerMapOnItems();
            console.log(`✅ Loaded ${items.bins.length} bins, ${items.trucks.length} trucks, ${items.depots.length} depots`);
            return;
        }
        let itemType = types[idx];
        let type = itemType.slice(0, -1);
        batchCreateMarkers(itemType, type, systemState[itemType], 20, 10, () => {
            idx++;
            processTypes();
        });
    }
    processTypes();
}

async function syncLoadedDataWithBackend() {
    try {
        // Batch sync all items in one request (batch_sync clears items itself)
        const bins = items.bins.map(({ marker, ...bin }) => bin);
        const trucks = items.trucks.map(({ marker, ...truck }) => truck);
        const depots = items.depots.map(({ marker, ...depot }) => depot);
        await fetch(`${API_BASE}/batch_sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bins, trucks, depots })
        });

        console.log('✅ Backend sync complete');
    } catch (error) {
        console.error('⚠ Backend sync failed:', error);
    }
}

function clearAllItems() {
    ['bins', 'trucks', 'depots'].forEach(itemType => {
        items[itemType].forEach(item => map.removeLayer(item.marker));
        items[itemType].length = 0;
    });
    routePolylines.forEach(polyline => {
        if (map.hasLayer(polyline)) map.removeLayer(polyline);
    });
    routePolylines.clear();
}

function centerMapOnItems() {
    const allItems = [...items.bins, ...items.trucks, ...items.depots];
    if (allItems.length === 0) return;
    const bounds = L.latLngBounds();
    allItems.forEach(item => bounds.extend([item.lat, item.lng]));
    map.fitBounds(bounds, { padding: [20, 20] });
}

async function loadSavedFilesList() {
    try {
        const response = await fetch(`${API_BASE}/saved_files`);
        const data = await response.json();
        if (data.status === 'success') {
            updateFilesListUI(data.files);
        }
    } catch (error) {
        console.error('⚠ Failed to load files list:', error);
    }
}

function updateFilesListUI(files) {
    const container = document.getElementById('filesList');
    if (files.length === 0) {
        container.innerHTML = '<div class="no-files">No saved files</div>';
        return;
    }

    container.innerHTML = files.map(file => `
        <div class="file-item" onclick="loadSavedFile('${file.name}')">
            <span class="file-name">${file.name}</span>
            <span class="file-info">${formatFileDate(file.modified)} • ${formatFileSize(file.size)}</span>
        </div>
    `).join('');
}

async function loadSavedFile(filename) {
    try {
        const response = await fetch(`${API_BASE}/load_system/${filename}`);
        const data = await response.json();
        if (data.status === 'success') {
            loadSystemFromState(data.systemState);
            await loadSchedules(); // Ensure schedules are refreshed after system load
            showNotification(`Loaded: ${filename}`, 'success');
        } else {
            throw new Error(data.message);
        }
    } catch (error) {
        showNotification(`Load failed: ${error.message}`, 'error');
    }
}

function formatFileDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 100);

    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => document.body.removeChild(notification), 300);
    }, 3000);
}

function updateTrafficDisplay(trafficInfo) {
    if (!trafficInfo) return;

    // Smoothly update density
    const targetDensity = trafficInfo.current_density || 1.0;
    displayedTrafficDensity = lerp(displayedTrafficDensity, targetDensity, 0.2);
    document.getElementById('trafficDensity').textContent = displayedTrafficDensity.toFixed(1) + 'x';

    // Sticky traffic level: only update if backend provides a valid value
    const targetLevel = trafficInfo.traffic_level;
    if (targetLevel && targetLevel !== "Unknown") {
        displayedTrafficLevel = targetLevel;
    }
    const levelElement = document.getElementById('trafficLevel');
    levelElement.textContent = displayedTrafficLevel;
    levelElement.className = 'stat-value';
    if (displayedTrafficLevel === 'Heavy') {
        levelElement.classList.add('traffic-heavy');
    } else if (displayedTrafficLevel === 'Moderate') {
        levelElement.classList.add('traffic-moderate');
    } else {
        levelElement.classList.add('traffic-light');
    }

    // Update waiting trucks
    updateWaitingTrucks();
}

function updateWaitingTrucks() {
    const waitingContainer = document.getElementById('waitingTrucks');
    const waitingTrucks = items.trucks.filter(t => t.status === 'waiting');

    if (waitingTrucks.length === 0) {
        waitingContainer.classList.remove('active');
        waitingContainer.innerHTML = '';
        return;
    }

    waitingContainer.classList.add('active');
    let html = '<strong>Waiting Trucks:</strong>';

    waitingTrucks.forEach(truck => {
        const waitRemaining = getWaitRemainingMinutes(truck.waitingUntil, simulationTime);
        html += `
            <div class="waiting-truck-item">
                ${truck.id}: ${waitRemaining}min - ${truck.waitReason || 'Traffic optimization'}
            </div>
        `;
    });

    waitingContainer.innerHTML = html;
}

// SCHEDULING FUNCTIONS

let schedules = [];

function initializeScheduling() {
    // Schedule dispatch button
    document.getElementById('scheduleDispatchBtn').addEventListener('click', openScheduleModal);

    // View schedules button
    document.getElementById('viewSchedulesBtn').addEventListener('click', openSchedulesViewModal);

    // Schedule modal controls
    document.getElementById('scheduleModalClose').addEventListener('click', closeScheduleModal);
    document.getElementById('cancelScheduleBtn').addEventListener('click', closeScheduleModal);
    document.getElementById('createScheduleBtn').addEventListener('click', createSchedule);

    // Recurrence dropdown change handler
    document.getElementById('scheduleRecurrence').addEventListener('change', function () {
        const maxOccurrencesGroup = document.getElementById('maxOccurrencesGroup');
        if (this.value === 'daily') {
            maxOccurrencesGroup.style.display = 'block';
        } else {
            maxOccurrencesGroup.style.display = 'none';
        }
    });

    // Schedules view modal controls
    document.getElementById('schedulesViewModalClose').addEventListener('click', closeSchedulesViewModal);
    document.getElementById('closeSchedulesViewBtn').addEventListener('click', closeSchedulesViewModal);

    // Close modals when clicking outside
    window.addEventListener('click', function (event) {
        const scheduleModal = document.getElementById('scheduleModal');
        const schedulesViewModal = document.getElementById('schedulesViewModal');

        if (event.target === scheduleModal) {
            closeScheduleModal();
        }
        if (event.target === schedulesViewModal) {
            closeSchedulesViewModal();
        }
    });

    // Load existing schedules
    loadSchedules();
}

async function loadSchedules() {
    try {
        const response = await fetch(`${API_BASE}/schedules`);
        const data = await response.json();

        if (data.status === 'success') {
            schedules = data.schedules;
            console.log('🟢 Schedules loaded from backend:', schedules);
            updateSchedulesDisplay();
        } else {
            console.error('Failed to load schedules:', data.message);
        }
    } catch (error) {
        console.error('Error loading schedules:', error);
    }
}

function openScheduleModal() {
    const modal = document.getElementById('scheduleModal');

    // Populate truck dropdown
    const truckSelect = document.getElementById('scheduleTruck');
    truckSelect.innerHTML = '<option value="">Choose a truck...</option>';
    items.trucks.forEach(truck => {
        const option = document.createElement('option');
        option.value = truck.id;
        option.textContent = `${truck.id} (${truck.status})`;
        truckSelect.appendChild(option);
    });

    // Populate depot dropdown
    const depotSelect = document.getElementById('scheduleDepot');
    depotSelect.innerHTML = '<option value="">Choose a depot...</option>';
    items.depots.forEach(depot => {
        const option = document.createElement('option');
        option.value = depot.id;
        option.textContent = depot.name || depot.id;
        depotSelect.appendChild(option);
    });

    // Populate bins checkboxes
    const binsContainer = document.getElementById('scheduleBins');
    binsContainer.innerHTML = '';
    items.bins.forEach(bin => {
        const checkboxItem = document.createElement('div');
        checkboxItem.className = 'checkbox-item';
        checkboxItem.innerHTML = `
            <input type="checkbox" id="bin_${bin.id}" value="${bin.id}">
            <label for="bin_${bin.id}">${bin.id} (${bin.fillLevel}%)</label>
        `;
        binsContainer.appendChild(checkboxItem);
    });

    // Reset form
    document.getElementById('scheduleForm').reset();

    modal.style.display = 'block';
}

function closeScheduleModal() {
    document.getElementById('scheduleModal').style.display = 'none';
}

async function createSchedule() {
    try {
        const truckId = document.getElementById('scheduleTruck').value;
        const depotId = document.getElementById('scheduleDepot').value;
        const scheduledHour = parseInt(document.getElementById('scheduleHour').value);
        const scheduledMinute = parseInt(document.getElementById('scheduleMinute').value);
        const areaName = document.getElementById('scheduleAreaName').value.trim();
        const reason = document.getElementById('scheduleReason').value.trim();
        const recurrenceType = document.getElementById('scheduleRecurrence').value;
        const maxOccurrences = document.getElementById('scheduleMaxOccurrences').value;

        // Get selected bins
        const selectedBins = [];
        const checkboxes = document.querySelectorAll('#scheduleBins input[type="checkbox"]:checked');
        checkboxes.forEach(checkbox => {
            selectedBins.push(checkbox.value);
        });

        // Validation
        if (!truckId) {
            alert('Please select a truck');
            return;
        }
        if (!depotId) {
            alert('Please select a depot');
            return;
        }
        if (selectedBins.length === 0) {
            alert('Please select at least one bin');
            return;
        }

        // Create schedule data
        const scheduleData = {
            truck_id: truckId,
            depot_id: depotId,
            target_bin_ids: selectedBins,
            scheduled_hour: scheduledHour,
            scheduled_minute: scheduledMinute,
            area_name: areaName || `Area with ${selectedBins.length} bins`,
            reason: reason || 'Scheduled dispatch',
            recurrence_type: recurrenceType,
            recurrence_interval: 24 // Always 24 hours for daily
        };

        // Add max occurrences if specified and recurrence is daily
        if (recurrenceType === 'daily' && maxOccurrences && maxOccurrences.trim() !== '') {
            scheduleData.max_occurrences = parseInt(maxOccurrences);
        }

        // Send to backend
        const response = await fetch(`${API_BASE}/schedules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(scheduleData)
        });

        const data = await response.json();

        if (data.status === 'success') {
            console.log('✅ Schedule created successfully');
            closeScheduleModal();
            loadSchedules(); // Reload schedules

            if (recurrenceType === 'daily') {
                alert(`Daily recurring schedule created successfully! Will execute ${maxOccurrences ? maxOccurrences + ' times' : 'indefinitely'}.`);
            } else {
                alert('One-time schedule created successfully!');
            }
        } else {
            alert(`Failed to create schedule: ${data.message}`);
        }

    } catch (error) {
        console.error('Error creating schedule:', error);
        alert('Error creating schedule. Please try again.');
    }
}

async function openSchedulesViewModal() {
    const modal = document.getElementById('schedulesViewModal');
    await loadSchedules(); // Refresh schedules

    const content = document.getElementById('schedulesViewContent');

    if (schedules.length === 0) {
        content.innerHTML = '<div class="no-schedules">No schedules found</div>';
    } else {
        let html = '';
        schedules.forEach(schedule => {
            const statusClass = schedule.status;
            const timeDisplay = `${schedule.scheduled_hour.toString().padStart(2, '0')}:${schedule.scheduled_minute.toString().padStart(2, '0')}`;
            const recurrenceDisplay = schedule.recurrence_type === 'daily' ? 'Daily' : 'One-time';
            const executionInfo = schedule.recurrence_type === 'daily'
                ? `(${schedule.total_executions || 0}/${schedule.max_occurrences || '∞'} executions)`
                : '';

            html += `
                <div class="schedule-view-item">
                    <div class="schedule-view-header">
                        <div class="schedule-view-time">${timeDisplay}</div>
                        <div class="schedule-status ${statusClass}">${schedule.status}</div>
                    </div>
                    <div class="schedule-view-details">
                        <div><strong>Truck:</strong> ${schedule.truck_id}</div>
                        <div><strong>Depot:</strong> ${schedule.depot_id}</div>
                        <div><strong>Area:</strong> ${schedule.area_name}</div>
                        <div><strong>Reason:</strong> ${schedule.reason}</div>
                        <div><strong>Recurrence:</strong> ${recurrenceDisplay} ${executionInfo}</div>
                        ${schedule.next_execution_time && schedule.recurrence_type === 'daily' && schedule.status === 'pending'
                    ? `<div><strong>Next Execution:</strong> ${formatNextExecutionTime(schedule.next_execution_time)}</div>`
                    : ''
                }
                    </div>
                    <div class="schedule-view-bins">
                        <strong>Target Bins:</strong> ${schedule.target_bin_ids.join(', ')}
                    </div>
                    ${schedule.status === 'pending' ? `
                        <div class="schedule-actions">
                            <button class="btn btn-danger" onclick="deleteSchedule('${schedule.id}')">Delete</button>
                        </div>
                    ` : ''}
                </div>
            `;
        });
        content.innerHTML = html;
    }

    modal.style.display = 'block';
}

function closeSchedulesViewModal() {
    document.getElementById('schedulesViewModal').style.display = 'none';
}

async function deleteSchedule(scheduleId) {
    if (!confirm('Are you sure you want to delete this schedule?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/schedules/${scheduleId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.status === 'success') {
            console.log('✅ Schedule deleted successfully');
            loadSchedules();
            openSchedulesViewModal(); // Refresh the modal
        } else {
            alert(`Failed to delete schedule: ${data.message}`);
        }

    } catch (error) {
        console.error('Error deleting schedule:', error);
        alert('Error deleting schedule. Please try again.');
    }
}

function formatNextExecutionTime(nextExecutionTime) {
    // Use centralized formatter (HH:MM)
    return formatSimTime(nextExecutionTime, false);
}

function updateSchedulesDisplay() {
    // Update sidebar schedules summary
    const activeSchedules = schedules.filter(s => s.status === 'pending').length;
    document.getElementById('activeSchedules').textContent = activeSchedules;

    // Find next dispatch
    const pendingSchedules = schedules.filter(s => s.status === 'pending');
    if (pendingSchedules.length > 0) {
        // Sort by next execution time
        pendingSchedules.sort((a, b) => {
            const timeA = a.next_execution_time || a.scheduled_time;
            const timeB = b.next_execution_time || b.scheduled_time;
            return timeA - timeB;
        });

        const next = pendingSchedules[0];
        const nextExecutionTime = next.next_execution_time || next.scheduled_time;
        const timeDisplay = formatNextExecutionTime(nextExecutionTime);
        document.getElementById('nextDispatch').textContent = timeDisplay;
    } else {
        document.getElementById('nextDispatch').textContent = 'None';
    }

    // Update schedules list in sidebar
    const schedulesList = document.getElementById('schedulesList');
    if (activeSchedules === 0) {
        schedulesList.innerHTML = '<div class="no-items">No active schedules</div>';
    } else {
        let html = '';
        const activeSched = schedules.filter(s => s.status === 'pending').slice(0, 3); // Show first 3

        activeSched.forEach(schedule => {
            const nextExecutionTime = schedule.next_execution_time || schedule.scheduled_time;
            const timeDisplay = formatNextExecutionTime(nextExecutionTime);
            const recurrenceIcon = schedule.recurrence_type === 'daily' ? '🔄' : '📅';

            html += `
                <div class="schedule-item ${schedule.status}">
                    <div class="schedule-time">${recurrenceIcon} ${timeDisplay}</div>
                    <div class="schedule-details">${schedule.truck_id} → ${schedule.area_name}</div>
                    ${schedule.recurrence_type === 'daily'
                    ? `<div class="schedule-details">Daily (${schedule.total_executions || 0}/${schedule.max_occurrences || '∞'})</div>`
                    : ''
                }
                </div>
            `;
        });

        if (activeSchedules > 3) {
            html += `<div class="schedule-item"><div class="schedule-details">+${activeSchedules - 3} more schedules</div></div>`;
        }

        schedulesList.innerHTML = html;
    }
}