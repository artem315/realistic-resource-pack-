// Shadow mapping with distortion, soft PCF and coloured translucent shadows.

vec3 distortShadow(vec3 p) {
    float f = length(p.xy) * SHADOW_DISTORT + (1.0 - SHADOW_DISTORT);
    p.xy /= f;
    p.z *= 0.2;
    return p;
}

const vec2 poisson[24] = vec2[](
    vec2(-0.613392, 0.617481), vec2(0.170019, -0.040254), vec2(-0.299417, 0.791925), vec2(0.645680, 0.493210),
    vec2(-0.651784, 0.717887), vec2(0.421003, 0.027070), vec2(-0.817194, -0.271096), vec2(-0.705374, -0.668203),
    vec2(0.977050, -0.108615), vec2(0.063326, 0.142369), vec2(0.203528, 0.214331), vec2(-0.667531, 0.326090),
    vec2(-0.098422, -0.295755), vec2(-0.885922, 0.215369), vec2(0.566637, 0.605213), vec2(0.039766, -0.396100),
    vec2(0.751946, 0.453352), vec2(0.078707, -0.715323), vec2(-0.075838, -0.529344), vec2(0.724479, -0.580798),
    vec2(0.222999, -0.215125), vec2(-0.467574, -0.405438), vec2(-0.248268, -0.814753), vec2(0.354411, -0.887570)
);

// playerPos: position relative to the camera (world orientation), normalW: world-space geometric normal
vec3 getShadow(vec3 playerPos, vec3 normalW, float noise, float softness) {
#ifdef SHADOWS
    float dist = length(playerPos);
    if (dist > shadowDistance) return vec3(1.0);
    vec3 p = playerPos + normalW * (0.03 + dist * 0.0025);
    vec4 sp = shadowProjection * (shadowModelView * vec4(p, 1.0));
    float f = length(sp.xy) * SHADOW_DISTORT + (1.0 - SHADOW_DISTORT);
    vec3 s = distortShadow(sp.xyz) * 0.5 + 0.5;
    if (any(lessThan(s, vec3(0.0))) || any(greaterThan(s, vec3(1.0)))) return vec3(1.0);
    s.z -= 0.0001;

    float radius = SHADOW_SOFTNESS * softness * 1.6 / float(shadowMapResolution);
    float a = noise * 2.0 * PI;
    mat2 rot = mat2(cos(a), sin(a), -sin(a), cos(a));
    float solid = 0.0;
    float all_ = 0.0;
    for (int i = 0; i < SHADOW_SAMPLES; i++) {
        vec2 o = rot * poisson[i] * radius;
        solid += texture(shadowtex1, vec3(s.xy + o, s.z));
    #ifdef COLORED_SHADOWS
        all_ += texture(shadowtex0, vec3(s.xy + o, s.z));
    #endif
    }
    solid /= float(SHADOW_SAMPLES);
    vec3 result = vec3(solid);
    #ifdef COLORED_SHADOWS
        all_ /= float(SHADOW_SAMPLES);
        if (all_ < solid - 0.01) {
            vec4 tint = texture(shadowcolor0, s.xy);
            vec3 t = toLinear(tint.rgb) * (1.0 - tint.a * 0.5);
            result = vec3(all_) + (solid - all_) * t;
        }
    #endif
    float fade = smoothstep(0.85, 1.0, dist / shadowDistance);
    return mix(result, vec3(1.0), fade);
#else
    return vec3(1.0);
#endif
}
