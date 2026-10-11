#define PI 3.14159265359

float sq(float x) { return x * x; }
float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
vec3 toLinear(vec3 c) { return pow(max(c, 0.0), vec3(2.2)); }
vec3 toSRGB(vec3 c) { return pow(max(c, 0.0), vec3(1.0 / 2.2)); }
float saturate(float x) { return clamp(x, 0.0, 1.0); }

vec2 octEncode(vec3 n) {
    n /= abs(n.x) + abs(n.y) + abs(n.z);
    vec2 s = vec2(n.x >= 0.0 ? 1.0 : -1.0, n.y >= 0.0 ? 1.0 : -1.0);
    vec2 e = n.z >= 0.0 ? n.xy : (1.0 - abs(n.yx)) * s;
    return e * 0.5 + 0.5;
}

vec3 octDecode(vec2 e) {
    e = e * 2.0 - 1.0;
    vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
    float t = max(-n.z, 0.0);
    n.x += n.x >= 0.0 ? -t : t;
    n.y += n.y >= 0.0 ? -t : t;
    return normalize(n);
}

// interleaved gradient noise, animated
float ign(vec2 p) {
    p += float(frameCounter % 64) * 5.588238;
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float hash13(vec3 p3) {
    p3 = fract(p3 * 0.1031);
    p3 += dot(p3, p3.zyx + 31.32);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash12(i), b = hash12(i + vec2(1, 0)), c = hash12(i + vec2(0, 1)), d = hash12(i + vec2(1, 1));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

vec3 screenToView(vec3 s) {
    vec4 p = gbufferProjectionInverse * vec4(s * 2.0 - 1.0, 1.0);
    return p.xyz / p.w;
}

vec3 viewToScreen(vec3 v) {
    vec4 p = gbufferProjection * vec4(v, 1.0);
    return p.xyz / p.w * 0.5 + 0.5;
}

float linearDepth(float d) {
    return (2.0 * near * far) / (far + near - (d * 2.0 - 1.0) * (far - near));
}

// lightmap coords from the vertex stage -> 0..1
vec2 remapLightmap(vec2 lm) {
    return clamp((lm - 1.0 / 32.0) * 32.0 / 30.0, 0.0, 1.0);
}
