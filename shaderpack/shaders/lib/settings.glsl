// ---------------------------------------------------------------------------
// User options (shown in the shader options menu)
// ---------------------------------------------------------------------------

// Lighting
#define SUN_INTENSITY 2.0 // [1.0 1.5 2.0 2.5 3.0 3.5 4.0]
#define AMBIENT_INTENSITY 1.0 // [0.5 0.75 1.0 1.25 1.5 2.0]
#define BLOCKLIGHT_INTENSITY 1.0 // [0.5 0.75 1.0 1.25 1.5 2.0]
#define MIN_LIGHT 0.015 // [0.0 0.005 0.01 0.015 0.02 0.03 0.05]
#define HANDHELD_LIGHT

// Shadows
#define SHADOWS
#define SHADOW_SOFTNESS 1.0 // [0.5 0.75 1.0 1.5 2.0 3.0]
#define SHADOW_SAMPLES 12 // [4 8 12 16 24]
#define COLORED_SHADOWS

// Materials (labPBR 1.3)
#define NORMAL_MAPPING
#define SPECULAR_MAPPING
#define POM
#define POM_STEPS 48 // [16 24 32 48 64 96]
#define POM_DEPTH 0.25 // [0.1 0.15 0.2 0.25 0.3 0.4 0.5]
#define POM_DISTANCE 24.0 // [8.0 16.0 24.0 32.0 48.0 64.0]
#define POM_SHADOWS
#define EMISSION_STRENGTH 2.0 // [0.5 1.0 1.5 2.0 3.0 4.0 6.0]
#define SSS_STRENGTH 1.0 // [0.0 0.25 0.5 0.75 1.0 1.5 2.0]
#define WET_SURFACES

// Reflections
#define SSR
#define SSR_STEPS 24 // [12 16 24 32 48 64]
#define SSR_THRESHOLD 0.55 // [0.3 0.4 0.5 0.55 0.6 0.7 0.8]

// Water
#define WATER_WAVES
#define WATER_WAVE_HEIGHT 1.0 // [0.0 0.25 0.5 0.75 1.0 1.5 2.0]
#define WATER_REFRACTION
#define WATER_DENSITY 1.0 // [0.25 0.5 0.75 1.0 1.5 2.0 3.0]

// Sky & atmosphere
#define CLOUDS
#define CLOUD_COVERAGE 0.5 // [0.2 0.3 0.4 0.5 0.6 0.7 0.8]
#define CLOUD_HEIGHT 250.0 // [150.0 200.0 250.0 300.0 400.0]
#define STARS
#define FOG_DENSITY 1.0 // [0.0 0.25 0.5 0.75 1.0 1.5 2.0 3.0]
#define GODRAYS
#define GODRAYS_STRENGTH 0.5 // [0.1 0.25 0.5 0.75 1.0 1.5]

// Terrain
#define WAVING_PLANTS
#define WAVING_SPEED 1.0 // [0.5 0.75 1.0 1.5 2.0]

// Post-processing
#define BLOOM
#define BLOOM_STRENGTH 0.07 // [0.02 0.04 0.07 0.1 0.15 0.2]
#define EXPOSURE 1.0 // [0.5 0.7 0.85 1.0 1.2 1.4 1.7 2.0]
#define AUTO_EXPOSURE
#define SATURATION 1.0 // [0.6 0.8 0.9 1.0 1.05 1.1 1.2 1.4]
#define CONTRAST 1.0 // [0.8 0.9 1.0 1.1 1.2]
#define VIGNETTE 0.25 // [0.0 0.1 0.25 0.4 0.6]

// ---------------------------------------------------------------------------
// Engine constants (read by Iris / OptiFine)
// ---------------------------------------------------------------------------
const int shadowMapResolution = 2048; // [1024 2048 3072 4096 8192]
const float shadowDistance = 128.0; // [64.0 96.0 128.0 160.0 192.0 256.0]
const float shadowDistanceRenderMul = 1.0;
const bool shadowHardwareFiltering = true;
const float sunPathRotation = -30.0; // [-50.0 -40.0 -30.0 -20.0 -10.0 0.0 10.0 20.0 30.0]
const float ambientOcclusionLevel = 1.0;
const float eyeBrightnessHalflife = 6.0;
const float wetnessHalflife = 300.0;
const float drynessHalflife = 120.0;

#define SHADOW_DISTORT 0.85

// make every boolean option visible to the Iris / OptiFine option parser
#ifdef HANDHELD_LIGHT
#endif
#ifdef SHADOWS
#endif
#ifdef COLORED_SHADOWS
#endif
#ifdef NORMAL_MAPPING
#endif
#ifdef SPECULAR_MAPPING
#endif
#ifdef POM
#endif
#ifdef POM_SHADOWS
#endif
#ifdef WET_SURFACES
#endif
#ifdef SSR
#endif
#ifdef WATER_WAVES
#endif
#ifdef WATER_REFRACTION
#endif
#ifdef CLOUDS
#endif
#ifdef STARS
#endif
#ifdef GODRAYS
#endif
#ifdef WAVING_PLANTS
#endif
#ifdef BLOOM
#endif
#ifdef AUTO_EXPOSURE
#endif
