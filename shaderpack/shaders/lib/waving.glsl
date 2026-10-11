// Wind animation for leaves and plants (world space offset).
vec3 waveOffset(vec3 worldPos, int id, bool topVertex) {
#ifdef WAVING_PLANTS
    float t = frameTimeCounter * WAVING_SPEED;
    float strength = 1.0 + rainStrength * 1.5;
    if (id == ID_LEAVES) {
        vec3 o;
        o.x = sin(t * 1.7 + worldPos.x * 0.7 + worldPos.y * 0.3) * 0.025;
        o.y = sin(t * 2.3 + worldPos.z * 0.8 + worldPos.x * 0.2) * 0.015;
        o.z = cos(t * 1.9 + worldPos.z * 0.6 + worldPos.y * 0.4) * 0.025;
        return o * strength;
    }
    if ((id == ID_PLANT && topVertex) || id == ID_PLANT_UPPER) {
        float gust = 0.6 + 0.4 * sin(t * 0.7 + worldPos.x * 0.05 + worldPos.z * 0.04);
        vec3 o;
        o.x = sin(t * 2.0 + worldPos.x * 0.9 + worldPos.z * 0.4) * 0.09 * gust;
        o.z = cos(t * 1.6 + worldPos.z * 0.8 + worldPos.x * 0.3) * 0.06 * gust;
        o.y = 0.0;
        return o * strength;
    }
#endif
    return vec3(0.0);
}
