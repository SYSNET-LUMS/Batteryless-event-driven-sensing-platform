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

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    initializeControls();
    initializeModal();
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
        getStatusColor: function(bin) {
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
        getStatusColor: function(truck) {
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
        getStatusColor: function(depot) {
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
}

function initializeControls() {
    // Simulation controls
    document.getElementById('startBtn').addEventListener('click', startSimulation);
    document.getElementById('stopBtn').addEventListener('click', stopSimulation);
    document.getElementById('resetBtn').addEventListener('click', resetSimulation);
    
    // Speed slider
    const speedSlider = document.getElementById('speedSlider');
    speedSlider.addEventListener('input', function() {
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
    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            closeModal();
        }
    });
}

function createMarker(item, type) {
    const config = ITEM_CONFIGS[type];
    const color = config.getStatusColor(item);
    const icon = L.divIcon({
        className: `${type}-icon`,
        html: `<div style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 4px; border: 2px solid #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">${config.icon}</div>`,
        iconSize: config.size,
        iconAnchor: [config.size[0]/2, config.size[1]/2]
    });

    const marker = L.marker([item.lat, item.lng], { 
        icon: icon,
        draggable: true 
    }).addTo(map);

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

    const icon = L.divIcon({
        className: `${type}-icon`,
        html: `<div style="background: ${color}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 4px; border: 2px solid #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">${config.icon}</div>`,
        iconSize: config.size,
        iconAnchor: [config.size[0]/2, config.size[1]/2]
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

        // If there is a pending route (remaining cluster bins), resume immediately
        if (truck.pendingRoute && truck.pendingRoute.length > 0) {
            const pending = truck.pendingRoute;
            truck.pendingRoute = null;
            // Dispatch to remaining bins in the same cluster sequence
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
            simulationInterval = setInterval(simulationStep, 1000 / simulationSpeed);
            
            console.log('✅ Simulation started');
        }
        
    } catch (error) {
        console.error('⚠️ Failed to start simulation:', error);
        alert(`Failed to start simulation: ${error.message}`);
    }
}

async function applyAIRoutingDecisions() {
    try {
        const response = await fetch(`${API_BASE}/ai_decision/truck_routing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                simulation_time: simulationTime  // ADD THIS
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success' && data.result && data.result.length > 0) {
            console.log(`🚛 Processing ${data.result.length} routing decisions...`);
            
            for (const route of data.result) {
                const truck = items.trucks.find(t => t.id === route.truck_id);
                
                if (truck && truck.status === 'idle') {
                    // Check if truck should wait
                    if (route.dispatch === 'wait') {
                        truck.status = 'waiting';
                        truck.waitingUntil = simulationTime + (route.delay_min * 60);
                        truck.waitReason = route.reason;
                        truck.pendingRoute = route.route;  // Store for later
                        console.log(`${truck.id} waiting ${route.delay_min} min: ${route.reason}`);
                    } else {
                        // Dispatch immediately
                        truck.dispatchReason = route.reason;
                        truck.dispatchTime = simulationTime;
                        await assignTruckToMultipleBins(truck, route.route);
                        console.log(`${truck.id} → ${route.route.join(', ')} - ${route.reason}`);
                    }
                }
            }
        } else {
            console.log('ℹNo urgent bins for routing');
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

async function simulationStep() {
    simulationTime += simulationSpeed;
    await callBackendSimulationStep(simulationSpeed);

    items.trucks.forEach(updateTruck);

    const idleTrucks = items.trucks.filter(t => t.status === 'idle' && !t.hasAssignment);
    if (idleTrucks.length > 0) {
        await assignIdleTrucks();
    }
    updateStats();
    updateSimulationTime();

    if (simulationInterval && isSimulationRunning) {  // Add isSimulationRunning check
        clearInterval(simulationInterval);
        simulationInterval = setInterval(simulationStep, Math.max(50, 1000 / simulationSpeed));
    }
}

async function assignIdleTrucks() {
    try {
        const response = await fetch(`${API_BASE}/ai_decision/truck_routing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                simulation_time: simulationTime  // ADD THIS
            })
        });
        
        // ... rest of the function remains the same but handle 'wait' decisions
        const data = await response.json();
        
        if (data.status === 'success' && data.result?.length > 0) {
            const assignedBins = new Set();
            items.trucks.forEach(t => {
                if (t.targetBin) assignedBins.add(t.targetBin.id);
            });

            for (const route of data.result) {
                const truck = items.trucks.find(t => 
                    t.id === route.truck_id && 
                    t.status === 'idle' && 
                    !t.hasAssignment
                );
                
                if (truck && route.route && route.route.length > 0) {
                    const targetBinId = route.route[0];
                    
                    if (assignedBins.has(targetBinId)) {
                        continue;
                    }
                    
                    // Handle wait decision
                    if (route.dispatch === 'wait') {
                        truck.status = 'waiting';
                        truck.waitingUntil = simulationTime + (route.delay_min * 60);
                        truck.waitReason = route.reason;
                        truck.pendingRoute = route.route;
                        truck.hasAssignment = true;
                        console.log(`${truck.id} waiting for better traffic`);
                    } else {
                        const targetBin = items.bins.find(b => b.id === targetBinId);
                        if (targetBin && targetBin.fillLevel > 1) {
                            assignedBins.add(targetBinId);
                            truck.hasAssignment = true;
                            await assignTruckToRoute(truck, targetBin);
                            console.log(`✅ Assigned ${truck.id} → ${targetBinId}`);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error('⚠️ Idle truck assignment failed:', error);
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

    // If we already have a planned sequence of cluster bins, continue with it first
    if (Array.isArray(truck.clusterBins) && truck.clusterBins.length > 0) {
        // Remove the bin we just collected from the plan
        truck.clusterBins = truck.clusterBins.filter(b => b.id !== bin.id);

        while (truck.clusterBins.length > 0) {
            const nextPlanned = truck.clusterBins[0];
            const nextAmount = (nextPlanned.fillLevel / 100) * nextPlanned.capacity;
            if (truck.currentLoad + nextAmount <= truck.capacity) {
                truck.targetBin = nextPlanned;
                truck.status = 'traveling';
                await assignTruckToRoute(truck, nextPlanned);
                console.log(`🚛 ${truck.id} continuing to planned bin: ${nextPlanned.id}`);
                return; // continue journey within cluster
            } else {
                // Can't fit next planned bin; store remaining plan for after dump
                truck.pendingRoute = truck.clusterBins.map(b => b.id);
                truck.clusterBins = null;
                break; // proceed to return to depot below
            }
        }
    }
    
    // Check for other bins in cluster to collect
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
            console.log("Cluster bins from backend:", remainingIds);

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
                // Store the overflow to resume after dumping at depot
                truck.pendingRoute = overflowBins.map(b => b.id);
            }

            if (feasibleBins.length > 0) {
                // Save plan locally so we can continue without extra backend calls
                truck.clusterBins = feasibleBins;
                const next = feasibleBins[0];
                truck.targetBin = next;
                truck.status = 'traveling';
                await assignTruckToRoute(truck, next);
                console.log(`🚛 ${truck.id} going to next cluster bin: ${next.id}`);
                return;
            }
        }
    } catch (error) {
        console.error('Failed to check cluster bins:', error);
    }
    
    // Return to depot if no more bins to collect or truck is full
    truck.status = 'returning_to_depot';
    truck.targetBin = null;
    truck.clusterBins = null;
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
    truck.clusterBins = targetBins;  // Store all cluster bins
    truck.currentRouteIndex = 0;
    console.log(`🚛 Setting clusterBins for ${truck.id}:`, truck.clusterBins?.map(b => `${b.id}(${b.fillLevel}%)`));

    // Get route to first bin
    await assignTruckToRoute(truck, targetBins[0]);
}

async function assignTruckToRoute(truck, bin) {
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
    }
}

async function getTruckReturnRoute(truck, depot) {
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
            
            // Process clusters and assign colors
            const clusterColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6'];
            const processedClusters = new Map();
            let colorIndex = 0;
            
            if (data.clusters) {
                // Group bins by their cluster
                Object.keys(data.clusters).forEach(binId => {
                    const clusterMembers = data.clusters[binId].sort().join(',');
                    if (!processedClusters.has(clusterMembers)) {
                        processedClusters.set(clusterMembers, {
                            color: clusterColors[colorIndex % clusterColors.length],
                            bins: data.clusters[binId]
                        });
                        colorIndex++;
                    }
                });
            }
            
            // Update all bin markers
            items.bins.forEach(bin => {
                const config = ITEM_CONFIGS.bin;
                const fillColor = config.getStatusColor(bin);
                let borderColor = '#fff';
                let borderWidth = '2px';
                
                // Find if bin is in a cluster
                processedClusters.forEach((clusterInfo) => {
                    if (clusterInfo.bins.includes(bin.id)) {
                        borderColor = clusterInfo.color;
                        borderWidth = '4px';
                    }
                });
                
                const icon = L.divIcon({
                    className: 'bin-icon',
                    html: `<div style="background: ${fillColor}; width: ${config.size[0]}px; height: ${config.size[1]}px; border-radius: 50%; border: ${borderWidth} solid ${borderColor}; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">${config.icon}</div>`,
                    iconSize: config.size,
                    iconAnchor: [config.size[0]/2, config.size[1]/2]
                });
                
                bin.marker.setIcon(icon);
            });
            
            if (data.traffic_info) {
                updateTrafficDisplay(data.traffic_info);
            }
        }
    } catch (error) {
        console.error('Backend simulation step failed:', error);
    }
}

function calculateDistance(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
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
}

function updateItemsList() {
    updateBinsList();
    updateTrucksList();
    updateCollectionQueue();
}

function updateBinsList() {
    const container = document.getElementById('binsList');
    container.innerHTML = '';
    items.bins.forEach(bin => {
        const dynamicThreshold = bin.dynamic_threshold || bin.threshold || 80;
        const staticThreshold = bin.threshold || 80;
        const isTargeted = items.trucks.some(truck => truck.targetBin === bin);
        const statusText = isTargeted ? 'TARGETED' : 
                        bin.fillLevel >= dynamicThreshold ? 'NEEDS COLLECTION' : 'OK';
        
        // Show both thresholds if they differ
        const thresholdText = Math.abs(dynamicThreshold - staticThreshold) > 0.1 
            ? `DT: ${dynamicThreshold.toFixed(2)}%`
            : `T: ${staticThreshold}%`;
        
        const card = document.createElement('div');
        card.className = `item-card ${getStatusClass(bin.fillLevel)}`;
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
            const waitRemaining = Math.max(0, Math.ceil((truck.waitingUntil - simulationTime) / 60));
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

function updateCollectionQueue() {
    const container = document.getElementById('collectionQueue');
    container.innerHTML = '';
    const queue = items.bins
        .filter(bin => {
            const threshold = bin.dynamic_threshold || bin.threshold || 80;
            return bin.fillLevel >= threshold;
        })
        .sort((a, b) => b.fillLevel - a.fillLevel)
        .slice(0, 5);

    if (queue.length === 0) {
        container.innerHTML = '<div class="no-selection">No collections needed</div>';
        return;
    }

    queue.forEach(bin => {
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
        container.appendChild(card);
    });
}

function getStatusClass(fillLevel) {
    if (fillLevel >= 90) return 'urgent';
    if (fillLevel >= 70) return 'warning';
    return 'normal';
}

let displayedSimulationTime = 0;

function updateSimulationTime() {
    displayedSimulationTime = lerp(displayedSimulationTime, simulationTime, 0.2);
    
    const actualTimeInSeconds = displayedSimulationTime + (simulationStartHour * 3600);
    
    const hours = Math.floor(actualTimeInSeconds / 3600);
    const minutes = Math.floor((actualTimeInSeconds % 3600) / 60);
    const seconds = Math.floor(actualTimeInSeconds % 60);
    
    const timeString = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    const timeStringHM = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
    
    // Debug logging (remove in production)
    if (Math.floor(simulationTime) % 10 === 0 && simulationTime > 0) {
        console.log(`Time update: simulationTime=${simulationTime}, simulationStartHour=${simulationStartHour}, actualTime=${timeString}`);
    }
    
    // Update main simulation time display (map overlay)
    const timeElement = document.getElementById('simulationTime');
    if (timeElement) {
        timeElement.textContent = timeString;
        // Debug log every few seconds to check UI updates
        if (Math.floor(simulationTime) % 10 === 0 && simulationTime > 0) {
            console.log(`✅ UI Updated: Element found, set to: ${timeString}, actual element text: ${timeElement.textContent}`);
        }
    } else {
        console.error(`❌ Element with id 'simulationTime' not found!`);
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
    reader.onload = function(e) {
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
    // Load items
    ['bins', 'trucks', 'depots'].forEach(itemType => {
        const type = itemType.slice(0, -1); // Remove 's'
        systemState[itemType].forEach(itemData => {
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
        });
    });

    // Sync with backend
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
}

async function syncLoadedDataWithBackend() {
    try {
        await fetch(`${API_BASE}/initialize`, { method: 'POST' });
        
        for (const itemType of ['depots', 'bins', 'trucks']) {
            for (const item of items[itemType]) {
                const type = itemType.slice(0, -1);
                
                // FIX: Remove marker before sending
                const { marker, ...cleanItem } = item;
                
                await fetch(`${API_BASE}/${type}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cleanItem)  // Send clean data only
                });
            }
        }
        
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
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
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
    
    // Update traffic time
    document.getElementById('trafficTime').textContent = trafficInfo.time_of_day || '00:00';
    
    // Update traffic level with color
    const levelElement = document.getElementById('trafficLevel');
    levelElement.textContent = trafficInfo.traffic_level || 'Unknown';
    levelElement.className = 'stat-value';
    
    if (trafficInfo.traffic_level === 'Heavy') {
        levelElement.classList.add('traffic-heavy');
    } else if (trafficInfo.traffic_level === 'Moderate') {
        levelElement.classList.add('traffic-moderate');
    } else {
        levelElement.classList.add('traffic-light');
    }
    
    // Update density
    const density = trafficInfo.current_density || 1.0;
    document.getElementById('trafficDensity').textContent = density.toFixed(1) + 'x';
    
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
        const waitRemaining = Math.max(0, Math.ceil((truck.waitingUntil - simulationTime) / 60));
        html += `
            <div class="waiting-truck-item">
                ${truck.id}: ${waitRemaining}min - ${truck.waitReason || 'Traffic optimization'}
            </div>
        `;
    });
    
    waitingContainer.innerHTML = html;
}