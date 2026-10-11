// Sky, sun / moon light and clouds.  All colours are linear HDR.

vec3 sunDirWorld() { return normalize(mat3(gbufferModelViewInverse) * sunPosition); }
vec3 lightDirWorld() { return normalize(mat3(gbufferModelViewInverse) * shadowLightPosition); }

float dayFactor() { return smoothstep(-0.12, 0.10, sunDirWorld().y); }

vec3 sunLightColor() {
    float h = sunDirWorld().y;
    vec3 c = mix(vec3(1.0, 0.36, 0.09), vec3(1.0, 0.94, 0.86), smoothstep(0.0, 0.35, h));
    return c * smoothstep(-0.02, 0.10, h) * SUN_INTENSITY * (1.0 - rainStrength * 0.85);
}

vec3 moonLightColor() {
    float h = -sunDirWorld().y;
    return vec3(0.45, 0.58, 0.95) * 0.09 * smoothstep(-0.02, 0.10, h) * (1.0 - rainStrength * 0.8);
}

// colour of the light that casts the shadows (sun by day, moon by night)
vec3 directLightColor() {
#if defined DIM_NETHER
    return vec3(0.0);
#elif defined DIM_END
    return vec3(0.55, 0.45, 0.75) * 0.6;
#else
    return dot(shadowLightPosition, sunPosition) > 0.0 ? sunLightColor() : moonLightColor();
#endif
}

vec3 skyAmbientColor() {
#if defined DIM_NETHER
    return toLinear(fogColor) * 1.6 + vec3(0.06, 0.03, 0.02);
#elif defined DIM_END
    return vec3(0.16, 0.12, 0.22);
#else
    float d = dayFactor();
    float h = sunDirWorld().y;
    vec3 day = vec3(0.42, 0.58, 1.0) * 0.6;
    vec3 sunset = vec3(0.7, 0.45, 0.35) * 0.45;
    vec3 night = vec3(0.10, 0.13, 0.25) * 0.10;
    vec3 c = mix(night, mix(sunset, day, smoothstep(0.05, 0.35, h)), d);
    c = mix(c, vec3(luma(c)) * 0.8, rainStrength * 0.7);
    return c * AMBIENT_INTENSITY;
#endif
}

// ---------------------------------------------------------------------------
float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    return (1.0 - g2) / (4.0 * PI * pow(1.0 + g2 - 2.0 * g * cosTheta, 1.5));
}

#if !defined DIM_NETHER && !defined DIM_END
vec3 atmosphere(vec3 dir) {
    vec3 sunDir = sunDirWorld();
    float h = sunDir.y;
    float d = dayFactor();
    float up = max(dir.y, 0.0);

    vec3 zenithDay = vec3(0.10, 0.27, 0.72);
    vec3 horizonDay = vec3(0.55, 0.70, 0.92);
    vec3 zenithNight = vec3(0.004, 0.007, 0.018);
    vec3 horizonNight = vec3(0.012, 0.017, 0.035);

    vec3 zenith = mix(zenithNight, zenithDay, d);
    vec3 horizon = mix(horizonNight, horizonDay, d);
    vec3 c = mix(horizon, zenith, pow(up, 0.5));

    // sunrise / sunset glow
    float twilight = smoothstep(0.45, 0.0, abs(h)) * smoothstep(-0.25, 0.0, h);
    float towardSun = dot(normalize(dir.xz + 1e-4), normalize(sunDir.xz + 1e-4)) * 0.5 + 0.5;
    vec3 glow = mix(vec3(0.9, 0.35, 0.12), vec3(1.0, 0.6, 0.3), towardSun);
    c += glow * twilight * exp(-up * 5.0) * (0.25 + 0.75 * towardSun * towardSun) * 1.2;

    // mie halo around the sun
    float mu = dot(dir, sunDir);
    c += sunLightColor() * henyeyGreenstein(mu, 0.76) * 0.12;
    // moon halo
    c += moonLightColor() * henyeyGreenstein(-mu, 0.8) * 0.6;

    // below the horizon: fade to a darker ground haze
    c = mix(c, horizon * 0.35, smoothstep(0.0, -0.25, dir.y));

    // rain
    c = mix(c, vec3(luma(c)) * 0.55, rainStrength * 0.85);
    return c;
}

float cloudDensity(vec2 p) {
    float t = frameTimeCounter * 0.6;
    p += vec2(t, t * 0.3);
    float n = 0.0, a = 0.55, f = 1.0;
    for (int i = 0; i < 5; i++) {
        n += a * vnoise(p * f * 0.0032 + float(i) * 7.31);
        f *= 2.17;
        a *= 0.5;
    }
    float coverage = mix(CLOUD_COVERAGE, 0.95, rainStrength);
    return smoothstep(1.0 - coverage, 1.0 - coverage + 0.35, n);
}

vec4 clouds(vec3 dir) {
    if (dir.y < 0.01) return vec4(0.0);
    float t = (CLOUD_HEIGHT - cameraPosition.y) / dir.y;
    if (t < 0.0) return vec4(0.0);
    vec2 p = cameraPosition.xz + dir.xz * t;
    float dens = cloudDensity(p);
    if (dens < 0.001) return vec4(0.0);
    vec3 sunDir = sunDirWorld();
    vec3 ld = lightDirWorld();
    // self shadowing: sample towards the light
    float shadow = cloudDensity(p + ld.xz * 60.0);
    float powder = 1.0 - exp(-dens * 2.0);
    vec3 light = directLightColor() * (1.0 - shadow * 0.7) * powder * 0.8;
    light += directLightColor() * henyeyGreenstein(dot(dir, ld), 0.6) * 0.9 * (1.0 - shadow);
    vec3 amb = skyAmbientColor() * 1.1 + atmosphere(vec3(0.0, 1.0, 0.0)) * 0.4;
    vec3 col = amb * (1.0 - dens * 0.35) + light;
    col = mix(col, vec3(luma(col)) * 0.7, rainStrength * 0.6);
    // fade with distance
    float fade = exp(-t * 0.00045) * smoothstep(0.01, 0.12, dir.y);
    return vec4(col, dens * fade);
}

float stars(vec3 dir) {
    vec3 p = floor(dir * 320.0);
    float s = hash13(p);
    float star = step(0.9975, s) * (s - 0.9975) / 0.0025;
    float twinkle = 0.6 + 0.4 * sin(frameTimeCounter * 3.0 + s * 100.0);
    return star * twinkle * smoothstep(0.0, 0.2, dir.y);
}
#endif

// full sky colour for a world-space direction (no sun disk)
vec3 getSky(vec3 dir) {
#if defined DIM_NETHER
    return toLinear(fogColor) * 1.2;
#elif defined DIM_END
    vec3 c = vec3(0.04, 0.025, 0.06);
    c += vec3(0.12, 0.05, 0.18) * pow(1.0 - abs(dir.y), 4.0);
    return c;
#else
    return atmosphere(dir);
#endif
}

vec3 skyWithClouds(vec3 dir) {
    vec3 c = getSky(dir);
#if defined CLOUDS && !defined DIM_NETHER && !defined DIM_END
    vec4 cl = clouds(dir);
    c = mix(c, cl.rgb, cl.a);
#endif
    return c;
}

vec3 sunDisk(vec3 dir) {
#if defined DIM_NETHER || defined DIM_END
    return vec3(0.0);
#else
    float mu = dot(dir, sunDirWorld());
    float disk = smoothstep(0.99955, 0.9997, mu);
    return sunLightColor() * disk * 60.0 * (1.0 - rainStrength);
#endif
}
