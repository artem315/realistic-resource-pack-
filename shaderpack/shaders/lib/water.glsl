// Procedural water waves.
float waterHeight(vec2 p) {
    float t = frameTimeCounter;
    float h = 0.0;
    h += vnoise(p * 0.35 + vec2(t * 0.35, t * 0.2)) * 0.50;
    h += vnoise(p * 0.8 - vec2(t * 0.25, -t * 0.45)) * 0.28;
    h += vnoise(p * 1.9 + vec2(-t * 0.6, t * 0.5)) * 0.14;
    h += vnoise(p * 4.1 + vec2(t * 0.9, t * 0.7)) * 0.08;
    return h;
}

vec3 waterNormalWorld(vec3 worldPos) {
#ifdef WATER_WAVES
    float e = 0.04;
    vec2 p = worldPos.xz;
    float h0 = waterHeight(p);
    float hx = waterHeight(p + vec2(e, 0.0));
    float hz = waterHeight(p + vec2(0.0, e));
    float s = 0.18 * WATER_WAVE_HEIGHT * (1.0 + rainStrength);
    return normalize(vec3(-(hx - h0) / e * s, 1.0, -(hz - h0) / e * s));
#else
    return vec3(0.0, 1.0, 0.0);
#endif
}
