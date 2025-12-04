/**
 * Google Earth Engine Tile Integration for Machakos AIDSTTUP
 * This integrates GEE JavaScript API with Django for dynamic tile loading
 */

class GEEIntegration {
    constructor() {
        this.map = null;
        this.geeLayers = {};
        this.currentAOI = null;
        this.isGEEInitialized = false;
        
        // Configuration
        this.config = {
            tileScale: 16,
            maxZoom: 18,
            minZoom: 8,
            visParams: {
                'NDVI': {min: 0, max: 1, palette: ['red', 'yellow', 'green']},
                'EVI': {min: -1, max: 1, palette: ['blue', 'white', 'green']},
                'NDMI': {min: -1, max: 1, palette: ['white', 'blue']},
                'SAVI': {min: 0.1, max: 0.7, palette: ['brown', 'yellow', 'green']},
                'NDRE': {min: 0.1, max: 0.45, palette: ['purple', 'yellow', 'green']}
            }
        };
    }
    
    /**
     * Initialize GEE with Django backend
     */
    async initialize() {
        try {
            // Check if GEE is available
            if (typeof ee === 'undefined') {
                console.error('Google Earth Engine API not loaded');
                this.loadGEEAPI();
                return false;
            }
            
            // Initialize GEE (this would be done server-side in Django)
            // For client-side, we need to handle authentication differently
            this.isGEEInitialized = true;
            console.log('GEE Integration initialized');
            return true;
            
        } catch (error) {
            console.error('GEE initialization failed:', error);
            return false;
        }
    }
    
    /**
     * Load GEE API dynamically
     */
    loadGEEAPI() {
        const script = document.createElement('script');
        script.src = 'https://code.earthengine.google.com/ee_api_js.js';
        script.onload = () => {
            console.log('GEE API loaded');
            this.initialize();
        };
        script.onerror = () => {
            console.error('Failed to load GEE API');
        };
        document.head.appendChild(script);
    }
    
    /**
     * Load Machakos County boundary
     */
    async loadMachakosBoundary() {
        try {
            // This would load from Django backend or GEE Assets
            const response = await fetch('/api/machakos-boundary/');
            const data = await response.json();
            
            // Convert to ee.Geometry
            this.currentAOI = ee.Geometry(data.geometry);
            
            // Add to map as polygon
            if (this.map) {
                L.geoJSON(data).addTo(this.map);
                this.map.fitBounds(L.geoJSON(data).getBounds());
            }
            
            return this.currentAOI;
            
        } catch (error) {
            console.error('Error loading Machakos boundary:', error);
            return null;
        }
    }
    
    /**
     * Get NDVI layer for a specific date
     * @param {string} date - YYYY-MM-DD format
     * @param {number} bufferKm - Buffer around AOI in kilometers
     */
    async getNDVILayer(date, bufferKm = 0) {
        if (!this.isGEEInitialized || !this.currentAOI) {
            console.error('GEE not initialized or no AOI set');
            return null;
        }
        
        try {
            // Buffer the AOI if needed
            let geometry = this.currentAOI;
            if (bufferKm > 0) {
                geometry = geometry.buffer(bufferKm * 1000);
            }
            
            // Create date range (monthly composite)
            const startDate = ee.Date(date);
            const endDate = startDate.advance(1, 'month');
            
            // Load Sentinel-2 collection
            const sentinel = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(geometry)
                .filterDate(startDate, endDate)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20));
            
            // Cloud masking function
            const maskClouds = function(image) {
                const qa = image.select('QA60');
                const cloudBitMask = 1 << 10;
                const cirrusBitMask = 1 << 11;
                const mask = qa.bitwiseAnd(cloudBitMask).eq(0)
                              .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
                return image.updateMask(mask).divide(10000);
            };
            
            // Calculate NDVI
            const addNDVI = function(image) {
                const ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
                return image.addBands(ndvi);
            };
            
            // Process collection
            const processed = sentinel
                .map(maskClouds)
                .map(addNDVI);
            
            // Create median composite
            const composite = processed.median();
            
            // Get tile URL
            const tileUrl = composite.select('NDVI')
                .getMap(this.config.visParams.NDVI)
                .tileUrl;
            
            return {
                tileUrl: tileUrl,
                image: composite,
                bounds: geometry.bounds().getInfo()
            };
            
        } catch (error) {
            console.error('Error generating NDVI layer:', error);
            return null;
        }
    }
    
    /**
     * Get multiple indices at once
     * @param {string} date - YYYY-MM-DD format
     * @param {string[]} indices - Array of indices to calculate
     */
    async getMultipleIndices(date, indices = ['NDVI', 'NDMI', 'SAVI']) {
        if (!this.isGEEInitialized) return null;
        
        try {
            const startDate = ee.Date(date);
            const endDate = startDate.advance(1, 'month');
            
            const sentinel = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(this.currentAOI)
                .filterDate(startDate, endDate)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20));
            
            // Cloud masking
            const maskClouds = function(image) {
                const qa = image.select('QA60');
                const cloudBitMask = 1 << 10;
                const cirrusBitMask = 1 << 11;
                const mask = qa.bitwiseAnd(cloudBitMask).eq(0)
                              .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
                return image.updateMask(mask).divide(10000);
            };
            
            // Calculate all indices
            const calculateIndices = function(image) {
                const ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
                const evi = image.expression(
                    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
                    {
                        'NIR': image.select('B8'),
                        'RED': image.select('B4'),
                        'BLUE': image.select('B2')
                    }
                ).rename('EVI');
                
                const ndmi = image.normalizedDifference(['B8', 'B11']).rename('NDMI');
                
                const savi = image.expression(
                    '((NIR - RED) / (NIR + RED + L)) * (1 + L)',
                    {
                        'NIR': image.select('B8'),
                        'RED': image.select('B4'),
                        'L': 0.5
                    }
                ).rename('SAVI');
                
                const ndre = image.normalizedDifference(['B8', 'B5']).rename('NDRE');
                
                return image.addBands([ndvi, evi, ndmi, savi, ndre]);
            };
            
            const processed = sentinel
                .map(maskClouds)
                .map(calculateIndices);
            
            const composite = processed.median();
            
            // Return tile URLs for each index
            const tileUrls = {};
            indices.forEach(index => {
                if (this.config.visParams[index]) {
                    tileUrls[index] = composite.select(index)
                        .getMap(this.config.visParams[index])
                        .tileUrl;
                }
            });
            
            return {
                tileUrls: tileUrls,
                image: composite,
                indices: indices
            };
            
        } catch (error) {
            console.error('Error generating multiple indices:', error);
            return null;
        }
    }
    
    /**
     * Get rainfall data from CHIRPS
     * @param {string} date - YYYY-MM-DD format
     */
    async getRainfallData(date) {
        if (!this.isGEEInitialized) return null;
        
        try {
            const startDate = ee.Date(date);
            const endDate = startDate.advance(1, 'month');
            
            const rainfall = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                .filterDate(startDate, endDate)
                .select('precipitation')
                .sum();
            
            // Get tile URL
            const tileUrl = rainfall.getMap({
                min: 0,
                max: 300,
                palette: ['white', 'blue', 'darkblue']
            }).tileUrl;
            
            // Calculate statistics
            const stats = rainfall.reduceRegion({
                reducer: ee.Reducer.mean(),
                geometry: this.currentAOI,
                scale: 5000,
                maxPixels: 1e9
            });
            
            const meanRainfall = stats.get('precipitation');
            
            return {
                tileUrl: tileUrl,
                meanRainfall: meanRainfall,
                image: rainfall
            };
            
        } catch (error) {
            console.error('Error getting rainfall data:', error);
            return null;
        }
    }
    
    /**
     * Add GEE tile layer to Leaflet map
     * @param {L.Map} map - Leaflet map instance
     * @param {string} tileUrl - GEE tile URL
     * @param {string} layerName - Name for the layer
     */
    addTileLayer(map, tileUrl, layerName) {
        if (!map || !tileUrl) return null;
        
        const tileLayer = L.tileLayer(tileUrl, {
            maxZoom: this.config.maxZoom,
            minZoom: this.config.minZoom,
            attribution: 'Google Earth Engine',
            tileSize: 256
        });
        
        tileLayer.addTo(map);
        this.geeLayers[layerName] = tileLayer;
        
        return tileLayer;
    }
    
    /**
     * Remove GEE tile layer
     * @param {string} layerName - Name of layer to remove
     */
    removeTileLayer(layerName) {
        if (this.geeLayers[layerName]) {
            this.map.removeLayer(this.geeLayers[layerName]);
            delete this.geeLayers[layerName];
        }
    }
    
    /**
     * Clear all GEE layers
     */
    clearAllLayers() {
        Object.keys(this.geeLayers).forEach(layerName => {
            this.removeTileLayer(layerName);
        });
    }
    
    /**
     * Run zonal statistics for farm polygons
     * @param {Array} farmFeatures - Array of farm features with geometries
     * @param {string} date - Date for analysis
     * @param {string} index - Index to analyze
     */
    async runZonalStatistics(farmFeatures, date, index = 'NDVI') {
        if (!this.isGEEInitialized) return null;
        
        try {
            // Convert farm features to ee.FeatureCollection
            const eeFeatures = farmFeatures.map(feature => {
                const geometry = ee.Geometry(feature.geometry);
                return ee.Feature(geometry, {
                    farm_id: feature.id,
                    name: feature.name || 'Unnamed'
                });
            });
            
            const featureCollection = ee.FeatureCollection(eeFeatures);
            
            // Get image for the date
            const startDate = ee.Date(date);
            const endDate = startDate.advance(1, 'month');
            
            const sentinel = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(featureCollection.geometry())
                .filterDate(startDate, endDate)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20));
            
            // Cloud masking
            const maskClouds = function(image) {
                const qa = image.select('QA60');
                const cloudBitMask = 1 << 10;
                const cirrusBitMask = 1 << 11;
                const mask = qa.bitwiseAnd(cloudBitMask).eq(0)
                              .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
                return image.updateMask(mask).divide(10000);
            };
            
            // Calculate index
            const calculateIndex = function(image) {
                switch(index) {
                    case 'NDVI':
                        return image.normalizedDifference(['B8', 'B4']).rename(index);
                    case 'NDMI':
                        return image.normalizedDifference(['B8', 'B11']).rename(index);
                    case 'SAVI':
                        return image.expression(
                            '((NIR - RED) / (NIR + RED + L)) * (1 + L)',
                            {
                                'NIR': image.select('B8'),
                                'RED': image.select('B4'),
                                'L': 0.5
                            }
                        ).rename(index);
                    case 'NDRE':
                        return image.normalizedDifference(['B8', 'B5']).rename(index);
                    default:
                        return image.normalizedDifference(['B8', 'B4']).rename('NDVI');
                }
            };
            
            const processed = sentinel
                .map(maskClouds)
                .map(calculateIndex);
            
            const composite = processed.median();
            
            // Run zonal statistics
            const results = composite.reduceRegions({
                collection: featureCollection,
                reducer: ee.Reducer.mean(),
                scale: 10,
                tileScale: 2
            });
            
            // Get results
            const resultsList = results.getInfo();
            
            return resultsList.features.map(feature => ({
                farm_id: feature.properties.farm_id,
                farm_name: feature.properties.name,
                [index]: feature.properties[index] || null,
                geometry: feature.geometry
            }));
            
        } catch (error) {
            console.error('Error running zonal statistics:', error);
            return null;
        }
    }
    
    /**
     * Export analysis results to CSV
     * @param {Array} results - Analysis results from zonal statistics
     * @param {string} filename - Output filename
     */
    exportToCSV(results, filename = 'gee_analysis.csv') {
        if (!results || results.length === 0) return;
        
        // Convert to CSV
        const headers = Object.keys(results[0]);
        const csvRows = [
            headers.join(','),
            ...results.map(row => 
                headers.map(header => 
                    JSON.stringify(row[header] || '')
                ).join(',')
            )
        ];
        
        const csvString = csvRows.join('\n');
        
        // Create download link
        const blob = new Blob([csvString], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        
        a.setAttribute('href', url);
        a.setAttribute('download', filename);
        a.click();
        
        window.URL.revokeObjectURL(url);
    }
    
    /**
     * Create timelapse animation
     * @param {string} startDate - Start date YYYY-MM-DD
     * @param {string} endDate - End date YYYY-MM-DD
     * @param {string} index - Index to visualize
     * @param {number} frameRate - Frames per second
     */
    async createTimelapse(startDate, endDate, index = 'NDVI', frameRate = 2) {
        if (!this.isGEEInitialized) return null;
        
        try {
            const start = ee.Date(startDate);
            const end = ee.Date(endDate);
            
            // Create monthly collection
            const months = ee.List.sequence(0, end.difference(start, 'month').subtract(1));
            
            const monthlyImages = months.map(monthOffset => {
                const monthStart = start.advance(monthOffset, 'month');
                const monthEnd = monthStart.advance(1, 'month');
                
                const sentinel = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                    .filterBounds(this.currentAOI)
                    .filterDate(monthStart, monthEnd)
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30));
                
                // Cloud masking
                const maskClouds = function(image) {
                    const qa = image.select('QA60');
                    const cloudBitMask = 1 << 10;
                    const cirrusBitMask = 1 << 11;
                    const mask = qa.bitwiseAnd(cloudBitMask).eq(0)
                                  .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
                    return image.updateMask(mask).divide(10000);
                };
                
                // Calculate index
                const calculateIndex = function(image) {
                    switch(index) {
                        case 'NDVI':
                            return image.normalizedDifference(['B8', 'B4']).rename(index);
                        case 'NDMI':
                            return image.normalizedDifference(['B8', 'B11']).rename(index);
                        default:
                            return image.normalizedDifference(['B8', 'B4']).rename('NDVI');
                    }
                };
                
                return sentinel
                    .map(maskClouds)
                    .map(calculateIndex)
                    .median()
                    .set('system:time_start', monthStart.millis());
            });
            
            const collection = ee.ImageCollection(monthlyImages);
            
            // Get animation URL
            const videoArgs = {
                dimensions: 768,
                region: this.currentAOI,
                framesPerSecond: frameRate,
                crs: 'EPSG:3857',
                min: this.config.visParams[index]?.min || 0,
                max: this.config.visParams[index]?.max || 1,
                palette: this.config.visParams[index]?.palette || ['red', 'yellow', 'green']
            };
            
            // Note: getVideoThumbURL requires proper GEE permissions
            // const videoUrl = collection.getVideoThumbURL(videoArgs);
            
            return {
                collection: collection,
                // videoUrl: videoUrl,
                months: months.length().getInfo(),
                startDate: start.format().getInfo(),
                endDate: end.format().getInfo()
            };
            
        } catch (error) {
            console.error('Error creating timelapse:', error);
            return null;
        }
    }
}

// Create global instance
window.GEEIntegration = new GEEIntegration();

// Example usage:
/*
// Initialize
await window.GEEIntegration.initialize();

// Load Machakos boundary
await window.GEEIntegration.loadMachakosBoundary();

// Get NDVI layer for current month
const ndviLayer = await window.GEEIntegration.getNDVILayer('2023-06-01');
if (ndviLayer && window.map) {
    window.GEEIntegration.addTileLayer(window.map, ndviLayer.tileUrl, 'NDVI_2023_06');
}

// Run zonal statistics for farms
const farmResults = await window.GEEIntegration.runZonalStatistics(
    farmFeatures, 
    '2023-06-01', 
    'NDVI'
);

// Export to CSV
window.GEEIntegration.exportToCSV(farmResults, 'farm_analysis_june_2023.csv');
*/